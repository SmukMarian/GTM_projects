"""Настройки приложения Haier Project Tracker."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


class AppSettings(BaseSettings):
    """Глобальные настройки приложения и путей хранения."""

    data_dir: Path = DATA_DIR
    primary_store: Path = DATA_DIR / "project_tracker.json"
    backups_dir: Path = DATA_DIR / "backups"
    files_dir: Path = DATA_DIR / "files"
    images_dir: Path = DATA_DIR / "images"

    model_config = SettingsConfigDict(env_prefix="HPT_", env_file=".env", env_file_encoding="utf-8")


settings = AppSettings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.backups_dir.mkdir(parents=True, exist_ok=True)
settings.files_dir.mkdir(parents=True, exist_ok=True)
settings.images_dir.mkdir(parents=True, exist_ok=True)
