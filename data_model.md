# Projects Tracker — Модель данных

Текстовое описание сущностей и связей согласно `Haier_Project_Tracker_TZ.md`. Служит ориентиром для реализации хранилища и API.

## Сущности

### Продуктовая группа
- `id` (UUID)
- `name` — название группы.
- `description` — описание (опционально).
- `status` — `active` / `archived`.
- `brands` — список брендов, относящихся к группе.
- `extra_fields` — словарь пользовательских полей.

### Проект
- `id` (UUID)
- `group_id` — ссылка на продуктовую группу.
- `name` — название проекта.
- `brand` — бренд проекта.
- `market` — рынок/регион.
- `short_description`, `full_description`.
- `status` — `active` / `closed` / `archived`.
- `current_gtm_stage_id` — текущий этап GTM.
- `planned_launch`, `actual_launch` — даты запуска.
- `priority` — `low` / `medium` / `high` (опционально).
- `custom_fields` — пользовательские поля.
- `gtm_stages` — список этапов (структура ниже).
- `tasks` — задачи проекта.
- `characteristics` — секции характеристик.
- `files` — файлы проекта.
- `images` — изображения и обложка.
- `comments` — общие комментарии к проекту.
- `history` — лента изменений.

### GTM-этап
- `id` (UUID)
- `title`, `description`.
- `order` — порядковый номер в проекте.
- `planned_start`, `planned_end` — плановые даты.
- `actual_end` — фактическое завершение.
- `status` — `not_started` / `in_progress` / `done` / `cancelled`.
- `risk_flag` — флаг риска (ручной или по просрочке).
- `checklist` — список `ChecklistItem`.

### Шаблон GTM-этапов
- `id` (UUID)
- `name`, `description`.
- `stages` — список этапов с порядком.

### Задача
- `id` (UUID)
- `title`, `description`.
- `status` — `todo` / `in_progress` / `done`.
- `due_date` — срок выполнения.
- `important` — признак важности.
- `gtm_stage_id` — привязка к GTM-этапу (опционально).
- `subtasks` — список подзадач.
- `comments` — комментарии к задаче.

### Подзадача
- `id` (UUID)
- `title` — текст подзадачи.
- `done` — флаг выполнения.
- `order` — порядок внутри задачи.

### Характеристики
- Представлены как список секций `CharacteristicSection`.
- Секция:
  - `id` (UUID)
  - `title`
  - `order`
  - `fields` — список `CharacteristicField`.
- Поле:
  - `id` (UUID)
  - `label_ru`, `label_en`
  - `value_ru`, `value_en` — строка, число, булево значение или `null`
  - `field_type` — `text` / `number` / `select` / `checkbox` / `other`.
  - `order`

### Шаблон характеристик
- `id` (UUID)
- `name`, `description`.
- `sections` — список секций с полями и типами.

### Файл
- `id` (UUID)
- `name`
- `description`
- `category` — настраиваемый тип (техдок, маркетинг и др.).
- `uploaded_at` — дата загрузки.
- `path` — путь к файлу на диске.

### Изображение
- `id` (UUID)
- `filename`
- `caption` — подпись.
- `uploaded_at` — дата загрузки.
- `order` — порядок в галерее.
- `is_cover` — флаг «обложка».
- `path` — путь к файлу.

### Комментарий
- `id` (UUID)
- `text`
- `created_at`

### История изменений
- `id` (UUID)
- `occurred_at`
- `summary` — краткое описание события.
- `details` — дополнительные детали (опционально).

### Экспорт проекта (агрегация)
- `name`, `group_name`, `brand`, `status`, `planned_launch`, `current_gtm_stage`.

## Связи
- Продуктовая группа `1→N` Проекты.
- Проект `1→N` GTM-этапы.
- Проект `1→N` Задачи.
- Задача `1→N` Подзадачи.
- Проект `1→N` Секции характеристик, секция `1→N` Поля.
- Проект `1→N` Файлы.
- Проект `1→N` Изображения.
- Проект `1→N` Комментарии.
- Проект `1→N` Записи истории.
- Шаблон GTM содержит `N` этапов, шаблон характеристик содержит `N` секций/полей.

## Примечания по хранению
- Данные хранятся локально в одном файле `project_tracker.json`; резервные копии — в `data/backups/`.
- Все идентификаторы — UUID.
- Путь и названия файлов конфигурируются через переменные окружения с префиксом `HPT_` (см. `backend/app/config.py`).
