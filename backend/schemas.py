from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=5, max_length=100)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return _utc_iso(value)


class Token(BaseModel):
    access_token: str
    token_type: str


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default="", max_length=2000)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)


class Project(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_datetimes(self, value: datetime) -> str:
        return _utc_iso(value)


class ProteinStructureBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    pdb_file_path: str
    fasta_sequence: Optional[str] = None
    generation_params: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None


class ProteinStructureCreate(ProteinStructureBase):
    pass


class ProteinStructure(ProteinStructureBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return _utc_iso(value)


class MessageResponse(BaseModel):
    status: str
    detail: str


class TaskResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
