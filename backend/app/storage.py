"""Локальное файловое хранилище для Projects Tracker.

Слой отвечает за загрузку и сохранение доменных моделей в один JSON-файл,
что соответствует требованию ТЗ о локальной работе и возможности ручного
копирования базы. Предоставляет минимальный репозиторий для работы с
продуктовыми группами и проектами; по мере развития интерфейса он будет
расширяться другими операциями.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .exporters import import_characteristics_from_excel as parse_characteristics_from_excel
from .models import (
    BackupInfo,
    BrandMetric,
    CharacteristicField,
    CharacteristicFlatRecord,
    CharacteristicSection,
    CharacteristicTemplate,
    Comment,
    CustomFieldOption,
    CustomFieldFilterMeta,
    CustomFieldFilterRequest,
    DashboardKPI,
    DashboardPayload,
    FileAttachment,
    GTMDistribution,
    GTMStage,
    GTMTemplate,
    GroupDashboardCard,
    GroupStatus,
    HistoryEvent,
    ImageAttachment,
    ProductGroup,
    Project,
    ProjectStatus,
    RecentChange,
    RiskProject,
    SpotlightTask,
    StageStatus,
    StatusSummary,
    Subtask,
    Task,
    TaskSpotlightSummary,
    TaskStatus,
    TaskUrgency,
    UpcomingItem,
)


class DataStore(BaseModel):
    """Основная структура данных, сохраняемая на диск."""

    product_groups: list[ProductGroup] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    gtm_templates: list[GTMTemplate] = Field(default_factory=list)
    characteristic_templates: list[CharacteristicTemplate] = Field(default_factory=list)
    next_project_short_id: int = 1

    model_config = ConfigDict(arbitrary_types_allowed=True, json_encoders={Path: str})


def _write_json(path: Path, store: DataStore) -> None:
    path.write_text(store.model_dump_json(indent=2, exclude_none=True, by_alias=False), encoding="utf-8")


def load_store(path: Path) -> DataStore:
    """Загрузить хранилище из файла; если файл отсутствует — вернуть пустую структуру."""

    if path.exists():
        return DataStore.model_validate_json(path.read_text(encoding="utf-8"))
    return DataStore()


def _normalize_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "да", "on"}:
            return True
        if lowered in {"false", "0", "no", "нет", "off"}:
            return False
    return None


def _normalize_number(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _normalize_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _detect_field_type(values: list) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "text"
    if all(isinstance(v, bool) for v in non_null):
        return "checkbox"
    if all(isinstance(v, (int, float)) for v in non_null):
        return "number"
    if all(_normalize_date(v) for v in non_null):
        return "date"
    if all(isinstance(v, str) for v in non_null):
        unique = {v for v in non_null if v != ""}
        if 1 < len(unique) <= 8:
            return "select"
    return "text"


def _build_custom_field_meta(items, field_accessor, *, counter_key: str) -> list[CustomFieldFilterMeta]:
    values_by_field: dict[str, list] = {}
    counts: Counter[str] = Counter()
    for item in items:
        fields = field_accessor(item) or {}
        for key, value in fields.items():
            counts[key] += 1
            values_by_field.setdefault(key, []).append(value)

    metas: list[CustomFieldFilterMeta] = []
    for key, count in counts.items():
        if count <= 1:
            continue
        values = values_by_field.get(key, [])
        field_type = _detect_field_type(values)
        options = None
        if field_type == "checkbox":
            # Boolean options implicit; keep options None.
            options = None
        elif field_type == "select":
            freq = Counter(str(v) for v in values if v not in (None, ""))
            options = [
                CustomFieldOption(value=val, count=cnt)
                for val, cnt in sorted(freq.items(), key=lambda x: x[0])
            ]
        meta_kwargs = {
            "field_id": key,
            "label_ru": key,
            "label_en": key,
            "type": field_type,
            "options": options,
            f"{counter_key}_count": count,
        }
        metas.append(CustomFieldFilterMeta(**meta_kwargs))
    metas.sort(key=lambda m: m.label_ru.lower())
    return metas


def _matches_filter(fields: dict[str, object], flt: CustomFieldFilterRequest) -> bool:
    if flt.type == "text":
        if not flt.value:
            return True
        value = fields.get(flt.field_id)
        return value is not None and str(value).lower().find(flt.value.lower()) != -1

    if flt.type == "number":
        target = _normalize_number(fields.get(flt.field_id))
        if target is None:
            return flt.value_from is None and flt.value_to is None
        if flt.value_from is not None and target < flt.value_from:
            return False
        if flt.value_to is not None and target > flt.value_to:
            return False
        return True

    if flt.type in {"select", "enum"}:
        if not flt.values:
            return True
        value = fields.get(flt.field_id)
        return value is not None and str(value) in set(flt.values)

    if flt.type in {"checkbox", "boolean"}:
        if flt.bool_value is None:
            return True
        value = _normalize_bool(fields.get(flt.field_id))
        return value is not None and value is flt.bool_value

    if flt.type == "date":
        target = _normalize_date(fields.get(flt.field_id))
        if target is None:
            return flt.date_from is None and flt.date_to is None
        if flt.date_from and target < flt.date_from:
            return False
        if flt.date_to and target > flt.date_to:
            return False
        return True

    # Fallback for unknown types: string contains
    if flt.value:
        value = fields.get(flt.field_id)
        return value is not None and str(value).lower().find(flt.value.lower()) != -1
    return True


def _filter_by_custom_fields(items, filters: list[CustomFieldFilterRequest] | None, *, field_accessor):
    if not filters:
        return list(items)
    active = [f for f in filters if f is not None]
    filtered = list(items)
    for flt in active:
        filtered = [item for item in filtered if _matches_filter(field_accessor(item), flt)]
    return filtered


class LocalRepository:
    """Простейший репозиторий поверх JSON-файла."""

    def __init__(self, path: Path):
        self.path = path
        self.store = load_store(path)
        self._ensure_project_short_ids()

    def save(self) -> None:
        _write_json(self.path, self.store)

    def _ensure_project_short_ids(self) -> None:
        """Назначить короткие ID проектам, у которых они отсутствуют."""

        max_id = max((p.short_id or 0 for p in self.store.projects), default=0)
        counter = max(self.store.next_project_short_id, max_id + 1)
        changed = False
        for project in self.store.projects:
            if project.short_id is None:
                project.short_id = counter
                counter += 1
                changed = True
        if counter != self.store.next_project_short_id:
            self.store.next_project_short_id = counter
            changed = True
        if changed:
            self.save()

    # --- Product groups ---
    def list_groups(
        self,
        include_archived: bool = True,
        *,
        brand: str | None = None,
        statuses: set[GroupStatus] | None = None,
        extra_key: str | None = None,
        extra_value: str | None = None,
        filters: list[CustomFieldFilterRequest] | None = None,
    ) -> list[ProductGroup]:
        groups: Iterable[ProductGroup] = self.store.product_groups
        if not include_archived:
            groups = [g for g in groups if g.status.value != "archived"]
        if brand:
            lowered = brand.lower()
            groups = [g for g in groups if any(lowered in b.lower() for b in g.brands)]
        if statuses:
            groups = [g for g in groups if g.status in statuses]
        if extra_key:
            key = extra_key.strip()
            groups = [g for g in groups if key in g.extra_fields]
            if extra_value:
                value_lower = extra_value.lower()
                groups = [
                    g
                    for g in groups
                    if str(g.extra_fields.get(key, "")).lower().find(value_lower) != -1
                ]
        groups = _filter_by_custom_fields(groups, filters, field_accessor=lambda g: g.extra_fields)
        return list(groups)

    def get_group(self, group_id: UUID) -> ProductGroup | None:
        for group in self.store.product_groups:
            if group.id == group_id:
                return group
        return None

    def add_group(self, group: ProductGroup) -> ProductGroup:
        self.store.product_groups.append(group)
        self.save()
        return group

    def update_group(self, group_id, updated: ProductGroup) -> ProductGroup:
        for idx, group in enumerate(self.store.product_groups):
            if group.id == group_id:
                self.store.product_groups[idx] = updated
                self.save()
                return updated
        raise KeyError(f"Group {group_id} not found")

    def delete_group(self, group_id: UUID) -> None:
        for idx, group in enumerate(self.store.product_groups):
            if group.id == group_id:
                self.store.product_groups.pop(idx)
                self.save()
                return
        raise KeyError(f"Group {group_id} not found")

    def has_projects_for_group(self, group_id: UUID) -> bool:
        return any(project.group_id == group_id for project in self.store.projects)

    # --- Projects ---
    def list_projects(
        self,
        *,
        include_archived: bool = True,
        group_id: UUID | None = None,
        statuses: set[ProjectStatus] | None = None,
        brand: str | None = None,
        current_stage_id: UUID | None = None,
        planned_from: date | None = None,
        planned_to: date | None = None,
        filters: list[CustomFieldFilterRequest] | None = None,
    ) -> list[Project]:
        projects: Iterable[Project] = self.store.projects
        if not include_archived:
            projects = [p for p in projects if p.status != ProjectStatus.ARCHIVED]
        if group_id:
            projects = [p for p in projects if p.group_id == group_id]
        if statuses:
            projects = [p for p in projects if p.status in statuses]
        if brand:
            projects = [p for p in projects if p.brand.lower() == brand.lower()]
        if current_stage_id:
            projects = [p for p in projects if p.current_gtm_stage_id == current_stage_id]
        if planned_from:
            projects = [
                p
                for p in projects
                if p.planned_launch is not None and p.planned_launch >= planned_from
            ]
        if planned_to:
            projects = [
                p
                for p in projects
                if p.planned_launch is not None and p.planned_launch <= planned_to
            ]
        projects = _filter_by_custom_fields(projects, filters, field_accessor=lambda p: p.custom_fields)
        return list(projects)

    def list_project_filter_meta(self) -> list[CustomFieldFilterMeta]:
        return _build_custom_field_meta(
            self.store.projects, field_accessor=lambda p: p.custom_fields, counter_key="projects"
        )

    def list_group_filter_meta(self) -> list[CustomFieldFilterMeta]:
        return _build_custom_field_meta(
            self.store.product_groups, field_accessor=lambda g: g.extra_fields, counter_key="groups"
        )

    def get_project(self, project_id: UUID) -> Project | None:
        for project in self.store.projects:
            if project.id == project_id:
                return project
        return None

    def add_project(self, project: Project) -> Project:
        if project.short_id is None:
            project.short_id = self.store.next_project_short_id
            self.store.next_project_short_id += 1
        self.store.projects.append(project)
        self.save()
        return project

    def update_project(self, project_id, updated: Project) -> Project:
        for idx, project in enumerate(self.store.projects):
            if project.id == project_id:
                if updated.short_id is None:
                    updated = updated.model_copy(update={"short_id": project.short_id})
                self.store.projects[idx] = updated
                self.save()
                return updated
        raise KeyError(f"Project {project_id} not found")

    def delete_project(self, project_id: UUID) -> None:
        for idx, project in enumerate(self.store.projects):
            if project.id == project_id:
                self.store.projects.pop(idx)
                self.save()
                return
        raise KeyError(f"Project {project_id} not found")

    def import_projects(self, projects: list[Project]) -> list[Project]:
        """Импортировать или обновить список проектов из Excel."""

        existing_map = {p.id: idx for idx, p in enumerate(self.store.projects)}
        updated_projects = list(self.store.projects)

        for project in projects:
            if project.id in existing_map:
                idx = existing_map[project.id]
                updated_projects[idx] = project
            else:
                if project.short_id is None:
                    project.short_id = self.store.next_project_short_id
                    self.store.next_project_short_id += 1
                updated_projects.append(project)

        self.store.projects = updated_projects
        self._ensure_project_short_ids()
        self.save()
        return updated_projects

    def replace_project(self, project_id: UUID, updated: Project) -> Project:
        for idx, project in enumerate(self.store.projects):
            if project.id == project_id:
                if updated.short_id is None:
                    updated = updated.model_copy(update={"short_id": project.short_id})
                self.store.projects[idx] = updated.model_copy(update={"id": project_id})
                self.save()
                return updated
        raise KeyError(f"Project {project_id} not found")

    def _get_project_with_index(self, project_id: UUID) -> tuple[int, Project]:
        for idx, project in enumerate(self.store.projects):
            if project.id == project_id:
                return idx, project
        raise KeyError(f"Project {project_id} not found")

    def _get_characteristic_section_with_index(
        self, project: Project, section_id: UUID
    ) -> tuple[int, CharacteristicSection]:
        for idx, section in enumerate(project.characteristics):
            if section.id == section_id:
                return idx, section
        raise KeyError(f"Characteristic section {section_id} not found")

    def _get_task_with_index(self, project: Project, task_id: UUID) -> tuple[int, Task]:
        for idx, task in enumerate(project.tasks):
            if task.id == task_id:
                return idx, task
        raise KeyError(f"Task {task_id} not found")

    # --- GTM templates ---
    def list_gtm_templates(self) -> list[GTMTemplate]:
        return list(self.store.gtm_templates)

    def get_gtm_template(self, template_id: UUID) -> GTMTemplate | None:
        for template in self.store.gtm_templates:
            if template.id == template_id:
                return template
        return None

    def add_gtm_template(self, template: GTMTemplate) -> GTMTemplate:
        self.store.gtm_templates.append(template)
        self.save()
        return template

    def update_gtm_template(self, template_id: UUID, updated: GTMTemplate) -> GTMTemplate:
        for idx, template in enumerate(self.store.gtm_templates):
            if template.id == template_id:
                self.store.gtm_templates[idx] = updated
                self.save()
                return updated
        raise KeyError(f"GTM template {template_id} not found")

    def delete_gtm_template(self, template_id: UUID) -> None:
        for idx, template in enumerate(self.store.gtm_templates):
            if template.id == template_id:
                self.store.gtm_templates.pop(idx)
                self.save()
                return
        raise KeyError(f"GTM template {template_id} not found")

    # --- Characteristic templates ---
    def list_characteristic_templates(self) -> list[CharacteristicTemplate]:
        return list(self.store.characteristic_templates)

    def get_characteristic_template(self, template_id: UUID) -> CharacteristicTemplate | None:
        for template in self.store.characteristic_templates:
            if template.id == template_id:
                return template
        return None

    def add_characteristic_template(self, template: CharacteristicTemplate) -> CharacteristicTemplate:
        self.store.characteristic_templates.append(template)
        self.save()
        return template

    def update_characteristic_template(
        self, template_id: UUID, updated: CharacteristicTemplate
    ) -> CharacteristicTemplate:
        for idx, template in enumerate(self.store.characteristic_templates):
            if template.id == template_id:
                self.store.characteristic_templates[idx] = updated
                self.save()
                return updated
        raise KeyError(f"Characteristic template {template_id} not found")

    def delete_characteristic_template(self, template_id: UUID) -> None:
        for idx, template in enumerate(self.store.characteristic_templates):
            if template.id == template_id:
                self.store.characteristic_templates.pop(idx)
                self.save()
                return
        raise KeyError(f"Characteristic template {template_id} not found")

    # --- GTM stages inside projects ---
    def list_gtm_stages(self, project_id: UUID) -> list[GTMStage]:
        project = self.get_project(project_id)
        if not project:
            raise KeyError(f"Project {project_id} not found")
        return list(project.gtm_stages)

    def add_gtm_stage(self, project_id: UUID, stage: GTMStage) -> GTMStage:
        for idx, project in enumerate(self.store.projects):
            if project.id == project_id:
                if stage.order == 0 and project.gtm_stages:
                    stage = stage.model_copy(update={"order": len(project.gtm_stages)})
                project.gtm_stages.append(stage)
                self.store.projects[idx] = project
                self.save()
                return stage
        raise KeyError(f"Project {project_id} not found")

    def update_gtm_stage(self, project_id: UUID, stage_id: UUID, updated: GTMStage) -> GTMStage:
        for p_idx, project in enumerate(self.store.projects):
            if project.id != project_id:
                continue
            for s_idx, stage in enumerate(project.gtm_stages):
                if stage.id == stage_id:
                    project.gtm_stages[s_idx] = updated
                    self.store.projects[p_idx] = project
                    self.save()
                    return updated
            raise KeyError(f"Stage {stage_id} not found in project {project_id}")
        raise KeyError(f"Project {project_id} not found")

    def delete_gtm_stage(self, project_id: UUID, stage_id: UUID) -> None:
        for p_idx, project in enumerate(self.store.projects):
            if project.id != project_id:
                continue
            for s_idx, stage in enumerate(project.gtm_stages):
                if stage.id == stage_id:
                    project.gtm_stages.pop(s_idx)
                    self.store.projects[p_idx] = project
                    self.save()
                    return
            raise KeyError(f"Stage {stage_id} not found in project {project_id}")
        raise KeyError(f"Project {project_id} not found")

    def apply_gtm_template(self, project_id: UUID, template_id: UUID) -> list[GTMStage]:
        template = self.get_gtm_template(template_id)
        if template is None:
            raise KeyError(f"GTM template {template_id} not found")

        for p_idx, project in enumerate(self.store.projects):
            if project.id == project_id:
                stage_id_map: dict[UUID, UUID] = {}

                def clone_stage(stage: GTMStage) -> GTMStage:
                    cloned_id = uuid4()
                    stage_id_map[stage.id] = cloned_id
                    cloned_checklist = [
                        item.model_copy(update={"id": uuid4(), "done": False})
                        for item in sorted(stage.checklist, key=lambda c: c.order)
                    ]
                    return stage.model_copy(
                        update={
                            "id": cloned_id,
                            "planned_start": None,
                            "planned_end": None,
                            "actual_end": None,
                            "status": StageStatus.NOT_STARTED,
                            "risk_flag": False,
                            "checklist": cloned_checklist,
                        }
                    )

                new_stages = [clone_stage(stage) for stage in sorted(template.stages, key=lambda s: s.order)]

                def clone_task(task: Task) -> Task:
                    if task.gtm_stage_id not in stage_id_map:
                        raise KeyError(f"Stage {task.gtm_stage_id} from template not found in cloned stages")

                    cloned_subtasks = [
                        sub.model_copy(update={"id": uuid4(), "done": False})
                        for sub in sorted(task.subtasks, key=lambda s: s.order)
                    ]
                    return task.model_copy(
                        update={
                            "id": uuid4(),
                            "gtm_stage_id": stage_id_map[task.gtm_stage_id],
                            "status": TaskStatus.TODO,
                            "due_date": None,
                            "subtasks": cloned_subtasks,
                            "comments": [],
                        }
                    )

                new_tasks = [clone_task(task) for task in template.tasks]

                project.gtm_stages = new_stages
                project.tasks = new_tasks
                self.store.projects[p_idx] = project
                self.save()
                return new_stages
        raise KeyError(f"Project {project_id} not found")

    def replace_gtm_stages(
        self, project_id: UUID, stages: list[GTMStage], tasks: list[Task] | None = None
    ) -> list[GTMStage]:
        for p_idx, project in enumerate(self.store.projects):
            if project.id != project_id:
                continue
            project.gtm_stages = stages
            if tasks is not None:
                project.tasks = tasks
            self.store.projects[p_idx] = project
            self.save()
            return stages
        raise KeyError(f"Project {project_id} not found")

    def create_gtm_template_from_project(self, project_id: UUID, name: str, description: str | None = None) -> GTMTemplate:
        for project in self.store.projects:
            if project.id != project_id:
                continue

            stage_id_map: dict[UUID, UUID] = {}

            def clone_stage(stage: GTMStage) -> GTMStage:
                cloned_id = uuid4()
                stage_id_map[stage.id] = cloned_id
                cloned_checklist = [
                    item.model_copy(update={"id": uuid4(), "done": False}) for item in sorted(stage.checklist, key=lambda c: c.order)
                ]
                return stage.model_copy(
                    update={
                        "id": cloned_id,
                        "planned_start": None,
                        "planned_end": None,
                        "actual_end": None,
                        "status": StageStatus.NOT_STARTED,
                        "risk_flag": False,
                        "checklist": cloned_checklist,
                    }
                )

            cloned_stages = [clone_stage(stage) for stage in sorted(project.gtm_stages, key=lambda s: s.order)]

            def clone_task(task: Task) -> Task:
                if task.gtm_stage_id not in stage_id_map:
                    return None  # skip tasks без этапа
                cloned_subtasks = [
                    sub.model_copy(update={"id": uuid4(), "done": False})
                    for sub in sorted(task.subtasks, key=lambda s: s.order)
                ]
                return task.model_copy(
                    update={
                        "id": uuid4(),
                        "gtm_stage_id": stage_id_map[task.gtm_stage_id],
                        "status": TaskStatus.TODO,
                        "due_date": None,
                        "subtasks": cloned_subtasks,
                        "comments": [],
                    }
                )

            cloned_tasks = [t for t in (clone_task(task) for task in project.tasks) if t is not None]
            template = GTMTemplate(name=name, description=description, stages=cloned_stages, tasks=cloned_tasks)
            self.store.gtm_templates.append(template)
            self.save()
            return template

        raise KeyError(f"Project {project_id} not found")

    # --- Tasks ---
    def list_tasks(
        self,
        project_id: UUID,
        *,
        statuses: set[TaskStatus] | None = None,
        only_active: bool = False,
        gtm_stage_id: UUID | None = None,
    ) -> list[Task]:
        _, project = self._get_project_with_index(project_id)
        tasks: Iterable[Task] = project.tasks
        if statuses:
            tasks = [t for t in tasks if t.status in statuses]
        if only_active:
            tasks = [t for t in tasks if t.status != TaskStatus.DONE]
        if gtm_stage_id:
            tasks = [t for t in tasks if t.gtm_stage_id == gtm_stage_id]
        return list(tasks)

    def add_task(self, project_id: UUID, task: Task) -> Task:
        p_idx, project = self._get_project_with_index(project_id)
        if task.gtm_stage_id is None:
            raise ValueError("gtm_stage_required")
        if not any(stage.id == task.gtm_stage_id for stage in project.gtm_stages):
            raise ValueError("gtm_stage_missing")
        project.tasks.append(task)
        self.store.projects[p_idx] = project
        self.save()
        return task

    def update_task(self, project_id: UUID, task_id: UUID, updated: Task) -> Task:
        p_idx, project = self._get_project_with_index(project_id)
        if updated.gtm_stage_id is None:
            raise ValueError("gtm_stage_required")
        if not any(stage.id == updated.gtm_stage_id for stage in project.gtm_stages):
            raise ValueError("gtm_stage_missing")
        for t_idx, task in enumerate(project.tasks):
            if task.id == task_id:
                project.tasks[t_idx] = updated
                self.store.projects[p_idx] = project
                self.save()
                return updated
        raise KeyError(f"Task {task_id} not found in project {project_id}")

    def delete_task(self, project_id: UUID, task_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        for t_idx, task in enumerate(project.tasks):
            if task.id == task_id:
                project.tasks.pop(t_idx)
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"Task {task_id} not found in project {project_id}")

    # --- Subtasks ---
    def add_subtask(self, project_id: UUID, task_id: UUID, subtask: Subtask) -> Subtask:
        p_idx, project = self._get_project_with_index(project_id)
        for t_idx, task in enumerate(project.tasks):
            if task.id == task_id:
                if subtask.order == 0 and task.subtasks:
                    subtask = subtask.model_copy(update={"order": len(task.subtasks)})
                task.subtasks.append(subtask)
                project.tasks[t_idx] = task
                self.store.projects[p_idx] = project
                self.save()
                return subtask
        raise KeyError(f"Task {task_id} not found in project {project_id}")

    def update_subtask(self, project_id: UUID, task_id: UUID, subtask_id: UUID, updated: Subtask) -> Subtask:
        p_idx, project = self._get_project_with_index(project_id)
        for t_idx, task in enumerate(project.tasks):
            if task.id != task_id:
                continue
            for s_idx, subtask in enumerate(task.subtasks):
                if subtask.id == subtask_id:
                    task.subtasks[s_idx] = updated
                    project.tasks[t_idx] = task
                    self.store.projects[p_idx] = project
                    self.save()
                    return updated
            raise KeyError(f"Subtask {subtask_id} not found in task {task_id}")
        raise KeyError(f"Task {task_id} not found in project {project_id}")

    def delete_subtask(self, project_id: UUID, task_id: UUID, subtask_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        for t_idx, task in enumerate(project.tasks):
            if task.id != task_id:
                continue
            for s_idx, subtask in enumerate(task.subtasks):
                if subtask.id == subtask_id:
                    task.subtasks.pop(s_idx)
                    project.tasks[t_idx] = task
                    self.store.projects[p_idx] = project
                    self.save()
                    return
            raise KeyError(f"Subtask {subtask_id} not found in task {task_id}")
        raise KeyError(f"Task {task_id} not found in project {project_id}")

    # --- Characteristics inside projects ---
    def list_characteristic_sections(self, project_id: UUID) -> list[CharacteristicSection]:
        _, project = self._get_project_with_index(project_id)
        return list(project.characteristics)

    def add_characteristic_section(self, project_id: UUID, section: CharacteristicSection) -> CharacteristicSection:
        p_idx, project = self._get_project_with_index(project_id)
        if section.order == 0 and project.characteristics:
            section = section.model_copy(update={"order": len(project.characteristics)})
        project.characteristics.append(section)
        self.store.projects[p_idx] = project
        self.save()
        return section

    def update_characteristic_section(
        self, project_id: UUID, section_id: UUID, updated: CharacteristicSection
    ) -> CharacteristicSection:
        p_idx, project = self._get_project_with_index(project_id)
        s_idx, _ = self._get_characteristic_section_with_index(project, section_id)
        project.characteristics[s_idx] = updated
        self.store.projects[p_idx] = project
        self.save()
        return updated

    def delete_characteristic_section(self, project_id: UUID, section_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        s_idx, _ = self._get_characteristic_section_with_index(project, section_id)
        project.characteristics.pop(s_idx)
        self.store.projects[p_idx] = project
        self.save()

    def add_characteristic_field(
        self, project_id: UUID, section_id: UUID, field: CharacteristicField
    ) -> CharacteristicField:
        p_idx, project = self._get_project_with_index(project_id)
        s_idx, section = self._get_characteristic_section_with_index(project, section_id)
        if field.order == 0 and section.fields:
            field = field.model_copy(update={"order": len(section.fields)})
        section.fields.append(field)
        project.characteristics[s_idx] = section
        self.store.projects[p_idx] = project
        self.save()
        return field

    def update_characteristic_field(
        self, project_id: UUID, section_id: UUID, field_id: UUID, updated: CharacteristicField
    ) -> CharacteristicField:
        p_idx, project = self._get_project_with_index(project_id)
        s_idx, section = self._get_characteristic_section_with_index(project, section_id)
        for f_idx, field in enumerate(section.fields):
            if field.id == field_id:
                section.fields[f_idx] = updated
                project.characteristics[s_idx] = section
                self.store.projects[p_idx] = project
                self.save()
                return updated
        raise KeyError(f"Field {field_id} not found in section {section_id}")

    def delete_characteristic_field(self, project_id: UUID, section_id: UUID, field_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        s_idx, section = self._get_characteristic_section_with_index(project, section_id)
        for f_idx, field in enumerate(section.fields):
            if field.id == field_id:
                section.fields.pop(f_idx)
                project.characteristics[s_idx] = section
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"Field {field_id} not found in section {section_id}")

    def apply_characteristic_template(
        self, project_id: UUID, template_id: UUID
    ) -> list[CharacteristicSection]:
        template = self.get_characteristic_template(template_id)
        if template is None:
            raise KeyError(f"Characteristic template {template_id} not found")

        p_idx, project = self._get_project_with_index(project_id)
        new_sections: list[CharacteristicSection] = []
        for section in template.sections:
            new_fields = [
                field.model_copy(update={"id": uuid4(), "value_ru": None, "value_en": None})
                for field in section.fields
            ]
            new_sections.append(section.model_copy(update={"id": uuid4(), "fields": new_fields}))
        project.characteristics = new_sections
        self.store.projects[p_idx] = project
        self.save()
        return new_sections

    def copy_characteristics_structure(
        self, project_id: UUID, source_project_id: UUID
    ) -> list[CharacteristicSection]:
        _, source_project = self._get_project_with_index(source_project_id)
        p_idx, target_project = self._get_project_with_index(project_id)

        new_sections: list[CharacteristicSection] = []
        for section in source_project.characteristics:
            new_fields = [
                field.model_copy(update={"id": uuid4(), "value_ru": None, "value_en": None})
                for field in section.fields
            ]
            new_sections.append(section.model_copy(update={"id": uuid4(), "fields": new_fields}))

        target_project.characteristics = new_sections
        self.store.projects[p_idx] = target_project
        self.save()
        return new_sections

    def import_characteristics_from_excel(
        self, project_id: UUID, content: bytes
    ) -> tuple[list[CharacteristicSection], list[str], dict[str, int]]:
        p_idx, project = self._get_project_with_index(project_id)
        sections, errors, report = parse_characteristics_from_excel(content, project)
        if errors:
            return [], errors, report

        project.characteristics = sections
        self.store.projects[p_idx] = project
        self.save()
        return sections, [], report

    def list_characteristics_overview(
        self, *, group_id: UUID | None = None, query: str | None = None
    ) -> list[CharacteristicFlatRecord]:
        records: list[CharacteristicFlatRecord] = []
        group_lookup = {g.id: g.name for g in self.store.product_groups}
        normalized_query = query.strip().lower() if query else None

        for project in self.store.projects:
            if group_id and project.group_id != group_id:
                continue
            group_name = group_lookup.get(project.group_id)
            for section in project.characteristics:
                for field in section.fields:
                    haystack = " ".join(
                        [
                            section.title or "",
                            field.label_ru or "",
                            field.label_en or "",
                            str(field.value_ru or ""),
                            str(field.value_en or ""),
                            project.name or "",
                            group_name or "",
                        ]
                    ).lower()
                    if normalized_query and normalized_query not in haystack:
                        continue
                    records.append(
                        CharacteristicFlatRecord(
                            project_id=project.id,
                            project_name=project.name,
                            group_name=group_name,
                            section=section.title,
                            label_ru=field.label_ru,
                            label_en=field.label_en,
                            value_ru=field.value_ru,
                            value_en=field.value_en,
                            field_type=field.field_type,
                        )
                    )

        return records

    def apply_characteristics_bulk(self, updates: dict[UUID, list[CharacteristicSection]]) -> None:
        if not updates:
            return
        for idx, project in enumerate(self.store.projects):
            if project.id not in updates:
                continue
            project.characteristics = updates[project.id]
            self.store.projects[idx] = project
        self.save()

    # --- Files ---
    def list_files(self, project_id: UUID) -> list[FileAttachment]:
        _, project = self._get_project_with_index(project_id)
        return list(project.files)

    def add_file(self, project_id: UUID, file: FileAttachment) -> FileAttachment:
        p_idx, project = self._get_project_with_index(project_id)
        project.files.append(file)
        self.store.projects[p_idx] = project
        self.save()
        return file

    def update_file(self, project_id: UUID, file_id: UUID, updated: FileAttachment) -> FileAttachment:
        p_idx, project = self._get_project_with_index(project_id)
        for f_idx, file in enumerate(project.files):
            if file.id == file_id:
                project.files[f_idx] = updated
                self.store.projects[p_idx] = project
                self.save()
                return updated
        raise KeyError(f"File {file_id} not found in project {project_id}")

    def delete_file(self, project_id: UUID, file_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        for f_idx, file in enumerate(project.files):
            if file.id == file_id:
                project.files.pop(f_idx)
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"File {file_id} not found in project {project_id}")

    # --- Images ---
    def list_images(self, project_id: UUID) -> list[ImageAttachment]:
        _, project = self._get_project_with_index(project_id)
        return list(project.images)

    def _normalize_cover(self, project: Project, cover_image_id: UUID | None) -> None:
        if cover_image_id is None:
            return
        for img in project.images:
            if img.id != cover_image_id and img.is_cover:
                img.is_cover = False

    def clear_cover(self, project_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        changed = False
        for img in project.images:
            if img.is_cover:
                img.is_cover = False
                changed = True
        if changed:
            self.store.projects[p_idx] = project
            self.save()
        else:
            # Сохраняем порядок даже если обложка не была задана
            self.store.projects[p_idx] = project

    def add_image(self, project_id: UUID, image: ImageAttachment) -> ImageAttachment:
        p_idx, project = self._get_project_with_index(project_id)
        if image.order == 0 and project.images:
            image = image.model_copy(update={"order": len(project.images)})
        project.images.append(image)
        self._normalize_cover(project, image.id if image.is_cover else None)
        self.store.projects[p_idx] = project
        self.save()
        return image

    def update_image(
        self, project_id: UUID, image_id: UUID, updated: ImageAttachment
    ) -> ImageAttachment:
        p_idx, project = self._get_project_with_index(project_id)
        for img_idx, image in enumerate(project.images):
            if image.id == image_id:
                project.images[img_idx] = updated
                if updated.is_cover:
                    self._normalize_cover(project, updated.id)
                self.store.projects[p_idx] = project
                self.save()
                return updated
        raise KeyError(f"Image {image_id} not found in project {project_id}")

    def delete_image(self, project_id: UUID, image_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        for img_idx, image in enumerate(project.images):
            if image.id == image_id:
                project.images.pop(img_idx)
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"Image {image_id} not found in project {project_id}")

    # --- Project comments ---
    def list_project_comments(self, project_id: UUID) -> list[Comment]:
        _, project = self._get_project_with_index(project_id)
        return list(project.comments)

    def add_project_comment(self, project_id: UUID, comment: Comment) -> Comment:
        p_idx, project = self._get_project_with_index(project_id)
        project.comments.insert(0, comment)
        self.store.projects[p_idx] = project
        self.save()
        return comment

    def delete_project_comment(self, project_id: UUID, comment_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        for c_idx, comment in enumerate(project.comments):
            if comment.id == comment_id:
                project.comments.pop(c_idx)
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"Comment {comment_id} not found in project {project_id}")

    def update_project_comment(self, project_id: UUID, comment_id: UUID, text: str) -> Comment:
        p_idx, project = self._get_project_with_index(project_id)
        for comment in project.comments:
            if comment.id == comment_id:
                comment.text = text
                comment.edited_at = datetime.utcnow()
                self.store.projects[p_idx] = project
                self.save()
                return comment
        raise KeyError(f"Comment {comment_id} not found in project {project_id}")

    # --- Task comments ---
    def list_task_comments(self, project_id: UUID, task_id: UUID) -> list[Comment]:
        _, project = self._get_project_with_index(project_id)
        _, task = self._get_task_with_index(project, task_id)
        return list(task.comments)

    def add_task_comment(self, project_id: UUID, task_id: UUID, comment: Comment) -> Comment:
        p_idx, project = self._get_project_with_index(project_id)
        t_idx, task = self._get_task_with_index(project, task_id)
        task.comments.insert(0, comment)
        project.tasks[t_idx] = task
        self.store.projects[p_idx] = project
        self.save()
        return comment

    def delete_task_comment(self, project_id: UUID, task_id: UUID, comment_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        t_idx, task = self._get_task_with_index(project, task_id)
        for c_idx, comment in enumerate(task.comments):
            if comment.id == comment_id:
                task.comments.pop(c_idx)
                project.tasks[t_idx] = task
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"Comment {comment_id} not found in task {task_id}")

    def update_task_comment(self, project_id: UUID, task_id: UUID, comment_id: UUID, text: str) -> Comment:
        p_idx, project = self._get_project_with_index(project_id)
        t_idx, task = self._get_task_with_index(project, task_id)
        for comment in task.comments:
            if comment.id == comment_id:
                comment.text = text
                comment.edited_at = datetime.utcnow()
                project.tasks[t_idx] = task
                self.store.projects[p_idx] = project
                self.save()
                return comment
        raise KeyError(f"Comment {comment_id} not found in task {task_id}")

    # --- History ---
    def list_history(self, project_id: UUID) -> list[HistoryEvent]:
        _, project = self._get_project_with_index(project_id)
        return list(project.history)

    def add_history_event(self, project_id: UUID, event: HistoryEvent) -> HistoryEvent:
        p_idx, project = self._get_project_with_index(project_id)
        project.history.insert(0, event)
        self.store.projects[p_idx] = project
        self.save()
        return event

    def delete_history_event(self, project_id: UUID, event_id: UUID) -> None:
        p_idx, project = self._get_project_with_index(project_id)
        for e_idx, event in enumerate(project.history):
            if event.id == event_id:
                project.history.pop(e_idx)
                self.store.projects[p_idx] = project
                self.save()
                return
        raise KeyError(f"History event {event_id} not found in project {project_id}")

    # --- Dashboard aggregations ---
    def _project_matches_filters(
        self,
        project: Project,
        *,
        include_archived: bool,
        group_id: UUID | None,
        brand: str | None,
        statuses: set[ProjectStatus] | None,
    ) -> bool:
        if not include_archived and project.status == ProjectStatus.ARCHIVED:
            return False
        if group_id and project.group_id != group_id:
            return False
        if brand and project.brand.lower() != brand.lower():
            return False
        if statuses and project.status not in statuses:
            return False
        return True

    @staticmethod
    def _project_has_risk(project: Project, today: date) -> bool:
        for stage in project.gtm_stages:
            if stage.risk_flag:
                return True
            if stage.planned_end and stage.status not in {StageStatus.DONE, StageStatus.CANCELLED}:
                if stage.planned_end < today:
                    return True
        for task in project.tasks:
            if task.due_date and task.status != TaskStatus.DONE and task.due_date < today:
                return True
        return False

    @staticmethod
    def _project_overdue_days(project: Project, today: date) -> int:
        """Самое сильное просроченное значение для проекта (в днях)."""

        max_overdue = 0
        for stage in project.gtm_stages:
            if stage.planned_end and stage.status not in {StageStatus.DONE, StageStatus.CANCELLED}:
                overdue = (today - stage.planned_end).days
                if overdue > max_overdue:
                    max_overdue = overdue
        for task in project.tasks:
            if task.due_date and task.status != TaskStatus.DONE:
                overdue = (today - task.due_date).days
                if overdue > max_overdue:
                    max_overdue = overdue
        return max_overdue

    def build_dashboard(
        self,
        *,
        include_archived: bool = False,
        group_id: UUID | None = None,
        brand: str | None = None,
        statuses: set[ProjectStatus] | None = None,
        upcoming_limit: int = 10,
        changes_limit: int = 24,
    ) -> DashboardPayload:
        today = date.today()
        now = datetime.now(timezone.utc)
        recent_threshold = now - timedelta(days=30)
        active_group_ids: set[UUID] | None = None
        if not include_archived:
            active_group_ids = {
                group.id for group in self.store.product_groups if group.status != GroupStatus.ARCHIVED
            }

        filtered_projects = [
            project
            for project in self.store.projects
            if self._project_matches_filters(
                project,
                include_archived=include_archived,
                group_id=group_id,
                brand=brand,
                statuses=statuses,
            )
            and (
                include_archived
                or active_group_ids is None
                or project.group_id in active_group_ids
            )
        ]

        status_summary = StatusSummary()
        for project in filtered_projects:
            if project.status == ProjectStatus.IN_PROGRESS:
                status_summary.in_progress += 1
            elif project.status == ProjectStatus.LAUNCHED:
                status_summary.launched += 1
            elif project.status == ProjectStatus.CLOSED:
                status_summary.closed += 1
            elif project.status == ProjectStatus.EOL:
                status_summary.eol += 1
            elif project.status == ProjectStatus.ARCHIVED:
                status_summary.archived += 1

        brand_metrics: dict[str, int] = {}
        for project in filtered_projects:
            brand_name = project.brand.strip() or "Без бренда"
            brand_metrics[brand_name] = brand_metrics.get(brand_name, 0) + 1

        gtm_distribution = GTMDistribution()
        for project in filtered_projects:
            if not project.gtm_stages:
                gtm_distribution.none += 1
                continue

            stages_sorted = sorted(project.gtm_stages, key=lambda s: s.order)
            current_index: int | None = None
            if project.current_gtm_stage_id:
                for idx, stage in enumerate(stages_sorted):
                    if stage.id == project.current_gtm_stage_id:
                        current_index = idx
                        break
            if current_index is None:
                for idx, stage in enumerate(stages_sorted):
                    if stage.status not in {StageStatus.DONE, StageStatus.CANCELLED}:
                        current_index = idx
                        break
            if current_index is None:
                current_index = len(stages_sorted) - 1

            ratio = (current_index + 1) / max(len(stages_sorted), 1)
            if ratio <= 1 / 3:
                gtm_distribution.early += 1
            elif ratio <= 2 / 3:
                gtm_distribution.middle += 1
            else:
                gtm_distribution.late += 1

        if include_archived:
            groups = list(self.store.product_groups)
        else:
            groups = [g for g in self.store.product_groups if g.status != GroupStatus.ARCHIVED]

        group_cards: list[GroupDashboardCard] = []
        for group in groups:
            group_projects = [p for p in filtered_projects if p.group_id == group.id]
            active_count = len([p for p in group_projects if p.status != ProjectStatus.ARCHIVED])
            risk = any(self._project_has_risk(p, today) for p in group_projects)
            group_cards.append(
                GroupDashboardCard(
                    id=group.id,
                    name=group.name,
                    active_projects=active_count,
                    risk=risk,
                )
            )

        upcoming: list[UpcomingItem] = []
        for project in filtered_projects:
            group_name = next((g.name for g in self.store.product_groups if g.id == project.group_id), "")
            for stage in project.gtm_stages:
                if stage.planned_end and stage.status not in {StageStatus.DONE, StageStatus.CANCELLED}:
                    delta = (stage.planned_end - today).days
                    upcoming.append(
                        UpcomingItem(
                            project_id=project.id,
                            project_name=project.name,
                            group_name=group_name,
                            kind="gtm_stage",
                            title=stage.title,
                            planned_date=stage.planned_end,
                            days_delta=delta,
                            risk=stage.risk_flag or delta < 0,
                        )
                    )
            for task in project.tasks:
                if task.due_date and task.status != TaskStatus.DONE and task.important:
                    delta = (task.due_date - today).days
                    upcoming.append(
                        UpcomingItem(
                            project_id=project.id,
                            project_name=project.name,
                            group_name=group_name,
                            kind="task",
                            title=task.title,
                            planned_date=task.due_date,
                            days_delta=delta,
                            risk=delta < 0,
                        )
                    )

        upcoming.sort(key=lambda item: item.days_delta)
        upcoming = upcoming[:upcoming_limit]

        recent_events: list[RecentChange] = []
        risk_projects: list[RiskProject] = []
        collect_recent = changes_limit > 0
        for project in filtered_projects:
            group_name = next((g.name for g in self.store.product_groups if g.id == project.group_id), "")
            if collect_recent:
                for event in project.history:
                    occurred_at = event.occurred_at
                    if occurred_at.tzinfo is None:
                        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                    if occurred_at < recent_threshold:
                        continue
                    recent_events.append(
                        RecentChange(
                            project_id=project.id,
                            project_name=project.name,
                            group_name=group_name,
                            occurred_at=occurred_at,
                            summary=event.summary,
                            details=event.details,
                        )
                    )

            if self._project_has_risk(project, today):
                overdue_days = self._project_overdue_days(project, today)
                reason = "Просрочка по задачам/этапам" if overdue_days > 0 else "Отмечен риск"
                risk_projects.append(
                    RiskProject(
                        project_id=project.id,
                        project_name=project.name,
                        group_name=group_name,
                        overdue_days=overdue_days,
                        reason=reason,
                    )
                )

        if collect_recent:
            recent_events.sort(key=lambda item: item.occurred_at, reverse=True)
            recent_events = recent_events[:changes_limit]
        else:
            recent_events = []

        total_projects = len(filtered_projects)
        overdue_projects = len(risk_projects)
        active_groups = len(groups)
        risky_groups = len([g for g in group_cards if g.risk])
        completion_rate = 0.0
        in_work_total = (
            status_summary.in_progress + status_summary.launched + status_summary.eol + status_summary.closed
        )
        if in_work_total:
            completion_rate = (status_summary.closed + status_summary.eol) / in_work_total
        overdue_rate = 0.0
        if total_projects:
            overdue_rate = overdue_projects / total_projects

        return DashboardPayload(
            statuses=status_summary,
            groups=group_cards,
            kpis=DashboardKPI(
                total_projects=total_projects,
                in_progress=status_summary.in_progress,
                launched=status_summary.launched,
                closed=status_summary.closed,
                eol=status_summary.eol,
                archived=status_summary.archived,
                completion_rate=round(completion_rate, 3),
                overdue_projects=overdue_projects,
                overdue_rate=round(overdue_rate, 3),
                active_groups=active_groups,
                risky_groups=risky_groups,
            ),
            brands=[
                BrandMetric(brand=name, projects=count)
                for name, count in sorted(brand_metrics.items(), key=lambda item: item[1], reverse=True)
            ],
            gtm_distribution=gtm_distribution,
            risk_projects=sorted(
                risk_projects, key=lambda r: (r.overdue_days * -1, r.project_name)
            ),
            upcoming=upcoming,
            recent_changes=recent_events,
        )

    def build_priority_task_summary(
        self, *, include_archived_projects: bool = False
    ) -> TaskSpotlightSummary:
        today = date.today()
        group_names = {group.id: group.name for group in self.store.product_groups}
        summary = TaskSpotlightSummary()

        def sort_key(item: SpotlightTask) -> tuple[int, int, str]:
            has_due = item.due_in_days is not None
            due_value = item.due_in_days or 0
            return (0 if has_due else 1, due_value, item.title.lower())

        for project in self.store.projects:
            if not include_archived_projects and project.status == ProjectStatus.ARCHIVED:
                continue

            stage_titles = {stage.id: stage.title for stage in project.gtm_stages}
            group_name = group_names.get(project.group_id, "Без группы")

            for task in project.tasks:
                if task.status == TaskStatus.DONE:
                    continue
                is_important = bool(task.important)
                is_urgent = task.urgency == TaskUrgency.HIGH
                if not is_important and not is_urgent:
                    continue

                due_in_days = None
                overdue = False
                if task.due_date:
                    due_in_days = (task.due_date - today).days
                    overdue = due_in_days < 0

                spotlight = SpotlightTask(
                    task_id=task.id,
                    title=task.title,
                    project_id=project.id,
                    project_name=project.name,
                    group_id=project.group_id,
                    group_name=group_name,
                    gtm_stage_id=task.gtm_stage_id,
                    gtm_stage_title=stage_titles.get(task.gtm_stage_id) if task.gtm_stage_id else None,
                    due_date=task.due_date,
                    due_in_days=due_in_days,
                    important=is_important,
                    urgency=task.urgency,
                    status=task.status,
                    overdue=overdue,
                )

                if is_important and is_urgent:
                    summary.urgent_and_important.append(spotlight)
                elif is_important:
                    summary.important_only.append(spotlight)
                else:
                    summary.urgent_only.append(spotlight)

        summary.urgent_and_important.sort(key=sort_key)
        summary.important_only.sort(key=sort_key)
        summary.urgent_only.sort(key=sort_key)
        return summary

    # --- Backups ---
    def list_backups(self, backups_dir: Path) -> list[BackupInfo]:
        backups: list[BackupInfo] = []
        if not backups_dir.exists():
            return backups

        for entry in backups_dir.glob("*.json"):
            stat = entry.stat()
            backups.append(
                BackupInfo(
                    file_name=entry.name,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )

        backups.sort(key=lambda item: item.created_at, reverse=True)
        return backups

    def create_backup(self, backups_dir: Path) -> BackupInfo:
        backups_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        file_name = f"project_tracker_{timestamp}.json"
        destination = backups_dir / file_name
        _write_json(destination, self.store)
        stat = destination.stat()
        return BackupInfo(
            file_name=file_name,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )

    def restore_from_backup(self, backups_dir: Path, file_name: str) -> BackupInfo:
        backup_path = backups_dir / file_name
        if not backup_path.exists():
            raise FileNotFoundError(f"Резервная копия {file_name} не найдена")

        restored_store = load_store(backup_path)
        self.store = restored_store
        self.save()

        stat = backup_path.stat()
        return BackupInfo(
            file_name=file_name,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )
