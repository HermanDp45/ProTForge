import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .. import crud, schemas, models
from ..config import UPLOAD_DIR
from ..integrations.dima_client import run_dima_generation
from ..utils import compact_dict, extract_pdb_metrics, extract_sequence_from_pdb


def _positive_float(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None

def create_generated_structure(
    db: Session,
    project_id: int,
    generation_params: Dict[str, object],
    name_prefix: str = "DiMA",
) -> models.ProteinStructure:
    length = int(generation_params.get("length", 120))
    requested_name = str(generation_params.get("name", "")).strip()
    structure_name = requested_name or f"{name_prefix}_{uuid.uuid4().hex[:8]}"

    file_id = f"{uuid.uuid4()}.pdb"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_path = UPLOAD_DIR / file_id

    dima_result = run_dima_generation(
        generation_params=generation_params,
        output_pdb_path=storage_path,
    )

    pdb_text = storage_path.read_text(encoding="utf-8", errors="ignore")
    sequence = extract_sequence_from_pdb(pdb_text) or str(dima_result.get("sequence", "")).strip()
    actual_length = len(sequence) if sequence else None
    pdb_metrics = extract_pdb_metrics(pdb_text)
    mean_plddt = _positive_float(dima_result.get("mean_plddt"))
    generation_meta = dima_result.get("generation") or {}
    decoder_meta = dima_result.get("decoder") or {}
    normalizer_meta = dima_result.get("normalizer") or {}

    generation_time_sec = dima_result.get("generation_time_sec")
    metrics = compact_dict({
        "length": actual_length,
        "requested_length": length,
        "length_delta": actual_length - length if actual_length is not None else None,
        "generation_time_sec": generation_time_sec,
        "generation_time": f"{generation_time_sec}s" if generation_time_sec is not None else None,
        "source": "DiMA",
        **pdb_metrics,
        "fixed_length": dima_result.get("fixed_length"),
        "generated_lengths": dima_result.get("generated_lengths"),
        "embedding_shape": dima_result.get("embedding_shape"),
        "num_samples": dima_result.get("num_samples"),
        "sampling_steps": generation_meta.get("N_steps"),
        "sampling_t_min": generation_meta.get("t_min"),
        "latent_embedding_size": generation_meta.get("embedding_size"),
        "max_sequence_len": generation_meta.get("max_sequence_len"),
        "decoder_config": decoder_meta.get("structure_config_name"),
        "decoder_latent_size": decoder_meta.get("latent_size"),
        "decoder_pad_size": decoder_meta.get("pad_size"),
        "decoder_num_recycle": decoder_meta.get("num_recycle"),
        "normalizer_loaded": normalizer_meta.get("loaded"),
    })

    if mean_plddt is not None:
        metrics["pLDDT"] = mean_plddt
        metrics["mean_plddt"] = mean_plddt
        metrics["plddt_source"] = "dima_result"

    stored_generation_params = compact_dict({
        "name": requested_name or None,
        "length": length,
        "source": "DiMA",
        "created_at": generation_params.get("created_at"),
    })

    structure_data = schemas.ProteinStructureCreate(
        name=structure_name,
        pdb_file_path=f"/uploads/{file_id}",
        fasta_sequence=sequence,
        generation_params=stored_generation_params,
        metrics=metrics,
    )

    return crud.create_protein_structure(db, structure_data, project_id)
