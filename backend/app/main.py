"""Базовый сервер Haier Project Tracker.

Этот модуль поднимает минимальное FastAPI-приложение, которое будет
обслуживать фронтенд и API. На данном этапе реализован только health-check
и раздача статических файлов из каталога ``frontend``.
"""

from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import (
    CharacteristicField,
    CharacteristicSection,
    CharacteristicTemplate,
    GTMStage,
    GTMTemplate,
    ProductGroup,
    Project,
    ProjectStatus,
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


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Простейший health-check эндпоинт."""

    return {"status": "ok"}


@app.get("/api/groups", response_model=list[ProductGroup])
def list_groups(include_archived: bool = True, repo: LocalRepository = Depends(get_repository)) -> list[ProductGroup]:
    """Вернуть список продуктовых групп."""

    return repo.list_groups(include_archived=include_archived)


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
    repo: LocalRepository = Depends(get_repository),
) -> list[Project]:
    """Вернуть список проектов с фильтрами по статусу и группе."""

    statuses = set(status) if status else None
    return repo.list_projects(include_archived=include_archived, group_id=group_id, statuses=statuses)


@app.post("/api/projects", response_model=Project, status_code=201)
def create_project(project: Project, repo: LocalRepository = Depends(get_repository)) -> Project:
    """Создать проект и связать его с группой."""

    if repo.get_group(project.group_id) is None:
        raise HTTPException(status_code=400, detail="Указанная продуктовая группа не найдена")

    return repo.add_project(project)


@app.get("/api/projects/{project_id}", response_model=Project)
def get_project(project_id: UUID, repo: LocalRepository = Depends(get_repository)) -> Project:
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


@app.put("/api/projects/{project_id}", response_model=Project)
def update_project(project_id: UUID, project: Project, repo: LocalRepository = Depends(get_repository)) -> Project:
    if repo.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if repo.get_group(project.group_id) is None:
        raise HTTPException(status_code=400, detail="Указанная продуктовая группа не найдена")
    aligned_project = project.model_copy(update={"id": project_id})
    return repo.update_project(project_id, aligned_project)


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
        return repo.add_gtm_stage(project_id, stage)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put("/api/projects/{project_id}/gtm-stages/{stage_id}", response_model=GTMStage)
def update_gtm_stage(project_id: UUID, stage_id: UUID, stage: GTMStage, repo: LocalRepository = Depends(get_repository)) -> GTMStage:
    aligned = stage.model_copy(update={"id": stage_id})
    try:
        return repo.update_gtm_stage(project_id, stage_id, aligned)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Этап GTM не найден")


@app.delete("/api/projects/{project_id}/gtm-stages/{stage_id}", status_code=204)
def delete_gtm_stage(project_id: UUID, stage_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_gtm_stage(project_id, stage_id)
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
        return repo.apply_gtm_template(project_id, template_id)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Шаблон GTM не найден")


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
        return repo.add_characteristic_section(project_id, section)
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
        return repo.update_characteristic_section(project_id, section_id, aligned)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Секция характеристик не найдена")


@app.delete(
    "/api/projects/{project_id}/characteristics/sections/{section_id}",
    status_code=204,
)
def delete_characteristic_section(project_id: UUID, section_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_characteristic_section(project_id, section_id)
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
        return repo.add_characteristic_field(project_id, section_id, field)
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
        return repo.update_characteristic_field(project_id, section_id, field_id, aligned)
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
    try:
        repo.delete_characteristic_field(project_id, section_id, field_id)
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
        return repo.apply_characteristic_template(project_id, template_id)
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
        return repo.copy_characteristics_structure(project_id, source_project_id)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message and str(project_id) in message:
            raise HTTPException(status_code=404, detail="Целевой проект не найден")
        raise HTTPException(status_code=404, detail="Проект-источник не найден")


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
        return repo.add_task(project_id, task)
    except KeyError:
        raise HTTPException(status_code=404, detail="Проект не найден")


@app.put("/api/projects/{project_id}/tasks/{task_id}", response_model=Task)
def update_task(project_id: UUID, task_id: UUID, task: Task, repo: LocalRepository = Depends(get_repository)) -> Task:
    aligned = task.model_copy(update={"id": task_id})
    try:
        return repo.update_task(project_id, task_id, aligned)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.delete("/api/projects/{project_id}/tasks/{task_id}", status_code=204)
def delete_task(project_id: UUID, task_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_task(project_id, task_id)
    except KeyError as exc:
        if "Project" in str(exc):
            raise HTTPException(status_code=404, detail="Проект не найден")
        raise HTTPException(status_code=404, detail="Задача не найдена")


@app.post("/api/projects/{project_id}/tasks/{task_id}/subtasks", response_model=Subtask, status_code=201)
def create_subtask(project_id: UUID, task_id: UUID, subtask: Subtask, repo: LocalRepository = Depends(get_repository)) -> Subtask:
    try:
        return repo.add_subtask(project_id, task_id, subtask)
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
        return repo.update_subtask(project_id, task_id, subtask_id, aligned)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "Task" in message:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        raise HTTPException(status_code=404, detail="Подзадача не найдена")


@app.delete("/api/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}", status_code=204)
def delete_subtask(project_id: UUID, task_id: UUID, subtask_id: UUID, repo: LocalRepository = Depends(get_repository)) -> None:
    try:
        repo.delete_subtask(project_id, task_id, subtask_id)
    except KeyError as exc:
        message = str(exc)
        if "Project" in message:
            raise HTTPException(status_code=404, detail="Проект не найден")
        if "Task" in message:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        raise HTTPException(status_code=404, detail="Подзадача не найдена")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def frontend_placeholder() -> str:
        """Заглушка, если фронтенд ещё не настроен."""

        return "<h1>Haier Project Tracker</h1><p>Фронтенд ещё не настроен.</p>"
