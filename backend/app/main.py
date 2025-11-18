"""Базовый сервер Haier Project Tracker.

Этот модуль поднимает минимальное FastAPI-приложение, которое будет
обслуживать фронтенд и API. На данном этапе реализован только health-check
и раздача статических файлов из каталога ``frontend``.
"""

import shutil
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .exporters import (
    export_characteristics_to_excel,
    export_gtm_stages_to_excel,
    export_projects_to_excel,
    import_gtm_stages_from_excel,
)
from .models import (
    BackupInfo,
    BackupRestoreRequest,
    CharacteristicField,
    CharacteristicSection,
    CharacteristicTemplate,
    Comment,
    DashboardPayload,
    FileAttachment,
    GTMStage,
    GTMTemplate,
    GroupStatus,
    HistoryEvent,
    ImageAttachment,
    ProductGroup,
    Project,
    ProjectStatus,
    TemplateFromProjectRequest,
    Subtask,
    Task,
    TaskStatus,
)
from .storage import LocalRepository

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Haier Project Tracker", version="0.1.0")
repository = LocalRepository(settings.primary_store)


def get_repository() -> LocalRepository:
    """Dependency для доступа к файловому хранилищу."""

    return repository


def resolve_storage_path(path: Path) -> Path:
    """Вернуть абсолютный путь для вложения, если сохранён относительный путь."""

    return path if path.is_absolute() else settings.data_dir / path


def save_uploaded_file(upload: UploadFile, base_dir: Path) -> Path:
    """Сохранить загруженный файл в каталоге проекта и вернуть относительный путь от data_dir."""

    base_dir.mkdir(parents=True, exist_ok=True)
    filename = upload.filename or "file"
    target = base_dir / f"{uuid4().hex}_{filename}"
    with target.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return target.relative_to(settings.data_dir)


