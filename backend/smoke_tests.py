"""Быстрые регрессионные проверки API без запуска сервера.

Скрипт использует TestClient c временным хранилищем на диске, чтобы убедиться,
что основные сценарии не возвращают 500 и корректно пишутся логи.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient


def _configure_env(tmp: Path) -> None:
    os.environ["HPT_DATA_DIR"] = str(tmp)
    os.environ["HPT_PRIMARY_STORE"] = str(tmp / "store.json")
    os.environ["HPT_BACKUPS_DIR"] = str(tmp / "backups")
    os.environ["HPT_FILES_DIR"] = str(tmp / "files")
    os.environ["HPT_IMAGES_DIR"] = str(tmp / "images")
    os.environ["HPT_LOGS_DIR"] = str(tmp / "logs")


# Настраиваем окружение до импорта приложения
TEMP_DIR = Path(tempfile.mkdtemp(prefix="hpt_smoke_"))
_configure_env(TEMP_DIR)
sys.path.append(str(Path(__file__).resolve().parent))

from app.main import app  # noqa: E402

client = TestClient(app)


def _assert_ok(resp, context: str) -> dict:
    if resp.status_code >= 500:
        raise AssertionError(f"{context}: unexpected {resp.status_code} — {resp.text}")
    return resp.json() if resp.text else {}


def run_smoke() -> Path:
    # Группа
    group = _assert_ok(
        client.post(
            "/api/groups",
            json={"name": "Smoke Group", "description": "", "status": "active", "brands": ["Test"], "extra_fields": {}},
        ),
        "create group",
    )
    group_id = UUID(group["id"])

    # Проект
    project = _assert_ok(
        client.post(
            "/api/projects",
            json={
                "group_id": str(group_id),
                "name": "Smoke Project",
                "brand": "Test",
                "market": "RU",
                "status": "active",
                "short_description": "",
                "full_description": "",
                "planned_launch": date.today().isoformat(),
            },
        ),
        "create project",
    )
    project_id = UUID(project["id"])
    fetched = _assert_ok(client.get(f"/api/projects/{project_id}"), "get project")
    if fetched.get("name") != "Smoke Project":
        raise AssertionError("project payload mismatch")

    # GTM этапы
    stage = _assert_ok(
        client.post(
            f"/api/projects/{project_id}/gtm-stages",
            json={"title": "Stage A", "description": "", "order": 1, "status": "in_progress"},
        ),
        "create stage",
    )
    stage_id = UUID(stage["id"])
    _assert_ok(
        client.put(
            f"/api/projects/{project_id}/gtm-stages/{stage_id}",
            json={
                "id": str(stage_id),
                "title": "Stage A",
                "description": "Updated",
                "order": 1,
                "status": "done",
                "planned_start": date.today().isoformat(),
                "planned_end": date.today().isoformat(),
            },
        ),
        "update stage",
    )

    # Характеристики
    section = _assert_ok(
        client.post(
            f"/api/projects/{project_id}/characteristics/sections",
            json={"title": "Main", "description": "", "order": 1},
        ),
        "create characteristic section",
    )
    section_id = UUID(section["id"])
    field = _assert_ok(
        client.post(
            f"/api/projects/{project_id}/characteristics/sections/{section_id}/fields",
            json={
                "label_ru": "Цвет",
                "label_en": "Color",
                "type": "text",
                "value_ru": "Белый",
                "value_en": "White",
                "order": 1,
            },
        ),
        "create characteristic field",
    )
    field_id = UUID(field["id"])
    _assert_ok(
        client.put(
            f"/api/projects/{project_id}/characteristics/sections/{section_id}/fields/{field_id}",
            json={
                "id": str(field_id),
                "label_ru": "Цвет",
                "label_en": "Color",
                "type": "text",
                "value_ru": "Чёрный",
                "value_en": "Black",
                "order": 1,
            },
        ),
        "update characteristic field",
    )

    # Задачи и подзадачи
    task = _assert_ok(
        client.post(
            f"/api/projects/{project_id}/tasks",
            json={
                "title": "Test task",
                "status": "todo",
                "description": "",
                "order": 1,
                "gtm_stage_id": str(stage_id),
            },
        ),
        "create task",
    )
    task_id = UUID(task["id"])
    subtask = _assert_ok(
        client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/subtasks",
            json={"title": "Subtask", "order": 1},
        ),
        "create subtask",
    )
    subtask_id = UUID(subtask["id"])
    _assert_ok(
        client.put(
            f"/api/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}",
            json={"id": str(subtask_id), "title": "Subtask", "order": 1, "done": True},
        ),
        "complete subtask",
    )

    # Комментарии
    comment = _assert_ok(
        client.post(
            f"/api/projects/{project_id}/comments",
            json={"text": "Первый комментарий"},
        ),
        "create comment",
    )
    comment_id = UUID(comment["id"])
    _assert_ok(
        client.put(
            f"/api/projects/{project_id}/comments/{comment_id}",
            json={"id": str(comment_id), "text": "Обновлено"},
        ),
        "update comment",
    )

    # Бэкап
    _assert_ok(client.post("/api/backups"), "create backup")
    backups = _assert_ok(client.get("/api/backups"), "list backups")
    if not backups:
        raise AssertionError("backup not created")

    log_path = TEMP_DIR / "logs" / "app.log"
    if log_path.exists():
        errors = [line for line in log_path.read_text(encoding="utf-8").splitlines() if " 500 " in line or "ERROR" in line]
        if errors:
            raise AssertionError(f"log contains errors: {errors[:3]}")
    return log_path


if __name__ == "__main__":
    path = run_smoke()
    print(f"Smoke tests passed. Log file: {path}")
