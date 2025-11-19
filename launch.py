"""Удобный запуск Haier Project Tracker как локального приложения.

Скрипт поднимает сервер FastAPI через uvicorn и автоматически
открывает основную страницу в браузере по локальному адресу.
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn


def _open_browser(url: str, delay: float) -> None:
    """Открыть браузер после небольшой задержки.

    Задержка нужна, чтобы сервер успел подняться до первого запроса.
    """

    time.sleep(delay)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Запуск локального веб-приложения Haier Project Tracker")
    parser.add_argument("--host", default="127.0.0.1", help="Адрес для прослушивания (по умолчанию 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Порт для прослушивания (по умолчанию 8000)")
    parser.add_argument("--reload", action="store_true", help="Перезапускать сервер при изменениях кода (для разработки)")
    parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер автоматически")
    parser.add_argument(
        "--browser-delay",
        type=float,
        default=1.0,
        help="Задержка перед автозапуском браузера в секундах (по умолчанию 1.0)",
    )
    args = parser.parse_args()

    target_url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(target_url, args.browser_delay), daemon=True).start()

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
