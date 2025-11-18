"""Экспорт данных в Excel."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Iterable
from uuid import UUID

from openpyxl import Workbook, load_workbook

from .models import ChecklistItem, GTMStage, Project, ProjectStatus, ProductGroup, StageStatus


def _find_current_stage_name(project: Project) -> str | None:
    if not project.current_gtm_stage_id:
        return None
    for stage in project.gtm_stages:
        if stage.id == project.current_gtm_stage_id:
            return stage.title
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


def export_gtm_stages_to_excel(project: Project) -> bytes:
    """Сформировать Excel-файл со структурой GTM-этапов проекта."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "GTM-этапы"

    headers = [
        "Порядок",
        "Название этапа",
        "Описание",
        "Плановая дата начала",
        "Плановая дата окончания",
        "Фактическая дата завершения",
        "Статус",
        "Риск",
        "Чек-лист",
    ]
    sheet.append(headers)

    for stage in sorted(project.gtm_stages, key=lambda s: s.order):
        checklist_serialized = "; ".join(
            f"{'[x]' if item.done else '[ ]'} {item.title}" for item in sorted(stage.checklist, key=lambda c: c.order)
        )
        sheet.append(
            [
                stage.order,
                stage.title,
                stage.description,
                stage.planned_start,
                stage.planned_end,
                stage.actual_end,
                stage.status.value,
                "да" if stage.risk_flag else "нет",
                checklist_serialized,
            ]
        )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "да", "y", "yes", "oui", "on"}


STATUS_ALIASES = {
    "не начат": StageStatus.NOT_STARTED,
    "not started": StageStatus.NOT_STARTED,
    "в работе": StageStatus.IN_PROGRESS,
    "in progress": StageStatus.IN_PROGRESS,
    "done": StageStatus.DONE,
    "завершен": StageStatus.DONE,
    "завершён": StageStatus.DONE,
    "отменен": StageStatus.CANCELLED,
    "отменён": StageStatus.CANCELLED,
    "cancelled": StageStatus.CANCELLED,
}


def import_gtm_stages_from_excel(content: bytes) -> tuple[list[GTMStage], list[str]]:
    """Распарсить Excel с этапами GTM и вернуть список этапов и список ошибок."""

    try:
        workbook = load_workbook(filename=BytesIO(content))
    except Exception as exc:  # noqa: BLE001
        return [], [f"Не удалось прочитать Excel: {exc}"]

    sheet = workbook.active

    try:
        first_row = next(sheet.iter_rows(max_row=1))
    except StopIteration:
        return [], ["Файл Excel пуст"]
    header_row = [str(cell.value).strip() if cell.value is not None else "" for cell in first_row]
    header_map = {title.lower(): idx for idx, title in enumerate(header_row) if title}

    required_columns = {"название этапа"}
    missing = required_columns - set(header_map)
    if missing:
        return [], [f"Отсутствуют обязательные столбцы: {', '.join(sorted(missing))}"]

    stages: list[GTMStage] = []
    errors: list[str] = []

    def col(key: str, default: int | None = None) -> int | None:
        if key in header_map:
            return header_map[key]
        return default

    for row_index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if all(cell is None for cell in row):
            continue

        title = row[col("название этапа")]
        if not title:
            errors.append(f"Строка {row_index}: пустое название этапа")
            continue

        order_cell = col("порядок")
        order_value = len(stages)
        if order_cell is not None and row[order_cell] is not None:
            try:
                order_value = int(row[order_cell])
            except ValueError:
                errors.append(f"Строка {row_index}: не удалось разобрать порядок '{row[order_cell]}'")
                continue

        status_cell = col("статус")
        status_raw = row[status_cell] if status_cell is not None else None
        status_value = StageStatus.NOT_STARTED
        if status_raw:
            normalized = str(status_raw).strip().lower()
            status_value = STATUS_ALIASES.get(normalized, None) or StageStatus.__members__.get(normalized.upper(), None)
            if status_value is None:
                errors.append(f"Строка {row_index}: неизвестный статус '{status_raw}'")
                continue

        risk_cell = col("риск")
        risk_value = _parse_bool(row[risk_cell]) if risk_cell is not None else False

        checklist_cell = col("чек-лист")
        checklist_raw = row[checklist_cell] if checklist_cell is not None else None
        checklist_items: list[str] = []
        if checklist_raw:
            checklist_items = [part.strip() for part in str(checklist_raw).split(";") if part.strip()]

        checklist_models = []
        for idx, item in enumerate(checklist_items):
            text = item
            done = False
            if item.startswith("[x]"):
                done = True
                text = item[3:].strip()
            elif item.startswith("[ ]"):
                text = item[3:].strip()
            checklist_models.append(ChecklistItem(title=text, done=done, order=idx))

        stage = GTMStage(
            title=str(title).strip(),
            description=(row[col("описание")] if col("описание") is not None else None),
            order=order_value,
            planned_start=row[col("плановая дата начала")] if col("плановая дата начала") is not None else None,
            planned_end=row[col("плановая дата окончания")] if col("плановая дата окончания") is not None else None,
            actual_end=row[col("фактическая дата завершения")] if col("фактическая дата завершения") is not None else None,
            status=status_value,
            risk_flag=risk_value,
            checklist=checklist_models,
        )

        stages.append(stage)

    stages.sort(key=lambda s: s.order)
    return stages, errors
