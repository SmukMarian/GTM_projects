# Haier Project Tracker

Локальное веб-приложение для личного ведения проектов по запуску новых продуктов на рынок. Основной источник требований — файл
`Haier_Project_Tracker_TZ.md` в корне репозитория.

## Структура

- `backend/` — минимальный сервер на FastAPI, сейчас отдаёт health-check и статику, содержит модели данных, файловое хранилище и настройки путей хранения.
- `frontend/` — заглушка главной страницы, раздаётся сервером как статический контент.
- `Haier_Project_Tracker_TZ.md` — полное ТЗ.
- `project-plan.md` — план реализации.
- `dev_tasks.md` — чек-лист задач.
- `data_model.md` — текстовая схема сущностей и связей.

### Хранилище и бэкапы

- Основной файл данных: `data/project_tracker.json` (создаётся автоматически).
- Резервные копии сохраняются в `data/backups/` и именуются `project_tracker_<UTC-метка>.json`.
- Файлы можно копировать вручную для дополнительного бэкапа вне приложения.

## Локальный запуск (черновой)

1. Установить зависимости backend: `pip install -r backend/requirements.txt`.
2. Запустить сервер: `uvicorn backend.app.main:app --reload`.
3. Открыть в браузере `http://127.0.0.1:8000` — будет отображена заглушка фронтенда.

Дальнейшие шаги: расширить API и фронтенд по ТЗ, добавить импорт/экспорт и резервное копирование.

### Минимальные API-эндпоинты (черновик)

- `GET /api/groups` — список продуктовых групп (можно скрывать архивные через `include_archived=false`).
- `GET /api/groups/{group_id}` — получение одной группы.
- `POST /api/groups` — создание группы. Принимает `ProductGroup`.
- `PUT /api/groups/{group_id}` — обновление группы по идентификатору.
- `DELETE /api/groups/{group_id}` — удаление группы; если есть связанные проекты, вернёт ошибку 400.
- `GET /api/projects` — список проектов; поддерживает фильтры `include_archived`, `group_id`, `status` (можно несколько значений).
- `GET /api/export/projects` — экспорт списка проектов в Excel; поддерживает `include_archived` и несколько `status`.
- `GET /api/projects/{project_id}` — получение проекта по id.
- `POST /api/projects` — создание проекта, валидирует наличие группы.
- `PUT /api/projects/{project_id}` — обновление проекта; валидирует группу.
- `DELETE /api/projects/{project_id}` — удаление проекта.
- `GET /api/gtm-templates` — список шаблонов GTM.
- `POST /api/gtm-templates` — создание шаблона GTM.
- `PUT /api/gtm-templates/{template_id}` — обновление шаблона GTM.
- `DELETE /api/gtm-templates/{template_id}` — удаление шаблона GTM.
- `GET /api/characteristic-templates` — список шаблонов характеристик.
- `POST /api/characteristic-templates` — создание шаблона характеристик.
- `PUT /api/characteristic-templates/{template_id}` — обновление шаблона характеристик.
- `DELETE /api/characteristic-templates/{template_id}` — удаление шаблона характеристик.
- `GET /api/projects/{project_id}/gtm-stages` — список GTM-этапов проекта.
- `POST /api/projects/{project_id}/gtm-stages` — добавление GTM-этапа в проект.
- `PUT /api/projects/{project_id}/gtm-stages/{stage_id}` — обновление GTM-этапа проекта.
- `DELETE /api/projects/{project_id}/gtm-stages/{stage_id}` — удаление GTM-этапа проекта.
- `POST /api/projects/{project_id}/gtm-stages/apply-template?template_id=` — заменить этапы проекта этапами шаблона.
- `GET /api/projects/{project_id}/characteristics/sections` — список секций характеристик проекта.
- `POST /api/projects/{project_id}/characteristics/sections` — добавление секции характеристик.
- `PUT /api/projects/{project_id}/characteristics/sections/{section_id}` — обновление секции характеристик.
- `DELETE /api/projects/{project_id}/characteristics/sections/{section_id}` — удаление секции характеристик.
- `POST /api/projects/{project_id}/characteristics/sections/{section_id}/fields` — добавление поля в секцию.
- `PUT /api/projects/{project_id}/characteristics/sections/{section_id}/fields/{field_id}` — обновление поля характеристики.
- `DELETE /api/projects/{project_id}/characteristics/sections/{section_id}/fields/{field_id}` — удаление поля характеристики.
- `POST /api/projects/{project_id}/characteristics/apply-template?template_id=` — заменить структуру характеристик проектом из шаблона (значения обнуляются).
- `POST /api/projects/{project_id}/characteristics/copy-structure?source_project_id=` — скопировать структуру секций/полей из другого проекта без значений.
- `GET /api/projects/{project_id}/tasks` — список задач проекта с фильтрами `status`, `only_active`, `gtm_stage_id`.
- `POST /api/projects/{project_id}/tasks` — создание задачи.
- `PUT /api/projects/{project_id}/tasks/{task_id}` — обновление задачи (включая смену статуса или даты).
- `DELETE /api/projects/{project_id}/tasks/{task_id}` — удаление задачи.
- `POST /api/projects/{project_id}/tasks/{task_id}/subtasks` — добавление подзадачи.
- `PUT /api/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}` — обновление подзадачи (например, отметка выполнено).
- `DELETE /api/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}` — удаление подзадачи.
- `GET /api/projects/{project_id}/files` — список файлов проекта.
- `POST /api/projects/{project_id}/files` — добавление файла (метаданные и путь).
- `PUT /api/projects/{project_id}/files/{file_id}` — обновление описания/категории/имени файла.
- `DELETE /api/projects/{project_id}/files/{file_id}` — удаление файла.
- `GET /api/projects/{project_id}/images` — список изображений проекта.
- `POST /api/projects/{project_id}/images` — добавление изображения (метаданные, подпись, флаг обложки).
- `PUT /api/projects/{project_id}/images/{image_id}` — обновление изображения/подписи/обложки.
- `DELETE /api/projects/{project_id}/images/{image_id}` — удаление изображения.
- `GET /api/projects/{project_id}/comments` — комментарии к проекту.
- `POST /api/projects/{project_id}/comments` — добавить комментарий к проекту.
- `DELETE /api/projects/{project_id}/comments/{comment_id}` — удалить комментарий проекта.
- `GET /api/projects/{project_id}/tasks/{task_id}/comments` — комментарии к задаче.
- `POST /api/projects/{project_id}/tasks/{task_id}/comments` — добавить комментарий к задаче.
- `DELETE /api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}` — удалить комментарий задачи.
- `GET /api/projects/{project_id}/history` — лента истории проекта.
- `POST /api/projects/{project_id}/history` — добавить событие в историю.
- `DELETE /api/projects/{project_id}/history/{event_id}` — удалить событие истории.
- `GET /api/backups` — список резервных копий.
- `POST /api/backups` — создать резервную копию текущего хранилища.
- `POST /api/backups/restore` — восстановить данные из резервной копии по имени файла.
