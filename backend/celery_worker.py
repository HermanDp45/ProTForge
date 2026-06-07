import os

from celery import Celery

from . import crud
from .database import SessionLocal
from .services.protein_generation import create_generated_structure


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(__name__)
celery.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,

    # Важно для GPU: не брать заранее пачку задач.
    worker_prefetch_multiplier=1,

    # Задача считается подтверждённой только после завершения.
    task_acks_late=True,

    # Если worker умер, задача вернётся в очередь.
    task_reject_on_worker_lost=True,

    # Чтобы долго висящие задачи не терялись Redis'ом.
    broker_transport_options={
        "visibility_timeout": 7200,
    },
    result_expires=7200,
)


@celery.task(name="generate_protein_async", bind=True)
def generate_protein_async(self, project_id: int, user_id: int, generation_params: dict):
    db = SessionLocal()

    try:
        print("=== REAL DIMA CELERY TASK STARTED ===", flush=True)
        print("project_id =", project_id, flush=True)
        print("user_id =", user_id, flush=True)
        print("generation_params =", generation_params, flush=True)

        project = crud.get_project_by_id(db, project_id)
        if project is None or project.owner_id != user_id:
            raise ValueError(
                f"Project not found or forbidden: project_id={project_id}, user_id={user_id}"
            )

        structure = create_generated_structure(
            db=db,
            project_id=project_id,
            generation_params=generation_params,
            name_prefix="DiMA",
        )

        print("=== REAL DIMA CELERY TASK FINISHED ===", flush=True)
        print("structure_id =", structure.id, flush=True)
        print("pdb_file_path =", structure.pdb_file_path, flush=True)

        return {
            "status": "success",
            "project_id": project_id,
            "structure_id": structure.id,
            "pdb_file_path": structure.pdb_file_path,
            "name": structure.name,
            "metrics": structure.metrics,
        }

    except Exception as exc:
        db.rollback()
        print("=== REAL DIMA CELERY TASK FAILED ===", flush=True)
        print(repr(exc), flush=True)
        raise

    finally:
        db.close()