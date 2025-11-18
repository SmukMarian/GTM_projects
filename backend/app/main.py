"""Базовый сервер Haier Project Tracker.

Этот модуль поднимает минимальное FastAPI-приложение, которое будет
обслуживать фронтенд и API. На данном этапе реализован только health-check
и раздача статических файлов из каталога ``frontend``.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Haier Project Tracker", version="0.1.0")


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Простейший health-check эндпоинт."""

    return {"status": "ok"}


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def frontend_placeholder() -> str:
        """Заглушка, если фронтенд ещё не настроен."""

        return "<h1>Haier Project Tracker</h1><p>Фронтенд ещё не настроен.</p>"
