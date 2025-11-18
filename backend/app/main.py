"""Базовый сервер Haier Project Tracker.

Этот модуль поднимает минимальное FastAPI-приложение, которое будет
обслуживать фронтенд и API. На данном этапе реализован только health-check
и раздача статических файлов из каталога ``frontend``.
"""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import ProductGroup, Project
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


@app.post("/api/groups", response_model=ProductGroup, status_code=201)
def create_group(group: ProductGroup, repo: LocalRepository = Depends(get_repository)) -> ProductGroup:
    """Создать продуктовую группу и сохранить её в файловом хранилище."""

    return repo.add_group(group)


@app.get("/api/projects", response_model=list[Project])
def list_projects(include_archived: bool = True, repo: LocalRepository = Depends(get_repository)) -> list[Project]:
    """Вернуть список проектов."""

    return repo.list_projects(include_archived=include_archived)


@app.post("/api/projects", response_model=Project, status_code=201)
def create_project(project: Project, repo: LocalRepository = Depends(get_repository)) -> Project:
    """Создать проект и связать его с группой."""

    groups = {g.id for g in repo.list_groups(include_archived=True)}
    if project.group_id not in groups:
        raise HTTPException(status_code=400, detail="Указанная продуктовая группа не найдена")

    return repo.add_project(project)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def frontend_placeholder() -> str:
        """Заглушка, если фронтенд ещё не настроен."""

        return "<h1>Haier Project Tracker</h1><p>Фронтенд ещё не настроен.</p>"
