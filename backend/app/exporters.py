"""Экспорт данных в Excel."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Iterable
from uuid import UUID

from openpyxl import Workbook, load_workbook

from .models import (
    CharacteristicSection,
    ChecklistItem,
    FieldType,
    GTMStage,
    Project,
    ProjectStatus,
    ProductGroup,
    StageStatus,
)


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


def export_characteristics_to_excel(project: Project) -> bytes:
    """Сформировать Excel-файл с характеристиками проекта."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Характеристики"

    headers = [
        "Секция",
        "Label RU",
        "Label EN",
        "Value RU",
        "Value EN",
        "Тип поля",
    ]
    sheet.append(headers)

    for section in sorted(project.characteristics, key=lambda s: s.order):
        for field in sorted(section.fields, key=lambda f: f.order):
            sheet.append(
                [
                    section.title,
                    field.label_ru,
                    field.label_en,
                    field.value_ru,
                    field.value_en,
                    field.field_type.value,
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


FIELD_TYPE_ALIASES = {
    "text": FieldType.TEXT,
    "текст": FieldType.TEXT,
    "number": FieldType.NUMBER,
    "число": FieldType.NUMBER,
    "select": FieldType.SELECT,
    "list": FieldType.SELECT,
    "список": FieldType.SELECT,
    "checkbox": FieldType.CHECKBOX,
    "флажок": FieldType.CHECKBOX,
    "галочка": FieldType.CHECKBOX,
    "other": FieldType.OTHER,
    "другое": FieldType.OTHER,
}


def import_characteristics_from_excel(
    content: bytes, project: Project
) -> tuple[list[CharacteristicSection], list[str]]:
    """Распарсить Excel с характеристиками и вернуть обновлённые секции и ошибки."""

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

    required_columns = {"секция", "label ru", "label en"}
    missing = required_columns - set(header_map)
    if missing:
        return [], [f"Отсутствуют обязательные столбцы: {', '.join(sorted(missing))}"]

    errors: list[str] = []
    sections_copy: list[CharacteristicSection] = [section.model_copy(deep=True) for section in project.characteristics]

    def col(key: str, default: int | None = None) -> int | None:
        if key in header_map:
            return header_map[key]
        return default

    def normalize(value: str | None) -> str:
        return value.strip().lower() if value else ""

    for row_index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if all(cell is None for cell in row):
            continue

        section_title = row[col("секция")]
        if not section_title:
            errors.append(f"Строка {row_index}: не заполнено название секции")
            continue

        label_ru = row[col("label ru")]
        label_en = row[col("label en")]
        if not label_ru and not label_en:
            errors.append(f"Строка {row_index}: не указаны Label RU/EN")
            continue

        section = next(
            (s for s in sections_copy if normalize(s.title) == normalize(str(section_title))),
            None,
        )
        if section is None:
            errors.append(f"Строка {row_index}: секция '{section_title}' не найдена в проекте")
            continue

        field = next(
            (
                f
                for f in section.fields
                if normalize(f.label_ru) == normalize(label_ru or "")
                and normalize(f.label_en) == normalize(label_en or "")
            ),
            None,
        )
        if field is None:
            errors.append(
                f"Строка {row_index}: поле '{label_ru or ''}/{label_en or ''}' не найдено в секции '{section_title}'"
            )
            continue

        value_ru_idx = col("value ru")
        value_en_idx = col("value en")
        if value_ru_idx is not None:
            field.value_ru = row[value_ru_idx]
        if value_en_idx is not None:
            field.value_en = row[value_en_idx]

        field_type_cell = col("тип поля")
        if field_type_cell is not None and row[field_type_cell] is not None:
            type_raw = normalize(str(row[field_type_cell]))
            field.field_type = FIELD_TYPE_ALIASES.get(type_raw, field.field_type)

    return sections_copy, errors
