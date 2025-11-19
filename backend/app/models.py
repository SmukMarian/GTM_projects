"""Доменные модели Projects Tracker.

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


class TaskUrgency(str, Enum):
    NORMAL = "normal"
    HIGH = "high"


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
    value_ru: str | int | float | bool | None = None
    value_en: str | int | float | bool | None = None
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
    tasks: list["Task"] = Field(default_factory=list)


class TemplateFromProjectRequest(BaseModel):
    name: str
    description: str | None = None


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
    urgency: TaskUrgency = TaskUrgency.NORMAL
    gtm_stage_id: UUID | None = None
    subtasks: list[Subtask] = Field(default_factory=list)
    comments: list["Comment"] = Field(default_factory=list)


class SpotlightTask(BaseModel):
    """Краткая карточка задачи для сводки важности/срочности."""

    task_id: UUID
    title: str
    project_id: UUID
    project_name: str
    group_id: UUID
    group_name: str
    gtm_stage_id: UUID | None = None
    gtm_stage_title: str | None = None
    due_date: date | None = None
    due_in_days: int | None = None
    important: bool = False
    urgency: TaskUrgency = TaskUrgency.NORMAL
    status: TaskStatus = TaskStatus.TODO
    overdue: bool = False


class TaskSpotlightSummary(BaseModel):
    urgent_and_important: list[SpotlightTask] = Field(default_factory=list)
    important_only: list[SpotlightTask] = Field(default_factory=list)
    urgent_only: list[SpotlightTask] = Field(default_factory=list)


class Comment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    edited_at: datetime | None = None


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
    short_id: int | None = None
    group_id: UUID
    name: str
    brand: str
    market: str
    moq: float | None = None
    promo_price: float | None = None
    rrp_price: float | None = None
    fob_price: float | None = None
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


class StatusSummary(BaseModel):
    """Счётчики проектов по статусам для дашборда."""

    active: int = 0
    closed: int = 0
    archived: int = 0


class GroupDashboardCard(BaseModel):
    """Сводка по продуктовой группе на дашборде."""

    id: UUID
    name: str
    active_projects: int
    risk: bool


class BrandMetric(BaseModel):
    """Количество проектов по бренду."""

    brand: str
    projects: int


class GTMDistribution(BaseModel):
    """Распределение проектов по стадии прохождения GTM."""

    early: int = 0
    middle: int = 0
    late: int = 0
    none: int = 0


class RiskProject(BaseModel):
    """Проекты с рисками/просрочками."""

    project_id: UUID
    project_name: str
    group_name: str
    overdue_days: int
    reason: str


class DashboardKPI(BaseModel):
    """Ключевые показатели для дашборда."""

    total_projects: int = 0
    active: int = 0
    closed: int = 0
    archived: int = 0
    completion_rate: float = 0.0
    overdue_projects: int = 0
    overdue_rate: float = 0.0
    active_groups: int = 0
    risky_groups: int = 0


class UpcomingItem(BaseModel):
    """Ближайшая важная дата (этап или задача)."""

    project_id: UUID
    project_name: str
    group_name: str
    kind: str
    title: str
    planned_date: date
    days_delta: int
    risk: bool = False


class RecentChange(BaseModel):
    """Элемент ленты последних изменений."""

    project_id: UUID
    project_name: str
    group_name: str
    occurred_at: datetime
    summary: str
    details: str | None = None


class DashboardPayload(BaseModel):
    """Комплексные данные для главного дашборда."""

    statuses: StatusSummary
    groups: list[GroupDashboardCard]
    kpis: DashboardKPI
    brands: list[BrandMetric]
    gtm_distribution: GTMDistribution
    risk_projects: list[RiskProject]
    upcoming: list[UpcomingItem]
    recent_changes: list[RecentChange]