def log_event(repo: LocalRepository, project_id: UUID, summary: str, details: str | None = None) -> None:
    """Записать событие в историю проекта, игнорируя ошибки отсутствия проекта."""

    try:
        repo.add_history_event(project_id, HistoryEvent(summary=summary, details=details))
    except KeyError:
        return


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Простейший health-check эндпоинт."""

    return {"status": "ok"}


@app.get("/api/dashboard", response_model=DashboardPayload)
def get_dashboard(
    include_archived: bool = False,
    group_id: UUID | None = None,
    brand: str | None = None,
    statuses: list[ProjectStatus] | None = Query(None),
    repo: LocalRepository = Depends(get_repository),
) -> DashboardPayload:
    """Собрать агрегированные данные для главного дашборда."""

    status_set = set(statuses) if statuses else None
    return repo.build_dashboard(
        include_archived=include_archived,
        group_id=group_id,
        brand=brand,
        statuses=status_set,
    )


@app.get("/api/groups", response_model=list[ProductGroup])
def list_groups(
    include_archived: bool = True,
    brand: str | None = None,
    status: list[GroupStatus] | None = Query(default=None),
    extra_key: str | None = None,
    extra_value: str | None = None,
    repo: LocalRepository = Depends(get_repository),
) -> list[ProductGroup]:
    """Вернуть список продуктовых групп с фильтрами по статусу, бренду и пользовательскому полю."""

    status_set = set(status) if status else None
    return repo.list_groups(
        include_archived=include_archived,
        brand=brand,
        statuses=status_set,
        extra_key=extra_key,
        extra_value=extra_value,
    )


@app.get("/api/groups/{group_id}", response_model=ProductGroup)
def get_group(group_id: UUID, repo: LocalRepository = Depends(get_repository)) -> ProductGroup:
    group = repo.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    return group


@app.post("/api/groups", response_model=ProductGroup, status_code=201)
def create_group(group: ProductGroup, repo: LocalRepository = Depends(get_repository)) -> ProductGroup:
    """Создать продуктовую группу и сохранить её в файловом хранилище."""

    return repo.add_group(group)


@app.put("/api/groups/{group_id}", response_model=ProductGroup)
def update_group(group_id: UUID, group: ProductGroup, repo: LocalRepository = Depends(get_repository)) -> ProductGroup:
    if repo.get_group(group_id) is None:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    aligned_group = group.model_copy(update={"id": group_id})
    return repo.update_group(group_id, aligned_group)


@app.delete("/api/groups/{group_id}", status_code=204)
def delete_group(group_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    if repo.has_projects_for_group(group_id):
        raise HTTPException(
            status_code=400,
            detail="Невозможно удалить группу: найдены связанные проекты. Архивируйте или перенесите проекты перед удалением.",
        )
    try:
        repo.delete_group(group_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Группа не найдена")


@app.get("/api/projects", response_model=list[Project])
def list_projects(
    include_archived: bool = True,
    group_id: UUID | None = None,
    status: list[ProjectStatus] | None = Query(default=None),
    brand: str | None = None,
    current_stage_id: UUID | None = None,
    planned_from: date | None = None,
    planned_to: date | None = None,
    repo: LocalRepository = Depends(get_repository),
) -> list[Project]:
    """Вернуть список проектов с фильтрами по статусу и группе."""

    statuses = set(status) if status else None
    return repo.list_projects(
        include_archived=include_archived,
        group_id=group_id,
        statuses=statuses,
        brand=brand,
        current_stage_id=current_stage_id,
        planned_from=planned_from,
        planned_to=planned_to,
    )


@app.get("/api/export/projects", response_class=StreamingResponse)
def export_projects(
    include_archived: bool = True,
    status: list[ProjectStatus] | None = Query(default=None),
    brand: str | None = None,
    current_stage_id: UUID | None = None,
    planned_from: date | None = None,
    planned_to: date | None = None,
    repo: LocalRepository = Depends(get_repository),
) -> StreamingResponse:
    """Экспортировать список проектов в Excel со статусами и основными полями."""

    statuses = set(status) if status else None
    export_bytes = export_projects_to_excel(
        projects=repo.list_projects(include_archived=True),
        groups=repo.list_groups(include_archived=True),
        statuses=statuses,
        include_archived=include_archived,
        brand=brand,
        current_stage_id=current_stage_id,
        planned_from=planned_from,
        planned_to=planned_to,
    )

    headers = {"Content-Disposition": "attachment; filename=projects.xlsx"}
    return StreamingResponse(
        BytesIO(export_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.post("/api/projects", response_model=Project, status_code=201)
def create_project(project: Project, repo: LocalRepository = Depends(get_repository)) -> Project:
    """Создать проект и связать его с группой."""

    if repo.get_group(project.group_id) is None:
        raise HTTPException(status_code=400, detail="Указанная продуктовая группа не найдена")

    created = repo.add_project(project)
    log_event(repo, created.id, "Создан проект", f"Статус: {created.status.value}")
    return created


@app.get("/api/projects/{project_id}", response_model=Project)
def get_project(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> Project:
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


@app.put("/api/projects/{project_id}", response_model=Project)
def update_project(project_id: UUID, project: Project, repo: LocalRepository = Depends(get_repository)) -> Project:
    existing = repo.get_project(project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if repo.get_group(project.group_id) is None:
        raise HTTPException(status_code=400, detail="Указанная продуктовая группа не найдена")
    aligned_project = project.model_copy(update={"id": project_id})
    updated = repo.update_project(project_id, aligned_project)
    if existing.status != updated.status:
        log_event(repo, project_id, "Изменён статус проекта", f"{existing.status.value} → {updated.status.value}")
    return updated


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_project(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.get("/api/gtm-templates", response_model=list[GTMTemplate])
def list_gtm_templates(repo: LocalRepository = Depends(get_repository)) -> list[GTMTemplate]:
    """Вернуть список шаблонов GTM."""

    return repo.list_gtm_templates()


@app.get("/api/gtm-templates/{template_id}", response_model=GTMTemplate)
def get_gtm_template(template_id: UUID, repo: LocalRepository = Depends(get_repository)) -> GTMTemplate:
    template = repo.get_gtm_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон GTM не найден")
    return template


@app.post("/api/gtm-templates", response_model=GTMTemplate, status_code=201)
def create_gtm_template(template: GTMTemplate, repo: LocalRepository = Depends(get_repository)) -> GTMTemplate:
    return repo.add_gtm_template(template)


@app.put("/api/gtm-templates/{template_id}", response_model=GTMTemplate)
def update_gtm_template(template_id: UUID, template: GTMTemplate, repo: LocalRepository = Depends(get_repository)) -> GTMTemplate:
    if repo.get_gtm_template(template_id) is None:
        raise HTTPException(status_code=404, detail="Шаблон GTM не найден")
    aligned = template.model_copy(update={"id": template_id})
    return repo.update_gtm_template(template_id, aligned)


@app.delete("/api/gtm-templates/{template_id}", status_code=204)
def delete_gtm_template(template_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_gtm_template(template_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Шаблон GTM не найден")


@app.get("/api/characteristic-templates", response_model=list[CharacteristicTemplate])
def list_characteristic_templates(repo: LocalRepository = Depends(get_repository)) -> list[CharacteristicTemplate]:
    """Вернуть список шаблонов характеристик."""

    return repo.list_characteristic_templates()


@app.get("/api/characteristic-templates/{template_id}", response_model=CharacteristicTemplate)
def get_characteristic_template(template_id: UUID, repo: LocalRepository = Depends(get_repository)) -> CharacteristicTemplate:
    template = repo.get_characteristic_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон характеристик не найден")
    return template


@app.post("/api/characteristic-templates", response_model=CharacteristicTemplate, status_code=201)
def create_characteristic_template(
    template: CharacteristicTemplate, repo: LocalRepository = Depends(get_repository)
) -> CharacteristicTemplate:
    return repo.add_characteristic_template(template)


@app.put("/api/characteristic-templates/{template_id}", response_model=CharacteristicTemplate)
def update_characteristic_template(
    template_id: UUID, template: CharacteristicTemplate, repo: LocalRepository = Depends(get_repository)
) -> CharacteristicTemplate:
    if repo.get_characteristic_template(template_id) is None:
        raise HTTPException(status_code=404, detail="Шаблон характеристик не найден")
    aligned = template.model_copy(update={"id": template_id})
    return repo.update_characteristic_template(template_id, aligned)


@app.delete("/api/characteristic-templates/{template_id}", status_code=204)
def delete_characteristic_template(template_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_characteristic_template(template_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Шаблон характеристик не найден")


@app.get("/api/projects/{project_id}/gtm-stages", response_model=list[GTMStage])
def list_gtm_stages(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[GTMStage]:
    try:
        return repo.list_gtm_stages(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post("/api/projects/{project_id}/gtm-stages", response_model=GTMStage, status_code=201)
def create_gtm_stage(project_id: UUID, stage: GTMStage, repo: LocalRepository = Depends(get_repository)) -> GTMStage:
    try:
        created = repo.add_gtm_stage(project_id, stage)
        log_event(repo, project_id, "Добавлен GTM-этап", created.title)
        return created
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put("/api/projects/{project_id}/gtm-stages/{stage_id}", response_model=GTMStage)
def update_gtm_stage(project_id: UUID, stage_id: UUID, stage: GTMStage, repo: LocalRepository = Depends(get_repository)) -> GTMStage:
    existing = next((item for item in repo.list_gtm_stages(project_id) if item.id == stage_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Этап GTM не найден")

    aligned = stage.model_copy(update={"id": stage_id})
    try:
        updated = repo.update_gtm_stage(project_id, stage_id, aligned)
        if existing.status != updated.status:
            log_event(
                repo,
                project_id,
                "Изменён статус GTM-этапа",
                f"{existing.title}: {existing.status.value} → {updated.status.value}",
            )
        return updated
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Этап GTM не найден")


@app.delete("/api/projects/{project_id}/gtm-stages/{stage_id}", status_code=204)
def delete_gtm_stage(project_id: UUID, stage_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    stage = next((item for item in repo.list_gtm_stages(project_id) if item.id == stage_id), None)
    try:
        repo.delete_gtm_stage(project_id, stage_id)
        if stage:
            log_event(repo, project_id, "Удалён GTM-этап", stage.title)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Этап GTM не найден")


@app.post(
    "/api/projects/{project_id}/gtm-stages/apply-template",
    response_model=list[GTMStage],
    status_code=201,
)
def apply_gtm_template(project_id: UUID, template_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[GTMStage]:
    try:
        stages = repo.apply_gtm_template(project_id, template_id)
        log_event(repo, project_id, "Применён шаблон GTM")
        return stages
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Шаблон GTM не найден")


@app.post(
    "/api/projects/{project_id}/gtm-stages/import",
    response_model=list[GTMStage],
    status_code=201,
)
async def import_gtm_stages(
    project_id: UUID, file: UploadFile = File(...), repo: LocalRepository = Depends(get_repository)
) -> list[GTMStage]:
    if repo.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")

    content = await file.read()
    stages, errors = import_gtm_stages_from_excel(content)
    if errors:
        raise HTTPException(status_code=400, detail={"message": "Ошибка импорта GTM", "errors": errors})

    stages = repo.replace_gtm_stages(project_id, stages)
    log_event(repo, project_id, "Импортированы GTM-этапы (Excel)")
    return stages


@app.get("/api/projects/{project_id}/gtm-stages/export")
def export_gtm_stages(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> StreamingResponse:
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    payload = export_gtm_stages_to_excel(project)
    headers = {"Content-Disposition": f"attachment; filename=gtm_stages_{project_id}.xlsx"}
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.post(
    "/api/projects/{project_id}/gtm-stages/save-template",
    response_model=GTMTemplate,
    status_code=201,
)
def save_gtm_template_from_project(
    project_id: UUID, payload: TemplateFromProjectRequest, repo: LocalRepository = Depends(get_repository)
) -> GTMTemplate:
    try:
        return repo.create_gtm_template_from_project(project_id, payload.name, payload.description)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.get(
    "/api/projects/{project_id}/characteristics/sections",
    response_model=list[CharacteristicSection],
)
def list_characteristic_sections(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[CharacteristicSection]:
    try:
        return repo.list_characteristic_sections(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post(
    "/api/projects/{project_id}/characteristics/sections",
    response_model=CharacteristicSection,
    status_code=201,
)
def create_characteristic_section(
    project_id: UUID, section: CharacteristicSection, repo: LocalRepository = Depends(get_repository)
) -> CharacteristicSection:
    try:
        created = repo.add_characteristic_section(project_id, section)
        log_event(repo, project_id, "Добавлена секция характеристик", created.title)
        return created
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put(
    "/api/projects/{project_id}/characteristics/sections/{section_id}",
    response_model=CharacteristicSection,
)
def update_characteristic_section(
    project_id: UUID,
    section_id: UUID,
    section: CharacteristicSection,
    repo: LocalRepository = Depends(get_repository),
) -> CharacteristicSection:
    aligned = section.model_copy(update={"id": section_id})
    try:
        updated = repo.update_characteristic_section(project_id, section_id, aligned)
        log_event(repo, project_id, "Обновлена секция характеристик", updated.title)
        return updated
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Секция характеристик не найдена")


@app.delete(
    "/api/projects/{project_id}/characteristics/sections/{section_id}",
    status_code=204,
)
def delete_characteristic_section(project_id: UUID, section_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    section = next((item for item in repo.list_characteristic_sections(project_id) if item.id == section_id), None)
    try:
        repo.delete_characteristic_section(project_id, section_id)
        if section:
            log_event(repo, project_id, "Удалена секция характеристик", section.title)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Секция характеристик не найдена")


@app.post(
    "/api/projects/{project_id}/characteristics/sections/{section_id}/fields",
    response_model=CharacteristicField,
    status_code=201,
)
def create_characteristic_field(
    project_id: UUID,
    section_id: UUID,
    field: CharacteristicField,
    repo: LocalRepository = Depends(get_repository),
) -> CharacteristicField:
    try:
        created = repo.add_characteristic_field(project_id, section_id, field)
        log_event(repo, project_id, "Добавлено поле характеристики", created.label_ru)
        return created
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Секция характеристик не найдена")


@app.put(
    "/api/projects/{project_id}/characteristics/sections/{section_id}/fields/{field_id}",
    response_model=CharacteristicField,
)
def update_characteristic_field(
    project_id: UUID,
    section_id: UUID,
    field_id: UUID,
    field: CharacteristicField,
    repo: LocalRepository = Depends(get_repository),
) -> CharacteristicField:
    aligned = field.model_copy(update={"id": field_id})
    try:
        updated = repo.update_characteristic_field(project_id, section_id, field_id, aligned)
        log_event(repo, project_id, "Обновлено поле характеристики", updated.label_ru)
        return updated
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "section" in message.lower():
            raise HTTPException(status_code=404, detail="Секция характеристик не найдена")
        raise HTTPException(status_code=404, detail="Поле характеристики не найдено")


@app.delete(
    "/api/projects/{project_id}/characteristics/sections/{section_id}/fields/{field_id}",
    status_code=204,
)
def delete_characteristic_field(
    project_id: UUID, section_id: UUID, field_id: UUID, repo: LocalRepository = Depends(get_repository)
) -> None:
    field = None
    for section in repo.list_characteristic_sections(project_id):
        if section.id == section_id:
            field = next((item for item in section.fields if item.id == field_id), None)
            break
    try:
        repo.delete_characteristic_field(project_id, section_id, field_id)
        if field:
            log_event(repo, project_id, "Удалено поле характеристики", field.label_ru)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "section" in message.lower():
            raise HTTPException(status_code=404, detail="Секция характеристик не найдена")
        raise HTTPException(status_code=404, detail="Поле характеристики не найдено")


@app.post(
    "/api/projects/{project_id}/characteristics/apply-template",
    response_model=list[CharacteristicSection],
    status_code=201,
)
def apply_characteristic_template(
    project_id: UUID, template_id: UUID, repo: LocalRepository = Depends(get_repository)
) -> list[CharacteristicSection]:
    try:
        sections = repo.apply_characteristic_template(project_id, template_id)
        log_event(repo, project_id, "Применён шаблон характеристик")
        return sections
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Шаблон характеристик не найден")


@app.post(
    "/api/projects/{project_id}/characteristics/copy-structure",
    response_model=list[CharacteristicSection],
    status_code=201,
)
def copy_characteristics_structure(
    project_id: UUID, source_project_id: UUID, repo: LocalRepository = Depends(get_repository)
) -> list[CharacteristicSection]:
    try:
        sections = repo.copy_characteristics_structure(project_id, source_project_id)
        log_event(repo, project_id, "Скопирована структура характеристик")
        return sections
    except KeyError as exc:
        message = str(exc)
        if "Project" in message and str(project_id) in message:
            raise HTTPException(status_code=404, detail="Целевой проект не найден")
    raise HTTPException(status_code=404, detail="Проект-источник не найден")


@app.get("/api/projects/{project_id}/characteristics/export")
def export_characteristics(project_id: UUID, repo: LocalRepository = Depends(get_repository)):
    """Выгрузить характеристики проекта в Excel."""

    try:
        project = repo.get_project(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")

    content = export_characteristics_to_excel(project)
    filename = f"characteristics_{project_id}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(BytesIO(content), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@app.post(
    "/api/projects/{project_id}/characteristics/import",
    response_model=list[CharacteristicSection],
    status_code=201,
)
def import_characteristics(
    project_id: UUID, file: UploadFile = File(...), repo: LocalRepository = Depends(get_repository)
) -> list[CharacteristicSection]:
    content = file.file.read()
    sections, errors = repo.import_characteristics_from_excel(project_id, content)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    log_event(repo, project_id, "Импортированы характеристики (Excel)")
    return sections


@app.get("/api/projects/{project_id}/tasks", response_model=list[Task])
def list_tasks(
    project_id: UUID,
    status: list[TaskStatus] | None = Query(default=None),
    only_active: bool = False,
    gtm_stage_id: UUID | None = None,
    repo: LocalRepository = Depends(get_repository),
) -> list[Task]:
    """Вернуть задачи проекта с базовыми фильтрами."""

    statuses = set(status) if status else None
    try:
        return repo.list_tasks(project_id, statuses=statuses, only_active=only_active, gtm_stage_id=gtm_stage_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post("/api/projects/{project_id}/tasks", response_model=Task, status_code=201)
def create_task(project_id: UUID, task: Task, repo: LocalRepository = Depends(get_repository)) -> Task:
    try:
        created = repo.add_task(project_id, task)
        log_event(repo, project_id, "Добавлена задача", created.title)
        return created
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put("/api/projects/{project_id}/tasks/{task_id}", response_model=Task)
def update_task(project_id: UUID, task_id: UUID, task: Task, repo: LocalRepository = Depends(get_repository)) -> Task:
    try:
        existing = next((item for item in repo.list_tasks(project_id) if item.id == task_id), None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if existing is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    aligned = task.model_copy(update={"id": task_id})
    try:
        updated = repo.update_task(project_id, task_id, aligned)
        if existing.status != updated.status:
            log_event(
                repo,
                project_id,
                "Изменён статус задачи",
                f"{existing.title}: {existing.status.value} → {updated.status.value}",
            )
        else:
            log_event(repo, project_id, "Обновлена задача", updated.title)
        return updated
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.delete("/api/projects/{project_id}/tasks/{task_id}", status_code=204)
def delete_task(project_id: UUID, task_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        task = next((item for item in repo.list_tasks(project_id) if item.id == task_id), None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")
    try:
        repo.delete_task(project_id, task_id)
        if task:
            log_event(repo, project_id, "Удалена задача", task.title)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.post("/api/projects/{project_id}/tasks/{task_id}/subtasks", response_model=Subtask, status_code=201)
def create_subtask(project_id: UUID, task_id: UUID, subtask: Subtask, repo: LocalRepository = Depends(get_repository)) -> Subtask:
    try:
        created = repo.add_subtask(project_id, task_id, subtask)
        log_event(repo, project_id, "Добавлена подзадача", created.title)
        return created
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.put("/api/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}", response_model=Subtask)
def update_subtask(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
    subtask: Subtask,
    repo: LocalRepository = Depends(get_repository),
) -> Subtask:
    aligned = subtask.model_copy(update={"id": subtask_id})
    try:
        updated = repo.update_subtask(project_id, task_id, subtask_id, aligned)
        log_event(repo, project_id, "Обновлена подзадача", updated.title)
        return updated
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "Task" in message:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        raise HTTPException(status_code=404, detail="Подзадача не найдена")


@app.delete("/api/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}", status_code=204)
def delete_subtask(project_id: UUID, task_id: UUID, subtask_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    subtask_obj = None
    try:
        tasks = repo.list_tasks(project_id)
        for task in tasks:
            if task.id == task_id:
                subtask_obj = next((item for item in task.subtasks if item.id == subtask_id), None)
                break
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")
    try:
        repo.delete_subtask(project_id, task_id, subtask_id)
        if subtask_obj:
            log_event(repo, project_id, "Удалена подзадача", subtask_obj.title)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "Task" in message:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        raise HTTPException(status_code=404, detail="Подзадача не найдена")


@app.get("/api/projects/{project_id}/files", response_model=list[FileAttachment])
def list_files(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[FileAttachment]:
    try:
        return repo.list_files(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post(
    "/api/projects/{project_id}/files/upload",
    response_model=FileAttachment,
    status_code=201,
)
def upload_file(
    project_id: UUID,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    category: str | None = Form(default=None),
    repo: LocalRepository = Depends(get_repository),
) -> FileAttachment:
    if repo.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")

    stored_path = save_uploaded_file(file, settings.files_dir / str(project_id))
    attachment = FileAttachment(
        name=file.filename or "Файл",
        description=description,
        category=category,
        path=stored_path,
    )
    created = repo.add_file(project_id, attachment)
    log_event(repo, project_id, "Загружен файл", created.name)
    return created


@app.post("/api/projects/{project_id}/files", response_model=FileAttachment, status_code=201)
def add_file(project_id: UUID, file: FileAttachment, repo: LocalRepository = Depends(get_repository)) -> FileAttachment:
    try:
        created = repo.add_file(project_id, file)
        log_event(repo, project_id, "Добавлен файл", created.name)
        return created
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put("/api/projects/{project_id}/files/{file_id}", response_model=FileAttachment)
def update_file(
    project_id: UUID, file_id: UUID, file: FileAttachment, repo: LocalRepository = Depends(get_repository)
) -> FileAttachment:
    aligned = file.model_copy(update={"id": file_id})
    try:
        updated = repo.update_file(project_id, file_id, aligned)
        log_event(repo, project_id, "Обновлены данные файла", updated.name)
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="Файл не найден или проект не существует")


@app.delete("/api/projects/{project_id}/files/{file_id}", status_code=204)
def delete_file(project_id: UUID, file_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        attachment = next((item for item in repo.list_files(project_id) if item.id == file_id), None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")

    if attachment is None:
        raise HTTPException(status_code=404, detail="Файл не найден или проект не существует")

    stored_path = resolve_storage_path(attachment.path)
    try:
        repo.delete_file(project_id, file_id)
        if stored_path.exists():
            stored_path.unlink()
        log_event(repo, project_id, "Удалён файл", attachment.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Файл не найден или проект не существует")


@app.get("/api/projects/{project_id}/files/{file_id}/download")
def download_file(project_id: UUID, file_id: UUID, repo: LocalRepository = Depends(get_repository)) -> FileResponse:
    try:
        attachment = next((item for item in repo.list_files(project_id) if item.id == file_id), None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")

    if attachment is None:
        raise HTTPException(status_code=404, detail="Файл не найден")

    stored_path = resolve_storage_path(attachment.path)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Физический файл не найден")

    return FileResponse(stored_path, filename=attachment.name)


@app.get("/api/projects/{project_id}/images", response_model=list[ImageAttachment])
def list_images(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[ImageAttachment]:
    try:
        return repo.list_images(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post(
    "/api/projects/{project_id}/images/upload",
    response_model=ImageAttachment,
    status_code=201,
)
def upload_image(
    project_id: UUID,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    is_cover: bool = Form(default=False),
    repo: LocalRepository = Depends(get_repository),
) -> ImageAttachment:
    if repo.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")

    stored_path = save_uploaded_file(file, settings.images_dir / str(project_id))
    order = len(repo.list_images(project_id))
    image = ImageAttachment(
        filename=file.filename or "image",
        caption=caption,
        is_cover=is_cover,
        order=order,
        path=stored_path,
    )
    created = repo.add_image(project_id, image)
    if created.is_cover:
        log_event(repo, project_id, "Назначена обложка проекта", created.filename)
    else:
        log_event(repo, project_id, "Добавлено изображение", created.filename)
    return created


@app.post("/api/projects/{project_id}/images", response_model=ImageAttachment, status_code=201)
def add_image(project_id: UUID, image: ImageAttachment, repo: LocalRepository = Depends(get_repository)) -> ImageAttachment:
    try:
        created = repo.add_image(project_id, image)
        log_event(repo, project_id, "Добавлено изображение", created.filename)
        return created
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put("/api/projects/{project_id}/images/{image_id}", response_model=ImageAttachment)
def update_image(
    project_id: UUID, image_id: UUID, image: ImageAttachment, repo: LocalRepository = Depends(get_repository)
) -> ImageAttachment:
    aligned = image.model_copy(update={"id": image_id})
    try:
        updated = repo.update_image(project_id, image_id, aligned)
        if updated.is_cover:
            log_event(repo, project_id, "Назначена обложка проекта", updated.filename)
        else:
            log_event(repo, project_id, "Обновлено изображение", updated.filename)
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="Изображение не найдено или проект не существует")


@app.delete("/api/projects/{project_id}/images/{image_id}", status_code=204)
def delete_image(project_id: UUID, image_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        image = next((item for item in repo.list_images(project_id) if item.id == image_id), None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")

    if image is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено или проект не существует")

    stored_path = resolve_storage_path(image.path)
    try:
        repo.delete_image(project_id, image_id)
        if stored_path.exists():
            stored_path.unlink()
        log_event(repo, project_id, "Удалено изображение", image.filename)
    except KeyError:
        raise HTTPException(status_code=404, detail="Изображение не найдено или проект не существует")


@app.get("/api/projects/{project_id}/images/{image_id}/download")
def download_image(project_id: UUID, image_id: UUID, repo: LocalRepository = Depends(get_repository)) -> FileResponse:
    try:
        image = next((item for item in repo.list_images(project_id) if item.id == image_id), None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")

    if image is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено")

    stored_path = resolve_storage_path(image.path)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Физический файл не найден")

    return FileResponse(stored_path, filename=image.filename)


@app.get("/api/projects/{project_id}/comments", response_model=list[Comment])
def list_project_comments(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[Comment]:
    try:
        return repo.list_project_comments(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post("/api/projects/{project_id}/comments", response_model=Comment, status_code=201)
def add_project_comment(project_id: UUID, comment: Comment, repo: LocalRepository = Depends(get_repository)) -> Comment:
    try:
        created = repo.add_project_comment(project_id, comment)
        log_event(repo, project_id, "Добавлен комментарий к проекту")
        return created
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.delete("/api/projects/{project_id}/comments/{comment_id}", status_code=204)
def delete_project_comment(project_id: UUID, comment_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_project_comment(project_id, comment_id)
        log_event(repo, project_id, "Удалён комментарий к проекту")
    except KeyError:
        raise HTTPException(status_code=404, detail="Комментарий не найден или проект не существует")


@app.put("/api/projects/{project_id}/comments/{comment_id}", response_model=Comment)
def update_project_comment(
    project_id: UUID, comment_id: UUID, comment: Comment, repo: LocalRepository = Depends(get_repository)
) -> Comment:
    try:
        updated = repo.update_project_comment(project_id, comment_id, comment.text)
        log_event(repo, project_id, "Изменён комментарий к проекту")
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="Комментарий не найден или проект не существует")


@app.get(
    "/api/projects/{project_id}/tasks/{task_id}/comments",
    response_model=list[Comment],
)
def list_task_comments(project_id: UUID, task_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[Comment]:
    try:
        return repo.list_task_comments(project_id, task_id)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.post(
    "/api/projects/{project_id}/tasks/{task_id}/comments",
    response_model=Comment,
    status_code=201,
)
def add_task_comment(project_id: UUID, task_id: UUID, comment: Comment, repo: LocalRepository = Depends(get_repository)) -> Comment:
    try:
        created = repo.add_task_comment(project_id, task_id, comment)
        log_event(repo, project_id, "Комментарий к задаче", comment.text[:140])
        return created
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.delete(
    "/api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}",
    status_code=204,
)
def delete_task_comment(
    project_id: UUID, task_id: UUID, comment_id: UUID, repo: LocalRepository = Depends(get_repository)
) -> None:
    try:
        repo.delete_task_comment(project_id, task_id, comment_id)
        log_event(repo, project_id, "Удалён комментарий задачи")
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "Task" in message:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        raise HTTPException(status_code=404, detail="Комментарий не найден")


@app.put(
    "/api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}",
    response_model=Comment,
)
def update_task_comment(
    project_id: UUID, task_id: UUID, comment_id: UUID, comment: Comment, repo: LocalRepository = Depends(get_repository)
) -> Comment:
    try:
        updated = repo.update_task_comment(project_id, task_id, comment_id, comment.text)
        log_event(repo, project_id, "Изменён комментарий задачи")
        return updated
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "Task" in message:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        raise HTTPException(status_code=404, detail="Комментарий не найден")


@app.get("/api/projects/{project_id}/history", response_model=list[HistoryEvent])
def list_history(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> list[HistoryEvent]:
    try:
        return repo.list_history(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.post("/api/projects/{project_id}/history", response_model=HistoryEvent, status_code=201)
def add_history_event(
    project_id: UUID, event: HistoryEvent, repo: LocalRepository = Depends(get_repository)
) -> HistoryEvent:
    try:
        return repo.add_history_event(project_id, event)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.delete("/api/projects/{project_id}/history/{event_id}", status_code=204)
def delete_history_event(project_id: UUID, event_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_history_event(project_id, event_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Событие не найдено или проект не существует")


@app.get("/api/backups", response_model=list[BackupInfo])
def list_backups(repo: LocalRepository = Depends(get_repository)) -> list[BackupInfo]:
    """Вернуть список доступных резервных копий."""

    return repo.list_backups(settings.backups_dir)


@app.post("/api/backups", response_model=BackupInfo, status_code=201)
def create_backup(repo: LocalRepository = Depends(get_repository)) -> BackupInfo:
    """Создать резервную копию текущего хранилища."""

    return repo.create_backup(settings.backups_dir)


@app.post("/api/backups/restore", response_model=BackupInfo)
def restore_backup(request: BackupRestoreRequest, repo: LocalRepository = Depends(get_repository)) -> BackupInfo:
    """Восстановить хранилище из выбранной резервной копии."""

    try:
        return repo.restore_from_backup(settings.backups_dir, request.file_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Резервная копия не найдена")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def frontend_placeholder() -> str:
        """Заглушка, если фронтенд ещё не настроен."""

        return "<h1>Haier Project Tracker</h1><p>Фронтенд ещё не настроен.</p>"
