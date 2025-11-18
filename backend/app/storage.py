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

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    CharacteristicTemplate,
    GTMTemplate,
    ProductGroup,
    Project,
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

    # --- Projects ---
    def list_projects(self, include_archived: bool = True) -> list[Project]:
        projects: Iterable[Project] = self.store.projects
        if not include_archived:
            projects = [p for p in projects if p.status.value != "archived"]
        return list(projects)

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
