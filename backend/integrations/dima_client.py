import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict


class DiMAGenerationError(RuntimeError):
    pass


def _env_required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise DiMAGenerationError(f"Environment variable {name} is not set")
    return value


def _build_env() -> Dict[str, str]:
    env = os.environ.copy()

    dima_repo_dir = _env_required("DIMA_REPO_DIR")
    salad_root = _env_required("SALAD_ROOT")

    old_pythonpath = env.get("PYTHONPATH", "")
    if old_pythonpath:
        env["PYTHONPATH"] = f"{dima_repo_dir}:{salad_root}:{old_pythonpath}"
    else:
        env["PYTHONPATH"] = f"{dima_repo_dir}:{salad_root}"

    env["HYDRA_FULL_ERROR"] = env.get("HYDRA_FULL_ERROR", "1")

    cuda_devices = env.get("DIMA_CUDA_VISIBLE_DEVICES")
    if cuda_devices:
        env["CUDA_VISIBLE_DEVICES"] = cuda_devices

    env.setdefault("MASTER_ADDR", "127.0.0.1")
    env.setdefault("MASTER_PORT", "29555")
    env.setdefault("RANK", "0")
    env.setdefault("WORLD_SIZE", "1")

    return env


def run_dima_generation(
    generation_params: Dict[str, Any],
    output_pdb_path: Path,
) -> Dict[str, Any]:
    """
    Запускает DiMA generate_structure.py как subprocess.

    На вход:
      generation_params: {"length": ..., "name": ..., "created_at": ...}
      output_pdb_path: финальный путь, куда надо положить PDB в uploads/

    На выход:
      dict с метаданными, которые уже ожидает protein_generation.py.
    """

    start_time = time.time()

    length = int(generation_params.get("length", 120))

    dima_repo_dir = Path(_env_required("DIMA_REPO_DIR"))
    dima_python = Path(_env_required("DIMA_PYTHON"))
    dima_script = Path(
        os.environ.get(
            "DIMA_GENERATE_SCRIPT",
            str(dima_repo_dir / "generate_structure.py"),
        )
    )

    structure_decoder_path = _env_required("DIMA_STRUCTURE_DECODER_PATH")
    statistics_path = _env_required("DIMA_STATISTICS_PATH")
    structure_config_name = _env_required("DIMA_STRUCTURE_CONFIG_NAME")

    checkpoints_prefix = os.environ.get("DIMA_CHECKPOINTS_PREFIX", "dima-salad-ft200k")
    checkpoint_name = os.environ.get("DIMA_CHECKPOINT_NAME", "400000")
    scheduler = os.environ.get("DIMA_SCHEDULER", "cosine")

    n_steps = int(os.environ.get("DIMA_N_STEPS", "1000"))
    batch_size = int(os.environ.get("DIMA_BATCH_SIZE", "1"))
    timeout_sec = int(os.environ.get("DIMA_TIMEOUT_SEC", "3600"))

    if not dima_repo_dir.exists():
        raise DiMAGenerationError(f"DIMA_REPO_DIR does not exist: {dima_repo_dir}")

    if not dima_python.exists():
        raise DiMAGenerationError(f"DIMA_PYTHON does not exist: {dima_python}")

    if not dima_script.exists():
        raise DiMAGenerationError(f"DIMA_GENERATE_SCRIPT does not exist: {dima_script}")

    output_pdb_path = Path(output_pdb_path)
    output_pdb_path.parent.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex
    save_dir = dima_repo_dir / "generated_from_backend" / run_id
    save_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(dima_python),
        str(dima_script),

        f"project.path={dima_repo_dir}",

        "encoder=salad",
        "encoder.config.encoder_style=bb",
        f"encoder.config.structure_decoder_path={structure_decoder_path}",
        f"encoder.config.statistics_path={statistics_path}",
        f"encoder.config.structure_config_name={structure_config_name}",

        f"scheduler={scheduler}",

        f"project.checkpoints_prefix={checkpoints_prefix}",
        f"+project.checkpoint_name={checkpoint_name}",

        f"+gen_length={length}",

        f"generation.N_steps={n_steps}",
        "generation.num_gen_samples=1",
        f"generation.batch_size={batch_size}",
        f"generation.save_dir={save_dir}",

        "metrics.mmfid.enabled=false",
    ]

    env = _build_env()

    lock_path = dima_repo_dir / "dima_generation.lock"

    try:
        import fcntl

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)

            result = subprocess.run(
                cmd,
                cwd=str(dima_repo_dir),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
            )

            fcntl.flock(lock_file, fcntl.LOCK_UN)

    except subprocess.TimeoutExpired as exc:
        raise DiMAGenerationError(
            f"DiMA generation timeout after {timeout_sec} seconds"
        ) from exc

    if result.returncode != 0:
        raise DiMAGenerationError(
            "DiMA generation failed\n\n"
            f"COMMAND:\n{' '.join(cmd)}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    pdb_files = sorted(save_dir.rglob("*.pdb"))

    if not pdb_files:
        raise DiMAGenerationError(
            "DiMA finished successfully, but no PDB files were found\n\n"
            f"save_dir={save_dir}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    generated_pdb_path = pdb_files[0]
    shutil.copyfile(generated_pdb_path, output_pdb_path)

    generation_time_sec = round(time.time() - start_time, 3)

    return {
        "sequence": None,
        "mean_plddt": None,

        "fixed_length": length,
        "generated_lengths": [length],
        "num_samples": 1,

        "embedding_shape": None,

        "generation_time_sec": generation_time_sec,

        "generation": {
            "N_steps": n_steps,
            "t_min": None,
            "embedding_size": None,
            "max_sequence_len": None,
        },

        "decoder": {
            "structure_config_name": structure_config_name,
            "latent_size": None,
            "pad_size": None,
            "num_recycle": None,
        },

        "normalizer": {
            "loaded": True,
        },

        "paths": {
            "save_dir": str(save_dir),
            "generated_pdb_path": str(generated_pdb_path),
            "output_pdb_path": str(output_pdb_path),
        },

        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }