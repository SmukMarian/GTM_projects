"""Доменные модели Haier Project Tracker.

Файл задаёт Pydantic-модели и перечисления, соответствующие сущностям
из `Haier_Project_Tracker_TZ.md`. Модели служат единым контрактом между
слоями приложения и помогают валидировать входящие данные.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class GroupStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class PriorityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
    OTHER = "other"


class Timestamped(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None


class ProductGroup(Timestamped):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    status: GroupStatus = GroupStatus.ACTIVE
    brands: list[str] = Field(default_factory=list)
    extra_fields: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CharacteristicField(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    label_ru: str
    label_en: str
    value_ru: str | None = None
    value_en: str | None = None
    field_type: FieldType = FieldType.TEXT
    order: int = 0


class CharacteristicSection(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    order: int = 0
    fields: list[CharacteristicField] = Field(default_factory=list)


class CharacteristicTemplate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    sections: list[CharacteristicSection] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    done: bool = False
    order: int = 0


class GTMStage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str | None = None
    order: int = 0
    planned_start: date | None = None
    planned_end: date | None = None
    actual_end: date | None = None
    status: StageStatus = StageStatus.NOT_STARTED
    risk_flag: bool = False
    checklist: list[ChecklistItem] = Field(default_factory=list)


class GTMTemplate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    stages: list[GTMStage] = Field(default_factory=list)


class Subtask(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    done: bool = False
    order: int = 0


class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    due_date: date | None = None
    important: bool = False
    gtm_stage_id: UUID | None = None
    subtasks: list[Subtask] = Field(default_factory=list)
    comments: list["Comment"] = Field(default_factory=list)


class Comment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FileAttachment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    category: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    path: Path


class ImageAttachment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    filename: str
    caption: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    order: int = 0
    is_cover: bool = False
    path: Path


class HistoryEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    details: str | None = None


class BackupInfo(BaseModel):
    """Данные о файле резервной копии."""

    file_name: str
    created_at: datetime


class BackupRestoreRequest(BaseModel):
    """Запрос на восстановление из резервной копии."""

    file_name: str


class Project(Timestamped):
    id: UUID = Field(default_factory=uuid4)
    group_id: UUID
    name: str
    brand: str
    market: str
    short_description: str | None = None
    full_description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    current_gtm_stage_id: UUID | None = None
    planned_launch: date | None = None
    actual_launch: date | None = None
    priority: PriorityLevel | None = None
    custom_fields: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    gtm_stages: list[GTMStage] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    characteristics: list[CharacteristicSection] = Field(default_factory=list)
    files: list[FileAttachment] = Field(default_factory=list)
    images: list[ImageAttachment] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)


class ProjectExport(BaseModel):
    """Упрощённая модель для экспорта списка проектов."""

    name: str
    group_name: str
    brand: str
    status: ProjectStatus
    planned_launch: date | None = None
    current_gtm_stage: str | None = None

