import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Dict, List

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import auth, crud, models, schemas
from .database import engine, get_db
from .utils import compact_dict, ensure_utc_iso, extract_pdb_metrics, extract_sequence_from_pdb, utc_now_iso
from .services.protein_generation import create_generated_structure
from .config import UPLOAD_DIR

BASE_DIR = Path(__file__).resolve().parent.parent
# UPLOAD_DIR = BASE_DIR / "uploads"
# UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Protein Design Information System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://molstar.org",
        "https://www.molstar.org",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

MAX_DIMA_LENGTH = 254


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "protein-design-system", "status": "ok"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}


@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, username=user.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    if crud.get_user_by_email(db, email=user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


@app.get("/users/me", response_model=schemas.User)
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.get("/projects/", response_model=List[schemas.Project])
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return crud.get_projects_by_user(db, current_user.id, skip, limit)


@app.post("/projects/", response_model=schemas.Project)
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return crud.create_project(db, project, current_user.id)


@app.get("/projects/{project_id}", response_model=schemas.Project)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = _get_project_or_404(db, project_id, current_user.id)
    return project


@app.put("/projects/{project_id}", response_model=schemas.Project)
def update_project(
    project_id: int,
    payload: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = _get_project_or_404(db, project_id, current_user.id)
    return crud.update_project(db, project, payload)


@app.delete("/projects/{project_id}", response_model=schemas.MessageResponse)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = _get_project_or_404(db, project_id, current_user.id)
    for structure in list(project.protein_structures):
        _delete_structure_file(structure.pdb_file_path)
    crud.delete_project(db, project)
    return {"status": "success", "detail": "Project deleted"}


@app.get("/projects/{project_id}/protein-structures/", response_model=List[schemas.ProteinStructure])
def list_project_structures(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_project_or_404(db, project_id, current_user.id)
    structures = crud.get_structures_by_project(db, project_id)
    for structure in structures:
        _refresh_structure_metadata_from_pdb(db, structure)
        structure.pdb_file_path = _normalize_public_path(structure.pdb_file_path)
    return structures


@app.post("/projects/{project_id}/generate-protein/", response_model=schemas.ProteinStructure)
def generate_protein(
    project_id: int,
    params: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_project_or_404(db, project_id, current_user.id)

    generation_params = _parse_generation_params(params)

    structure = create_generated_structure(
        db=db,
        project_id=project_id,
        generation_params=generation_params,
        name_prefix="DiMA",
    )

    structure.pdb_file_path = _normalize_public_path(structure.pdb_file_path)
    return structure

@app.post("/projects/{project_id}/generate-protein-async/", response_model=schemas.TaskResponse)
async def generate_protein_async_endpoint(
    project_id: int,
    params: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_project_or_404(db, project_id, current_user.id)
    generation_params = _parse_generation_params(params)

    try:
        from .celery_worker import celery

        task = celery.send_task(
            "generate_protein_async",
            args=[project_id, current_user.id, generation_params],
        )
        return {"task_id": task.id, "status": "queued"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Async generation queue is unavailable. Start Redis/Celery or use the synchronous generation endpoint.",
        )


@app.get("/tasks/{task_id}", response_model=schemas.TaskStatusResponse)
def get_task_status(task_id: str):
    if task_id.startswith("sync-"):
        return {"task_id": task_id, "status": "SUCCESS", "result": {"mode": "sync"}}

    try:
        from celery.result import AsyncResult
        from .celery_worker import celery

        result = AsyncResult(task_id, app=celery)
        payload = result.result if isinstance(result.result, dict) else None
        return {
            "task_id": task_id,
            "status": result.status,
            "result": payload,
        }
    except Exception:
        return {
            "task_id": task_id,
            "status": "UNAVAILABLE",
            "result": {"detail": "Celery is not configured on this environment"},
        }


@app.post("/projects/{project_id}/upload-protein/", response_model=schemas.ProteinStructure)
async def upload_protein(
    project_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_project_or_404(db, project_id, current_user.id)

    if not name.strip():
        raise HTTPException(status_code=400, detail="Structure name is required")

    filename = file.filename or ""
    if not filename.lower().endswith(".pdb"):
        raise HTTPException(status_code=400, detail="Only .pdb files are supported")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is too large (max 10 MB)")

    file_id = f"{uuid.uuid4()}.pdb"
    storage_path = UPLOAD_DIR / file_id
    storage_path.write_bytes(content)

    pdb_text = content.decode("utf-8", errors="ignore")
    fasta_sequence = extract_sequence_from_pdb(pdb_text)
    pdb_metrics = extract_pdb_metrics(pdb_text)
    uploaded_at = utc_now_iso()

    structure_data = schemas.ProteinStructureCreate(
        name=name.strip(),
        pdb_file_path=f"/uploads/{file_id}",
        fasta_sequence=fasta_sequence,
        generation_params={"source": "upload", "uploaded_at": uploaded_at},
        metrics=compact_dict({
            "upload_time": uploaded_at,
            "length": len(fasta_sequence) if fasta_sequence else None,
            "source": "upload",
            **pdb_metrics,
        }),
    )

    structure = crud.create_protein_structure(db, structure_data, project_id)
    structure.pdb_file_path = _normalize_public_path(structure.pdb_file_path)
    return structure


@app.get("/protein-structures/{structure_id}", response_model=schemas.ProteinStructure)
def get_protein_structure(
    structure_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    structure = _get_structure_or_404(db, structure_id, current_user.id)
    _refresh_structure_metadata_from_pdb(db, structure)
    structure.pdb_file_path = _normalize_public_path(structure.pdb_file_path)
    return structure


@app.delete("/protein-structures/{structure_id}", response_model=schemas.MessageResponse)
def delete_protein_structure(
    structure_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    structure = _get_structure_or_404(db, structure_id, current_user.id)
    _delete_structure_file(structure.pdb_file_path)
    crud.delete_structure(db, structure)
    return {"status": "success", "detail": "Protein structure deleted"}


def _get_project_or_404(db: Session, project_id: int, owner_id: int) -> models.Project:
    project = crud.get_project_by_id(db, project_id)
    if project is None or project.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_structure_or_404(db: Session, structure_id: int, owner_id: int) -> models.ProteinStructure:
    structure = crud.get_structure_by_id(db, structure_id)
    if structure is None:
        raise HTTPException(status_code=404, detail="Structure not found")

    project = crud.get_project_by_id(db, structure.project_id)
    if project is None or project.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Structure not found")

    return structure


def _parse_generation_params(params: str) -> Dict[str, object]:
    try:
        payload = json.loads(params)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON in generation params") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Generation params must be a JSON object")

    try:
        length = int(payload.get("length", 120))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Protein length must be a number") from exc

    raw_name = payload.get("name", "")
    name = str(raw_name).strip() if raw_name is not None else ""

    if length < 50 or length > MAX_DIMA_LENGTH:
        raise HTTPException(status_code=400, detail=f"Protein length must be between 50 and {MAX_DIMA_LENGTH}")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Structure name must be 100 characters or fewer")

    clean_payload = {
        "length": length,
        "created_at": utc_now_iso(),
    }
    if name:
        clean_payload["name"] = name
    return clean_payload


def _normalize_public_path(value: str) -> str:
    if value.startswith("/uploads/"):
        return value
    if value.startswith("uploads/"):
        return f"/{value}"
    filename = os.path.basename(value)
    return f"/uploads/{filename}"


def _resolve_storage_path(value: str) -> Path:
    if value.startswith("/uploads/"):
        return BASE_DIR / value.lstrip("/")
    if value.startswith("uploads/"):
        return BASE_DIR / value
    if os.path.isabs(value):
        return Path(value)
    return UPLOAD_DIR / value


def _delete_structure_file(path_value: str) -> None:
    try:
        storage_path = _resolve_storage_path(path_value)
        if storage_path.exists():
            storage_path.unlink()
    except Exception:
        # File cleanup should not block API response.
        return


def _refresh_structure_metadata_from_pdb(db: Session, structure: models.ProteinStructure) -> None:
    metrics = dict(structure.metrics or {})
    generation_params = dict(structure.generation_params or {})
    changed = _normalize_timestamp_fields(generation_params, ("created_at", "uploaded_at"))
    changed = _normalize_timestamp_fields(metrics, ("upload_time",)) or changed

    try:
        storage_path = _resolve_storage_path(structure.pdb_file_path)
        if not storage_path.exists():
            if changed:
                _save_structure_metadata(db, structure, metrics, generation_params)
            return
        pdb_text = storage_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        if changed:
            _save_structure_metadata(db, structure, metrics, generation_params)
        return

    sequence = extract_sequence_from_pdb(pdb_text)
    pdb_metrics = extract_pdb_metrics(pdb_text)

    if sequence and not structure.fasta_sequence:
        structure.fasta_sequence = sequence
        changed = True

    if sequence and not metrics.get("length"):
        metrics["length"] = len(sequence)
        changed = True

    for key, value in pdb_metrics.items():
        if value is None:
            continue
        if metrics.get(key) in (None, "", [], 0):
            metrics[key] = value
            changed = True

    if changed:
        _save_structure_metadata(db, structure, metrics, generation_params)


def _normalize_timestamp_fields(payload: Dict[str, object], keys: tuple[str, ...]) -> bool:
    changed = False
    for key in keys:
        if key not in payload:
            continue
        normalized = ensure_utc_iso(payload[key])
        if normalized != payload[key]:
            payload[key] = normalized
            changed = True
    return changed


def _save_structure_metadata(
    db: Session,
    structure: models.ProteinStructure,
    metrics: Dict[str, object],
    generation_params: Dict[str, object],
) -> None:
    structure.metrics = compact_dict(metrics)
    structure.generation_params = compact_dict(generation_params)
    db.add(structure)
    db.commit()
    db.refresh(structure)
