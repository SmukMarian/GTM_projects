"""Локальное файловое хранилище для Haier Project Tracker.

Слой отвечает за загрузку и сохранение доменных моделей в один JSON-файл,
что соответствует требованию ТЗ о локальной работе и возможности ручного
копирования базы. Предоставляет минимальный репозиторий для работы с
продуктовыми группами и проектами; по мере развития интерфейса он будет
расширяться другими операциями.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    CharacteristicField,
    CharacteristicSection,
    CharacteristicTemplate,
    Comment,
    FileAttachment,
    GTMTemplate,
    GTMStage,
    HistoryEvent,
    ImageAttachment,
    ProductGroup,
    Project,
    ProjectStatus,
    Subtask,
    Task,
    TaskStatus,
)


class DataStore(BaseModel):
    """Основная структура данных, сохраняемая на диск."""

    product_groups: list[ProductGroup] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    gtm_templates: list[GTMTemplate] = Field(default_factory=list)
    characteristic_templates: list[CharacteristicTemplate] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True, json_encoders={Path: str})


def _write_json(path: Path, store: DataStore) -> None:
    path.write_text(store.model_dump_json(indent=2, exclude_none=True, by_alias=False), encoding="utf-8")


def load_store(path: Path) -> DataStore:
    """Загрузить хранилище из файла; если файл отсутствует — вернуть пустую структуру."""

    if path.exists():
        return DataStore.model_validate_json(path.read_text(encoding="utf-8"))
    return DataStore()


class LocalRepository:
    """Простейший репозиторий поверх JSON-файла."""

    def __init__(self, path: Path):
        self.path = path
        self.store = load_store(path)

    def save(self) -> None:
        _write_json(self.path, self.store)

    # --- Product groups ---
    def list_groups(self, include_archived: bool = True) -> list[ProductGroup]:
        groups: Iterable[ProductGroup] = self.store.product_groups
        if not include_archived:
            groups = [g for g in groups if g.status.value != "archived"]
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
    ) -> list[Project]:
        projects: Iterable[Project] = self.store.projects
        if not include_archived:
            projects = [p for p in projects if p.status.value != "archived"]
        if group_id:
            projects = [p for p in projects if p.group_id == group_id]
        if statuses:
            projects = [p for p in projects if p.status in statuses]
        return list(projects)

    def get_project(self, project_id: UUID) -> Project | None:
        for project in self.store.projects:
            if project.id == project_id:
                return project
        return None

    def add_project(self, project: Project) -> Project:
        self.store.projects.append(project)
        self.save()
        return project

    def update_project(self, project_id, updated: Project) -> Project:
        for idx, project in enumerate(self.store.projects):
            if project.id == project_id:
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
                new_stages = [stage.model_copy(update={"id": uuid4()}) for stage in template.stages]
                project.gtm_stages = new_stages
                self.store.projects[p_idx] = project
                self.save()
                return new_stages
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
        project.tasks.append(task)
        self.store.projects[p_idx] = project
        self.save()
        return task

    def update_task(self, project_id: UUID, task_id: UUID, updated: Task) -> Task:
        p_idx, project = self._get_project_with_index(project_id)
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
