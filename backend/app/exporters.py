"""Экспорт данных в Excel."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Iterable
from uuid import UUID

from openpyxl import Workbook

from .models import Project, ProjectStatus, ProductGroup


def _find_current_stage_name(project: Project) -> str | None:
    if not project.current_gtm_stage_id:
        return None
    for stage in project.gtm_stages:
        if stage.id == project.current_gtm_stage_id:
            return stage.name
    return None


def export_projects_to_excel(
    *,
    projects: Iterable[Project],
    groups: Iterable[ProductGroup],
    statuses: set[ProjectStatus] | None = None,
    include_archived: bool = True,
    brand: str | None = None,
    current_stage_id: UUID | None = None,
    planned_from: date | None = None,
    planned_to: date | None = None,
) -> bytes:
    """Сформировать Excel-файл со списком проектов."""

    projects_list: list[Project] = list(projects)
    if statuses is not None:
        projects_list = [p for p in projects_list if p.status in statuses]
    if not include_archived:
        projects_list = [p for p in projects_list if p.status != ProjectStatus.ARCHIVED]
    if brand:
        projects_list = [p for p in projects_list if p.brand.lower() == brand.lower()]
    if current_stage_id:
        projects_list = [p for p in projects_list if p.current_gtm_stage_id == current_stage_id]
    if planned_from:
        projects_list = [
            p
            for p in projects_list
            if p.planned_launch is not None and p.planned_launch >= planned_from
        ]
    if planned_to:
        projects_list = [
            p
            for p in projects_list
            if p.planned_launch is not None and p.planned_launch <= planned_to
        ]

    group_name_by_id = {group.id: group.name for group in groups}

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Проекты"

    headers = [
        "Название проекта",
        "Продуктовая группа",
        "Бренд",
        "Статус",
        "Рынок/регион",
        "Плановая дата запуска",
        "Фактическая дата запуска",
        "Текущий GTM-этап",
        "Приоритет",
    ]
    sheet.append(headers)

    for project in projects_list:
        current_stage_name = _find_current_stage_name(project)
        sheet.append(
            [
                project.name,
                group_name_by_id.get(project.group_id, ""),
                project.brand,
                project.status.value,
                project.market,
                project.planned_launch,
                project.actual_launch,
                current_stage_name,
                project.priority.value if project.priority else None,
            ]
        )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
