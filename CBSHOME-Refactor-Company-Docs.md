# CBSHOME -- Refactor: Company Attachments, Templates & Purchase Docs

**Версия:** 0.5 / decision-locked
**Дата:** 10 мая 2026

**Статус:** дизайн зафиксирован, дальше -- только реализация. Изменения в этом документе допускаются только через явный поворот решения (через обсуждение и новый changelog в issue/PR).

**Changelog v0.5 (10 May 2026):**
- Bootstrap path для platform default templates: `backend/seed/templates/_default/` -> `backend/scripts/seed_data/templates/_default/` (§1.4, §4.9, §10). Causes: `backend/seed/` в корне backend выпадал из существующей структуры (всё под `app/` или `scripts/`). Seed-данные кладутся рядом с seed-скриптами под `scripts/seed_data/`.
- "Sentry" заменён на "structlog + audit event" во всём документе (§5.1, §10). Causes: Sentry в проекте не подключен, alarm-канал -- structlog (структурный лог) + audit_log row.
- §2.1 список public API storage layer обновлён под реальную реализацию iter 2.1 (добавлены `get_object_bytes`, `list_objects`, `download_filename` и `content_length` kwargs).
- §3.5 убрано устаревшее "(или новый permission, см. Q-ATT-1)" -- Q-ATT-1 закрыт.
- §3.4 убрано "TBD, см. Q-ATT-2" -- Q-ATT-2 закрыт (rate-limits зафиксированы в §10).
- §3.7 + §4.8 reconcile-описание: вместо "`mc cp` + `mc rm`" указано "через storage layer (`upload_object` + `delete_object`)" -- reconcile это Python-скрипт, mc CLI ему не доступен.
- §4.10 убрана несуществующая env `MINIO_TEMPLATE_CACHE_TTL=0`. Конкретный механизм отключения кэша в тестах -- через monkeypatch константы `TEMPLATE_HTML_CACHE_TTL_SECONDS`. Уточнено что Redis-клиент имеет `decode_responses=True`, поэтому HTML кэшируется как base64-encoded строка.
- §5.2 устаревшая двухступенчатая fallback-логика заменена ссылкой на §4.7 (4 ступени с platform default).
- Маркеры реализации проставлены в §2 (✓ iter 2.1), §3 (✓ iter 2.2), §4 (в работе iter 2.3), §5 (впереди iter 2.4).

**Связанные документы:**
- `CBSHOME-Refactor-Investor-Market-And-Staff.md` v0.3 -- параллельный рефакторинг. **Двусторонняя зависимость:** этот документ предоставляет storage layer (§2), которым пользуются и attachments здесь, и roadmap covers в Refactor 1 §5.5. Refactor 1 §1.6 определяет public investor flow, в котором public attachments из этого документа отображаются на public-странице компании.
- `CBSHOME-Design-Document.md` -- Конституция v1.5
- `CBSHOME-Backend.md` -- Backend ТЗ v3.6
- `CBSHOME-Frontend.md` -- Frontend ТЗ v2.7
- `CBSHOME-Financial-System.md` -- §11 "Документ на каждую покупку" (текущая спецификация, расходится с реализацией)

---

## 0. Контекст и цели

### 0.1. Что не так сейчас

Заказчик не может запустить продажи -- юридически нельзя продавать опционы, не предоставив инвестору доказательство легитимности компании (сертификат инкорпорации + лицензия на выпуск ценных бумаг). Текущая система этого не умеет:

- Нет хранилища произвольных файлов компании (бизнес-лицензии, презентации, патенты, ванпейджеры).
- Sprint 9.2 реализовал `GET /api/v1/purchases/{id}/certificate` с **одним глобальным шаблоном** на все компании (`backend/app/modules/purchases/templates/certificate.html`). Это технически работает, но семантически ломается:
  - Компании юридически разные -- у каждой свой подписант, своя печать, свой шаблон договора.
  - Один эндпоинт смешивает две сущности: договор покупки (per-Purchase, юридически фиксированный) и сертификат владения (агрегат по компании, актуальный на текущий момент).
  - Нет per-Purchase snapshot шаблона -- если Staff обновит шаблон, исторические покупки начнут рендериться "по-новому", что юридически недопустимо.
- Семафор S-07 (`Все Purchase имеют document_id NOT NULL`) описан в `CBSHOME-Financial-System.md`, но в коде нет ни поля, ни проверки.

### 0.2. Цели рефакторинга

Закрыть три задачи в одном цикле:

1. **Хранилище файлов компании** (`company_attachments`) -- бизнес-лицензии, сертификаты, презентации, любые "бумажки". MinIO как storage, метаданные в Postgres, прокачка через backend (private bucket + presigned URLs).
2. **Шаблоны юридических документов на компанию** (`company_doc_templates`) -- per-company HTML/Jinja2 шаблоны для договоров покупки и сертификатов владения. Staff редактирует через UI.
3. **Починка Purchase docs** -- snapshot шаблона на момент покупки, разделение `agreement` (per-Purchase) и `ownership_certificate` (per investor-company aggregate), новые эндпоинты.

### 0.3. Инфраструктура -- начинаем со скрипта

Заказчик ждёт от нас один артефакт: `install_cbshome.sh`. Это означает: всё новое окружение должно подниматься одним запуском без ручных шагов после установки. MinIO встаёт в `docker-compose.yml` рядом с postgres/redis и поднимается автоматически. Новые секции в management-скрипте `cbshome` (backup/restore с учётом MinIO) -- обязательны.

### 0.4. Что НЕ делаем в этом рефакторе

- **Программные guard'ы на покупку** при отсутствии бизнес-лицензии. Контроль процедурный: Staff обязан загрузить документы перед активацией компании. На старте 3 компании, проверяется глазами + чеклистом.
- **Antivirus scanning** загруженных файлов (ClamAV) -- post-MVP, follow-up.
- **OCR / автоматическое извлечение метаданных** из PDF -- post-MVP.
- **DocuSign integration** (TD-005) -- остаётся в backlog.
- **Public bucket policy** в MinIO -- не делаем. Все файлы приватные на уровне MinIO, доступ только через backend (с auth или без -- зависит от `is_public` флага).

---

## 1. Инфраструктура: MinIO + install_cbshome.sh

### 1.1. MinIO в docker-compose

**✓ Реализовано (iter 1).**

Новый сервис `minio` в существующем `docker-compose.yml`:

- Образ `minio/minio:latest`.
- Команда `server /data --console-address ":9001"`.
- Порты:
  - `127.0.0.1:9000:9000` -- S3 API. Loopback-only, наружу не выставляем; доступ только через backend (по docker-сети `http://minio:9000`).
  - `127.0.0.1:9001:9001` -- Web UI (Object Browser, см. https://min.io/docs/minio/linux/operations/installation.html). Loopback на уровне docker, наружу проксируется через nginx (см. §1.4) под доменом `storage-mc-admin.cbshome.org` с basic-auth.
- Volume `cbshome_minio_data:/data`.
- Healthcheck: `curl -f http://localhost:9000/minio/health/live`.
- Restart `unless-stopped`.
- env_file -- `./backend/.env` (читает `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`).

### 1.2. Init-сервис для bucket

**✓ Реализовано (iter 1).**

Отдельный one-shot сервис `minio-init` (запускается с `restart: "no"`), который через `mc` (mc -- official MinIO client) создаёт bucket'ы и применяет policy:

```
mc alias set local http://minio:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
mc mb -p local/cbshome-attachments
mc anonymous set none local/cbshome-attachments  # explicitly private
```

Запускается каждый раз вместе с `docker compose up -d`. Идемпотентен -- повторный запуск ничего не ломает.

### 1.3. Конфиг (backend/.env)

**✓ Реализовано (iter 1).**

Добавляются переменные:

| Переменная | Назначение | Пример |
|------------|------------|--------|
| `MINIO_ROOT_USER` | admin login | сгенерированный 16 chars |
| `MINIO_ROOT_PASSWORD` | admin password | сгенерированный 32 chars |
| `MINIO_ENDPOINT` | URL для backend клиента | `http://minio:9000` |
| `MINIO_ACCESS_KEY` | service account для backend (не root) | сгенерированный |
| `MINIO_SECRET_KEY` | service account secret | сгенерированный |
| `MINIO_BUCKET` | имя бакета | `cbshome-attachments` |
| `MINIO_REGION` | region для S3 SDK | `us-east-1` (default) |
| `MINIO_PRESIGNED_TTL_AUTH` | TTL presigned для auth flow | `900` (15 мин) |
| `MINIO_PRESIGNED_TTL_PUBLIC` | TTL presigned для public flow | `86400` (24 ч) |
| `MINIO_MAX_FILE_SIZE_MB` | hard limit на размер файла | `100` |
| `MINIO_CONSOLE_BASIC_AUTH_PASSWORD` | пароль для basic-auth nginx перед Web UI | сгенерированный 32 chars |

Service account (`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`) создаётся `minio-init`-сервисом отдельно от root credentials -- backend никогда не использует root.

Login для basic-auth перед Web UI -- фиксированный `admin`. `.htpasswd` генерируется в `install_cbshome.sh` из `MINIO_CONSOLE_BASIC_AUTH_PASSWORD` и кладётся по пути `/etc/nginx/.htpasswd-storage-mc-admin`.

### 1.4. install_cbshome.sh -- что добавляется

**◐ Реализовано частично (iter 1).** Открыто: seed platform default templates -- `mc cp -r backend/scripts/seed_data/templates/_default/ ...` и `python backend/scripts/seed_platform_templates.py`. Закрывается в iter 2.3.

Новая секция в скрипте после `Mail Server`, перед `Docker Stack`:

- Генерация всех `MINIO_*` переменных через `openssl rand` (включая `MINIO_CONSOLE_BASIC_AUTH_PASSWORD`).
- Inject в `backend/.env` (рядом с `POSTGRES_PASSWORD`, `REDIS_PASSWORD`).
- Создание `.htpasswd` для basic-auth: `htpasswd -cb /etc/nginx/.htpasswd-storage-mc-admin admin "$MINIO_CONSOLE_BASIC_AUTH_PASSWORD"`.
- Создание nginx-конфига `/etc/nginx/sites-available/storage-mc-admin.cbshome.org`:
  - `server_name storage-mc-admin.cbshome.org`
  - `auth_basic "MinIO Console"`
  - `auth_basic_user_file /etc/nginx/.htpasswd-storage-mc-admin`
  - `proxy_pass http://127.0.0.1:9001`
  - `client_max_body_size 100M` (для upload через Web UI)
  - стандартные `proxy_set_header` для X-Real-IP, X-Forwarded-For, Host, X-Forwarded-Proto.
  - WebSocket upgrade headers (`Upgrade`, `Connection`) -- Console использует WS для real-time updates.
- Symlink в `sites-enabled` + `nginx -t && systemctl reload nginx`.
- `certbot --nginx -d storage-mc-admin.cbshome.org` -- получение TLS-сертификата.
- В шаге запуска стека `docker compose up -d` явно ждём healthcheck сервиса `minio` перед запуском `app` (зависимость в compose).
- В шаге миграций -- стандартный alembic upgrade head (новые миграции для таблиц `company_attachments`, `company_document_templates` плюс поле `purchase_agreement_template_id` в `purchases`).
- **Новый шаг -- seed platform default templates (см. §4.9):**
  1. `mc cp -r backend/scripts/seed_data/templates/_default/ local/cbshome-attachments/_platform/templates/` -- копирует HTML + ассеты (logo placeholder, signature placeholder, stamp placeholder) для всех 4 kind'ов и поддерживаемых языков (en/de/ru/ar) в MinIO под префикс `_platform/templates/`.
  2. `python backend/scripts/seed_platform_templates.py` -- создаёт rows в `company_document_templates` с `company_id=NULL`, `status=active`, `storage_prefix='_platform/templates/<kind>/<lang>/'` для каждой пары `(kind, language)`. Идемпотентен -- повторный запуск не создаёт дубли.

После этого backend стартует с гарантированным fallback'ом для рендера договоров и сертификатов: даже свежесозданная компания без своих кастомных шаблонов получает рабочий рендер через platform default.

**DNS pre-flight check.** В существующем DNS-checker'e скрипта (там уже проверяются `cbshome.org`, `api.cbshome.org`, `mail.cbshome.org`) добавляется проверка `storage-mc-admin.cbshome.org` -> сервер IP. Без A-записи certbot упадёт на HTTP-01 challenge, скрипт это ловит и сообщает понятным сообщением "Добавь A-запись `storage-mc-admin.cbshome.org` -> `<server-ip>` и перезапусти install".

DNS-запись -- одна A-запись на тот же IP сервера, что у других поддоменов:

```
storage-mc-admin.cbshome.org    A    <server-ip>    TTL 300
```

AAAA / CAA / TXT для этого поддомена не требуются.

### 1.5. cbshome management script -- что меняется

**◐ Реализовано частично (iter 1).** Сделаны: backup с `mc mirror`, status с healthcheck minio, `logs minio`, `storage stats`, `storage console`. Открыто: `storage reconcile`, `storage reconcile-templates`, `storage reconcile-platform-templates` -- сейчас stub'ы, печатают "next iteration"; реальные команды появляются вместе с Python-скриптами в iter 2.1 / 2.2 / 2.3 соответственно.

`cbshome backup` сейчас делает только `pg_dump` + копию `.env`. Расширяется:

- Добавляется `mc mirror local/cbshome-attachments /tmp/minio_backup_$TIMESTAMP/`.
- Архив включает MinIO snapshot.
- Rotation -- те же 7 дней.

`cbshome status` -- добавляется проверка контейнера `minio` (healthcheck).

`cbshome logs minio` -- новый case в `case_logs`.

Новая команда `cbshome storage`:

- `cbshome storage stats` -- размер бакета, количество объектов (через `mc du`, `mc ls --recursive | wc -l`).
- `cbshome storage console` -- печатает URL и credentials Web UI, чтобы Staff/админу не лазить в `.env`:
  ```
  MinIO Console:  https://storage-mc-admin.cbshome.org
  Login:          admin
  Password:       <значение MINIO_CONSOLE_BASIC_AUTH_PASSWORD из .env>
  ```
- `cbshome storage reconcile <company_id>` -- сканирует MinIO inbox компании, создаёт rows в `company_attachments` (см. §3.7). Опции:
  - `--all` -- по всем компаниям.
  - `--dry-run` -- показать что было бы сделано, без записи.
  - `--orphans-only` -- только направление MinIO -> БД (orphan-объекты без rows).
  - `--broken-only` -- только направление БД -> MinIO (rows со ссылкой на несуществующий объект).
- `cbshome storage reconcile-templates <company_id>` -- сканирует `companies/{id}/templates-inbox/`, переносит набор файлов template'а (HTML + ассеты) в canonical path `companies/{id}/templates/<kind>/<lang>/`, создаёт/обновляет row в `company_document_templates` (см. §4.8). Опции `--all`, `--dry-run`.
- `cbshome storage reconcile-platform-templates` -- сканирует `_platform/templates-inbox/`, переносит файлы в `_platform/templates/<kind>/<lang>/`, обновляет platform default row с `company_id=NULL` (см. §4.9). Используется когда юристы платформы правят общий шаблон. Опция `--dry-run`.

Под капотом эти команды запускают соответствующие Python-скрипты в `backend/scripts/` через `docker compose exec`.

### 1.6. Размеры и лимиты

**✓ Реализовано (iter 1).**

- Initial volume для MinIO -- `20GB`. На три компании по 5-10 файлов (1-30MB каждый) хватит с большим запасом. Отдельный volume, не общий с postgres.
- Max file size -- `100MB`. Применяется в трёх местах: nginx `client_max_body_size`, backend Pydantic-валидатор `Field(max_length=...)` на `multipart/form-data`, MinIO принимает любой размер.
- MinIO bucket versioning -- **OFF**. Перезаливание файла перезаписывает старую версию. Если юристам потребуется история -- включаем потом отдельной задачей.
- Retention/lock policy -- не настраиваем.

## 2. Backend: Storage abstraction layer

**✓ Реализовано (iter 2.1).** Все четыре подраздела закрыты, тесты против реального MinIO зелёные.

### 2.1. Новый модуль `app/core/storage.py`

Тонкая обёртка над `aiobotocore` для работы с MinIO как S3. Backend нигде в business-коде не должен знать про MinIO напрямую -- всегда через этот слой.

Public API (фактическая реализация iter 2.1):
- `upload_object(key: str, data: bytes | BinaryIO, content_type: str, *, content_length: int | None = None) -> str` -- кладёт объект (поддержка bytes и потоковая загрузка через BinaryIO + явный Content-Length для multipart-router пути), возвращает stored key.
- `delete_object(key: str) -> None` -- удаляет, идемпотентен на missing key.
- `generate_presigned_url(key: str, ttl_seconds: int, *, download_filename: str | None = None) -> str` -- presigned GET для скачивания. `download_filename` задаёт `Content-Disposition: attachment; filename=...` через `ResponseContentDisposition` -- защита от stored-XSS на download-эндпоинтах.
- `object_exists(key: str) -> bool` -- проверка наличия (с disambiguation missing key vs missing bucket).
- `get_object_metadata(key: str) -> dict` -- HEAD объекта (size, last_modified, content_type).
- `get_object_bytes(key: str) -> bytes` -- выкачивает payload в bytes. Используется reconcile-скриптами и (в перспективе iter 2.3) кэшем HTML template'ов.
- `list_objects(prefix: str) -> list[str]` -- список keys по префиксу. Используется reconcile-скриптами для скана inbox'а.

Исключения: `StorageError` (общая ошибка upstream), `StorageNotFoundError` (для `get_object_*` на missing key).

Все функции -- async. Используют общий `aiobotocore.session()` через connection pool.

Конфигурация читается из `app/core/config.py` (Pydantic Settings) -- те же `MINIO_*` переменные.

### 2.2. Object key naming

Иерархическая структура ключей (без слешей в концах названий):

```
# Per-company files
companies/<company_id>/attachments/<attachment_id>/<original_filename>   # static files
companies/<company_id>/inbox/<slug>.<ext>                                # attachments inbox
companies/<company_id>/inbox/<slug>.<ext>.cbsmeta.json                   # companion metadata
companies/<company_id>/roadmap/<item_id>/cover.<ext>                     # roadmap covers
companies/<company_id>/templates/<kind>/<lang>/template.html             # per-company template HTML
companies/<company_id>/templates/<kind>/<lang>/<asset>.{png,jpg}         # template assets (logo, signature, stamp)
companies/<company_id>/templates-inbox/<kind>__<lang>/template.html      # templates inbox
companies/<company_id>/templates-inbox/<kind>__<lang>/<asset>.{png,jpg}
companies/<company_id>/templates-inbox/<kind>__<lang>/_meta.cbsmeta.json # template metadata

# Platform-wide defaults (see §4.9)
_platform/templates/<kind>/<lang>/template.html                          # platform default template
_platform/templates/<kind>/<lang>/<asset>.{png,jpg}                      # platform default assets (placeholders)
_platform/templates-inbox/<kind>__<lang>/...                             # for platform-level updates
```

Привязка к UUID для `attachments` гарантирует уникальность; для template'ов используется **canonical path** (один active template на пару `(kind, language)`), потому что версионирование делает БД (через `status=archived` row), а в MinIO можно перезатирать.

Storage layer используется в нескольких местах:
- Attachments (этот документ §3) -- произвольные файлы компании.
- Roadmap covers (Refactor 1 §5.5) -- обложки для roadmap-items.
- Templates per-company (§4) -- HTML + ассеты per company per (kind, language).
- Templates platform default (§4.9) -- HTML + placeholder-ассеты на префиксе `_platform/`.

### 2.3. Зависимости

Добавляется в `pyproject.toml`:
- `aiobotocore>=2.13.0,<3.0`

Это тянет `botocore`, `aiohttp`, `aioitertools` -- стандартный набор. Без `boto3` (синхронный, не нужен).

### 2.4. Тесты

В тестах используется реальный MinIO (тот же контейнер, что в production-стеке -- `docker-compose.yml` уже включает minio + minio-init). Никакого `moto`, никакого мока -- реальный путь обнаружит больше edge cases (multipart, presigned, ACL).

Тестовый bucket -- отдельный, `cbshome-attachments-test`, создаётся `minio-init` рядом с основным. Очищается перед каждым тестом через fixture (mc rm --recursive --force, либо через aiobotocore list_objects + delete).

## 3. Backend: модуль `company_attachments`

**✓ Реализовано (iter 2.2).** Все подразделы закрыты. Deviations от спеки:
- §3.7 reconcile-скрипт реализован чисто на Python через storage layer (`upload_object` / `delete_object`), не через `mc cp` / `mc rm`. Спека уточнена в этом документе.
- §3.7 missing sidecar при reconcile = skip + WARNING (как в спеке). Mismatched mime по filename = skip + ERROR (через единый валидатор `validate_attachment_mime_by_filename` в `companies/service.py`, разделяемый router'ом и reconcile'ом).
- 100MB upload limit -- валидируется на уровне nginx (`client_max_body_size 100M`). Backend не дублирует -- предложение в спеке про "Pydantic-валидатор `Field(max_length=...)` на multipart" не было реализовано (multipart body нельзя валидировать через Pydantic length-limit без буферизации в память; nginx ловит раньше, дешевле).
- Auth-flow GET download дополнительно фильтрует `is_published=True`. Спека этого явно не требовала, но без фильтра investor с прямой ссылкой мог бы скачать draft. Документировано в роутере.
- `storage_key` UNIQUE constraint добавлен в follow-up миграции `0030_storage_key_unique` (защита от UUID4-коллизии и manual DB pokes).
- In-category drag-and-drop reorder API -- не реализован (frontend-only в §6.2; PATCH `order` per-item достаточно для MVP).

### 3.1. Назначение

Произвольные бинарные файлы, прикреплённые к компании: бизнес-лицензии, сертификаты инкорпорации, лицензии на выпуск ценных бумаг, презентации, ванпейджеры, патенты, любые юридические/маркетинговые материалы. **Никаких** шаблонов, рендеринга, генерации -- просто файл + метаданные.

### 3.2. Модель `CompanyAttachment`

Поля:

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | -- |
| `company_id` | FK CompanyProfile RESTRICT | -- |
| `category` | String(200), index | path-tree (см. §3.2.1). Например: `legal/licenses/business`, `marketing/presentations`, `patents`. Regex `^[a-z0-9_-]+(/[a-z0-9_-]+){0,4}$` -- max 5 уровней, нижний регистр, без пробелов. |
| `language` | String(10), nullable | ISO 639-1 (`en/ru/de/ar`); NULL для language-agnostic (например, патент на английском по умолчанию). См. §3.6 |
| `title` | String(500) | отображаемое имя |
| `description` | String(5000), nullable | пояснение для инвестора |
| `storage_key` | String(1000) | ключ в MinIO (см. §2.2) |
| `original_filename` | String(500) | оригинальное имя файла (для скачивания "как есть") |
| `mime_type` | String(100) | application/pdf, image/png, ... |
| `file_size_bytes` | BigInteger | размер в байтах |
| `order` | Integer | для сортировки в UI |
| `is_published` | Boolean, default False | виден ли инвестору вообще |
| `is_public` | Boolean, default False | доступен ли без auth (см. §3.4) |
| `created_by` | FK users.id (staff) RESTRICT | -- |
| `created_at`, `updated_at` | стандартные timestamps | -- |
| `is_deleted` | Boolean, default False | soft-delete |

Индексы:
- `(company_id, category, is_published, is_deleted)` -- composite для основного запроса инвестора.
- `(company_id, order)` -- для сортировки.

Известные пути категорий фиксируются в `companies/constants.py` как **рекомендованный список**:
```python
KNOWN_ATTACHMENT_PATHS = {
    # Legal
    "legal/incorporation",
    "legal/licenses/business",
    "legal/licenses/stock",
    # Marketing
    "marketing/presentations",
    "marketing/onepagers",
    "marketing/press",
    # IP
    "patents",
    # Reports
    "reports/annual",
    "reports/audit",
    "reports/quarterly",
    # Generic
    "other",
}
```
UI Staff показывает chip с этими путями + возможность ввести custom (с regex-валидацией на фронте). Backend валидирует только regex -- список -- hint, не constraint.

#### 3.2.1. Path-tree логика

`category` хранится как plain string с разделителем `/`. Максимум 5 уровней (regex `{0,4}` -- нулевой уровень это сам сегмент). Слеши -- разделители логических уровней; в MinIO как ключ объекта они не участвуют (там UUID-based path, см. §2.2).

Фильтрация:
- `?category=legal/licenses/business` -- exact match.
- `?category_prefix=legal/` -- prefix-match (`category LIKE :prefix || '%'`). Полезно для UI-аккордеона "все юридические".

Frontend рендерит дерево клиентски: `path.split('/')` -> nested map по сегментам. Папка существует если в ней есть хотя бы один файл (нет "пустых папок"). По умолчанию L1 раскрыт, L2+ свёрнут.

Локализация имён сегментов -- через i18n: `i18n.t('inv.path.legal')` -> "Юридические". Если ключа нет -- fallback title-case (`legal -> Legal`).

### 3.3. Эндпоинты (auth flow)

Все под префиксом `/api/v1/companies/{company_id}/attachments` (читаемые) и `/api/v1/staff/companies/{company_id}/attachments` (управление).

Public read для investor (auth required, role investor/agent):
- `GET /api/v1/companies/{id}/attachments` -- список, фильтры `?category=X` (exact) или `?category_prefix=Y` (prefix-match), `?language=Z`, возвращает только `is_published=True AND is_deleted=False`. Поле `is_public` тоже возвращается (UI показывает индикатор "публичный документ").
- `GET /api/v1/companies/{id}/attachments/{att_id}/download` -- генерирует presigned URL (TTL `MINIO_PRESIGNED_TTL_AUTH` = 15 мин), отдаёт `302 Location` redirect на MinIO. Auth required.

Staff (управление):
- `GET /api/v1/staff/companies/{id}/attachments` -- список включая unpublished, deleted (с `?include_deleted=true`).
- `POST /api/v1/staff/companies/{id}/attachments` -- multipart upload (file + JSON metadata). Backend пишет в MinIO, создаёт запись.
- `PATCH /api/v1/staff/companies/{id}/attachments/{att_id}` -- метаданные (title, description, language, category, is_published, is_public, order).
- `PATCH /api/v1/staff/companies/{id}/attachments/{att_id}/replace` -- multipart, замена файла. Удаляет старый объект из MinIO, кладёт новый, обновляет storage_key/mime_type/file_size.
- `DELETE /api/v1/staff/companies/{id}/attachments/{att_id}` -- soft-delete. Объект в MinIO остаётся (для возможного восстановления).
- `DELETE /api/v1/staff/companies/{id}/attachments/{att_id}/hard` -- hard-delete: убирает из MinIO + DELETE row. Только admin (Q-ATT-1, см. §10).

### 3.4. Эндпоинты (public flow)

Без auth, для маркетинговых материалов с `is_public=True AND is_published=True`:

- `GET /api/v1/public/companies/{id}/attachments` -- список только public + published. Используется для "deep link"-показа презентаций без логина (например, Заказчик публикует ссылку в LinkedIn).
- `GET /api/v1/public/companies/{id}/attachments/{att_id}/download` -- presigned URL (TTL `MINIO_PRESIGNED_TTL_PUBLIC` = 24h), 302 redirect. Без auth. Если файл не `is_public` или не `is_published` -- 404 (не 403, чтобы не подтверждать существование).

Rate-limit на public-эндпоинты (Q-ATT-2, см. §10): `60 req/min/IP` для list, `300 req/min/IP` для download. Per-IP, отдельные Redis-ключи для list и download так чтобы перебор по download'у не мог исчерпать list quota и наоборот.

### 3.5. Permissions

| Операция | Permission |
|----------|-----------|
| Создать / редактировать / удалить attachment | `company_manage` |
| Просмотр Staff (включая unpublished) | любой staff (без специального гейта) |
| Hard-delete | admin (Q-ATT-1, см. §10) |

`content_manage` НЕ используется -- attachments относятся к конфигурации компании, не к контентной работе (новости/события).

### 3.6. Мультиязычность как pattern

Каждая языковая версия документа -- **отдельный `CompanyAttachment` row + отдельный объект в MinIO**. Поля `category` и `title` совпадают, отличается `language`.

Например, "Investor Deck Q2 2026" в трёх языках = три row:

| id | category | language | title |
|----|----------|----------|-------|
| uuid-1 | `marketing/presentations` | `de` | Investor Deck Q2 2026 |
| uuid-2 | `marketing/presentations` | `en` | Investor Deck Q2 2026 |
| uuid-3 | `marketing/presentations` | `ru` | Investor Deck Q2 2026 |

**Backend ничего не знает про "группу языковых версий"** -- никакого `language_group_id`, никаких связок. Бэк отдаёт плоский список.

**Группировка -- на фронте**, по `(category, title)`:
- При локали `de` инвестор видит карточку "Investor Deck Q2 2026" с language-бейджем `DE`.
- Внутри карточки (если у юзера переключатель "All languages" включён) -- табы `DE / EN / RU`, переключающие presigned URL для скачивания.
- Если у документа `language=null` -- он видим в любой локали без переключения языка.

**Когда `language=null`:**
- Patents -- обычно language-agnostic если на английском по дефолту.
- Финансовые отчёты -- зависит от компании.
- Сертификат инкорпорации -- обычно `language=de` для немецкой компании, не null. Если хочется english-перевод -- отдельный attachment с `language=en`.

Решение принимает Staff при загрузке (через `.cbsmeta.json`, см. §3.7).

**Filter API:** `?language=de` -- exact match. Если хочется "все варианты" -- параметр опускается. Без specific фронт-логики backend не делает -- в нашем случае фильтр выставляется фронтом.

### 3.7. Workflow Staff через MinIO Web UI (Inbox pattern + companion JSON)

В MVP UI приложения для загрузки attachments **отсутствует**. Staff работает с документами через **MinIO Web UI** (`https://storage-mc-admin.cbshome.org`, см. §1.4) по схеме **Inbox + reconcile**.

**MVP-flow:**

1. Staff заходит в Web UI, идёт в bucket `cbshome-attachments` -> `companies/{company_uuid}/inbox/`.
2. Загружает (drag-drop) **пары файлов**:
   - Сам документ: `<slug>.<ext>` (например, `investor-deck-q2-de.pdf`). Slug произвольный -- читабельный, без UUID, для удобства самого Staff'а.
   - Companion JSON: `<slug>.<ext>.cbsmeta.json` -- метаданные (см. формат ниже).
3. После загрузки Staff/админ запускает `cbshome storage reconcile <company_uuid>`.
4. Reconcile-скрипт:
   - Сканирует `companies/{company_uuid}/inbox/`.
   - Для каждого файла ищет companion `.cbsmeta.json` рядом.
   - **Если JSON отсутствует** -- skip + WARNING в лог: `WARN: orphan in inbox without metadata: <key>`. Файл остаётся в inbox.
   - **Если JSON есть** -- валидирует через Pydantic-схему `AttachmentInboxMetadata`. На ошибке валидации -- skip + ERROR в лог.
   - **Если валидация прошла** -- генерирует `attachment_id = uuid4()`, через storage layer (`upload_object` для нового объекта в `attachments/<attachment_id>/<slug>.<ext>` + `delete_object` для inbox-файла и его `.cbsmeta.json`), создаёт row в БД с полями из JSON + `storage_key`, `mime_type` (валидированный по extension через `validate_attachment_mime_by_filename`), `file_size_bytes`.
   - **Match check:** если в БД для этой компании уже есть row с теми же `(title, category, language)` -- это **replace existing**. Старый объект удаляется из MinIO, row обновляется (новый `storage_key`, `mime_type`, `file_size_bytes`, `updated_at`).
5. После reconcile папка `inbox/` пуста, всё в `attachments/<id>/`. Staff проверяет на стороне инвестора что документы видны.

**Формат `.cbsmeta.json`:**

```json
{
  "title": "Investor Deck Q2 2026",
  "description": "Q2 highlights, new projects pipeline",
  "category": "marketing/presentations",
  "language": "de",
  "order": 10,
  "is_published": true,
  "is_public": true
}
```

**Pydantic-схема `AttachmentInboxMetadata`** (та же, которую POST `/staff/attachments` будет принимать в post-MVP UI):

| Поле | Required | Default | Validation |
|------|----------|---------|------------|
| `title` | yes | -- | min_length=1, max_length=500 |
| `description` | no | null | max_length=5000 |
| `category` | no | `"unsorted"` | regex как у модели (см. §3.2) |
| `language` | no | null | ISO 639-1 (en/ru/de/ar) или null |
| `order` | no | 0 | int >= 0 |
| `is_published` | no | false | bool |
| `is_public` | no | false | bool |

Default'ы по умолчанию **safety-first**: `is_published=false`, `is_public=false`. Документ не светится инвестору пока Staff явно не выставит `is_published=true` в JSON.

**Bulk-загрузка нескольких документов:**

Локально в файловой системе Staff готовит папку:
```
upload-batch/
├── deck-de.pdf
├── deck-de.pdf.cbsmeta.json
├── deck-en.pdf
├── deck-en.pdf.cbsmeta.json
├── incorporation-cert.pdf
└── incorporation-cert.pdf.cbsmeta.json
```

Drag-drop всю папку в Web UI в `inbox/`, потом один `cbshome storage reconcile <uuid>` -- всё попадает в БД.

**Post-MVP UI** будет загружать через `POST /api/v1/staff/companies/{id}/attachments` (multipart, см. §3.3) с body, идентичным `AttachmentInboxMetadata`. Никаких разных форматов в двух местах -- inbox + companion JSON и production POST принимают одну и ту же Pydantic-схему.

**Reconcile -- двунаправленный:**

- Direction `inbox -> DB` (orphans): описано выше.
- Direction `DB -> MinIO` (broken): для каждой row в `company_attachments` проверяется наличие объекта по `storage_key`. Если объекта нет -- row помечается `is_deleted=true` (не удаляется hard, чтобы Staff мог разобраться). В лог: `WARN: broken record, marked as deleted: id=...`.

Опции `--orphans-only` и `--broken-only` запускают только одно из направлений.

---

## 4. Backend: модуль `company_doc_templates`

**В работе (iter 2.3).** Templates backend + platform default seed реализуются одной итерацией -- без platform default rows fallback в §4.7 не покрывает свежесозданную компанию, и реалистичные тесты не пишутся.

### 4.1. Назначение

Шаблоны для **генерируемых** юридических документов компании. Каждый template -- это **набор файлов в MinIO** (HTML + бинарные ассеты), а не TEXT в БД. БД хранит только метаданные и pointer на storage prefix.

В отличие от compliance-документов (модуль `documents`, body в frontend assets, hash-versioning через seed), у каждой компании свои шаблоны, потому что:
- Каждая компания юридически разная -- свой подписант, печать, логотип.
- Шаблон должен включать бинарные ассеты (logo.png, signature.png, stamp.png), которые нативно живут в файловой системе, а не в HTML.
- Загрузка идёт через MinIO Web UI (см. §4.8), как и attachments.

**Platform default fallback.** Помимо per-company template'ов, существуют **platform default templates** -- общие для всех компаний, лежат в MinIO под префиксом `_platform/templates/`. Если у компании нет своего active template для нужной пары `(kind, language)` -- используется platform default. Это гарантирует что свежесозданная компания может генерировать договоры сразу, без ручных действий со стороны Staff'а. См. §4.7 (fallback) и §4.9 (platform default flow).

Платформа default'ы устанавливаются скриптом `install_cbshome.sh` при первой установке (см. §1.4) -- HTML + placeholder-ассеты копируются из репо в MinIO, в БД создаются rows с `company_id=NULL`.

### 4.2. Модель `CompanyDocumentTemplate`

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | -- |
| `company_id` | FK CompanyProfile RESTRICT, **nullable** | NULL = platform default (общий fallback для всех компаний). NOT NULL = per-company override. |
| `kind` | String(50) | enum: см. §4.3 |
| `language` | String(10) | ISO 639-1 |
| `version` | Integer | инкремент при обновлении |
| `title` | String(500) | для UI Staff (read-only inspection) |
| `storage_prefix` | String(500) | путь к "папке" template'а в MinIO. Для per-company: `companies/<id>/templates/<kind>/<lang>/`. Для platform default: `_platform/templates/<kind>/<lang>/`. |
| `asset_files` | JSONB list | список имён ассетов в storage_prefix, например `["logo.png", "signature.png", "stamp.png"]`. Заполняется reconcile-скриптом при загрузке. Используется для валидации (template.html не должен ссылаться на отсутствующий ассет). |
| `status` | String(20) | `draft / active / archived` |
| `created_by` | FK users.id (staff), nullable | NULL для platform default (создан seed-скриптом, не Staff'ом) |
| `created_at`, `updated_at` | timestamps | -- |
| UNIQUE | `(company_id, kind, language, version)` | NULL company_id -- одна уникальная серия для platform default |
| Index | `(company_id, kind, language, status)` | для lookup'а active при создании Purchase |

State machine: `draft <-> active`, `draft/active -> archived`. При появлении нового active для пары `(company_id, kind, language)` -- старый active автоматически становится archived (в service layer, при reconcile).

**`body` поле УДАЛЕНО.** HTML лежит в MinIO как файл `<storage_prefix>/template.html`. Backend читает его при каждом рендере (с кэшем в Redis, TTL 5 мин -- см. §4.10).

**Поиск template'а** -- 4-ступенчатый fallback с учётом `company_id IS NULL` для platform default. См. §4.7.

### 4.3. Допустимые `kind`

Фиксированный enum в `companies/constants.py` (в отличие от `category` у attachments -- здесь жёсткий список, потому что от kind зависит логика рендеринга и набор плейсхолдеров):

```python
class DocumentTemplateKind(StrEnum):
    PURCHASE_AGREEMENT = "purchase_agreement"
    GIFT_CERTIFICATE = "gift_certificate"
    INSTALLMENT_SUBCONTRACT = "installment_subcontract"
    OWNERSHIP_CERTIFICATE = "ownership_certificate"
```

Соответствие:
- `purchase_agreement` -- для `Purchase.legal_basis = sale`.
- `gift_certificate` -- для `Purchase.legal_basis = gift`.
- `installment_subcontract` -- для `Purchase.legal_basis = installment_tranche`.
- `ownership_certificate` -- агрегат всех Purchase юзера по компании.

### 4.4. Placeholders и Jinja-функции

Для каждого `kind` определён набор переменных Jinja2-контекста. Зафиксирован в `companies/constants.py` как `TEMPLATE_PLACEHOLDERS: dict[DocumentTemplateKind, set[str]]`.

Примерный набор (TBD в детализации):
- `purchase_agreement` -- `investor_name`, `investor_email`, `company_name`, `company_legal_name`, `product_name`, `units`, `paid_cents`, `price_per_unit_cents`, `purchase_date`, `certificate_number`, `legal_basis`.
- `ownership_certificate` -- `investor_name`, `company_name`, `total_units`, `sale_units`, `gift_units`, `total_paid_cents`, `current_value_cents`, `as_of_date`, `purchases[]` (массив).

**Jinja-функция `asset_data_uri(filename)`** -- кастомная функция, регистрируется в Jinja2 Environment для каждого рендера. Принимает имя файла из `asset_files` template'а, возвращает `data:image/png;base64,<...>` URI с inline-bytes ассета. Используется в HTML вот так:

```html
<div class="header">
  <img src="{{ asset_data_uri('logo.png') }}" alt="logo">
</div>
...
<div class="footer">
  <img src="{{ asset_data_uri('stamp.png') }}" alt="stamp">
  <img src="{{ asset_data_uri('signature.png') }}" alt="signature">
</div>
```

**Никаких external URLs.** Все ассеты embed'аются inline в base64 -- это нужно для:
- PDF-рендера через xhtml2pdf, который не всегда работает с external HTTP-ресурсами.
- Email-рассылки (PDF as attachment) -- ассеты не теряются если получатель открыл письмо в offline-режиме.
- Self-contained HTML output -- юрист может сохранить договор как один файл без зависимости от cbshome.org.

Implementation: в `app/modules/purchases/certificate_service.py` (после рефакторинга в §5.4) -- helper `make_asset_data_uri_func(storage_prefix, asset_files)` создаёт замыкание, которое для каждого вызова `asset_data_uri('logo.png')` делает `storage.get_object_bytes(storage_prefix + 'logo.png')`, кодирует в base64, оборачивает в `data:<mime>;base64,...`. Функция регистрируется в Jinja2 Environment перед рендером.

Validation шаблона при reconcile (см. §4.8): парсинг через Jinja2 (`Environment.parse`), отлов синтаксических ошибок (`TemplateSyntaxError`). Ссылки на ассеты, отсутствующие в `asset_files` -- ERROR в логе reconcile, template не активируется.

### 4.5. Эндпоинты (MVP scope)

В MVP UI приложения для редактирования template'ов **отсутствует** -- управление через MinIO Web UI (см. §4.8). Backend в MVP экспонирует только read-only inspection эндпоинты для Staff:

- `GET /api/v1/staff/companies/{id}/templates` -- список template'ов компании (фильтр `?kind=&language=&status=`). Включая platform default (если у компании нет своего active для пары -- в ответе указывается `is_platform_default: true` и read-only inspection идёт через storage_prefix `_platform/...`).
- `GET /api/v1/staff/companies/{id}/templates/{tpl_id}` -- один (с inline content HTML и list of asset_files для inspection).

**Post-MVP** (вне scope этого refactor'а): полный CRUD через UI, preview-эндпоинт, эндпоинт upload через multipart. Все эти эндпоинты будут принимать ту же Pydantic-схему, что reconcile-script использует для `_meta.cbsmeta.json` (см. §4.8) -- единый формат в двух местах.

### 4.6. Permissions

`company_manage` для всех CRUD-операций. Никакой `financial_operations` не нужен -- редактирование шаблона не финансовая операция (финансовая -- момент покупки, а там проверяется `financial_operations` отдельно).

### 4.7. Fallback логика (4 ступени с platform default)

При создании Purchase или ownership_certificate render, helper `find_active_template(company_id, kind, language)` ищет template в следующем порядке:

1. **Per-company, локаль юзера:** `WHERE company_id=X AND kind AND language=user_lang AND status=active`. Нашёл? Используй.
2. **Per-company, English fallback:** `WHERE company_id=X AND kind AND language='en' AND status=active`. Нашёл? Используй.
3. **Platform default, локаль юзера:** `WHERE company_id IS NULL AND kind AND language=user_lang AND status=active`. Нашёл? Используй.
4. **Platform default, English fallback:** `WHERE company_id IS NULL AND kind AND language='en' AND status=active`.

**Если ничего не нашлось -- 500 (system error).** В production такого быть не должно, потому что platform default гарантированно есть после `install_cbshome.sh` (см. §1.4 + §4.9). 500 в этом случае означает что что-то сломалось в seed'е или MinIO -- сигнал на починку, не штатное поведение.

В тестах эта 4-ступенчатая логика обеспечивает работу свежесозданных компаний "из коробки": тест создаёт компанию через `POST /staff/companies`, не загружает свои template'ы, и сразу может дёргать `GET /purchases/{id}/agreement` -- рендер идёт через platform default (ступень 3 или 4).

### 4.8. Workflow Staff через MinIO Web UI (per-company templates)

Загрузка/обновление template'ов для конкретной компании -- тот же inbox-pattern, что для attachments (§3.7), только в отдельном prefix'е и со своим reconcile-скриптом.

**MVP-flow:**

1. Staff локально готовит "папку шаблона":
   ```
   purchase-agreement-de/
   ├── template.html        # HTML с Jinja2-плейсхолдерами + asset_data_uri('logo.png') и т.д.
   ├── logo.png             # фактический логотип компании
   ├── signature.png        # подпись подписанта
   ├── stamp.png            # печать
   └── _meta.cbsmeta.json   # метаданные template'а
   ```

2. Заходит в MinIO Web UI -> bucket `cbshome-attachments` -> `companies/{company_uuid}/templates-inbox/`.

3. Создаёт подпапку `<kind>__<lang>/` (например `purchase_agreement__de/`) и drag-drop'ает все файлы template'а внутрь.

4. Запускает `cbshome storage reconcile-templates <company_uuid>`.

5. Reconcile-скрипт:
   - Сканирует `companies/{uuid}/templates-inbox/<kind>__<lang>/`.
   - Читает `_meta.cbsmeta.json`. Валидирует через Pydantic-схему `TemplateInboxMetadata`. На ошибке -- skip + ERROR в лог.
   - Валидирует `template.html` через Jinja2 `Environment.parse`. На ошибке -- skip + ERROR.
   - Проверяет что все `asset_data_uri('<filename>')` в HTML ссылаются на файлы, которые присутствуют рядом. На несовпадении -- skip + ERROR.
   - Через storage layer (`upload_object` для нового места + `delete_object` для inbox-источников и `_meta.cbsmeta.json`) переносит файлы из `templates-inbox/<kind>__<lang>/` в canonical path `templates/<kind>/<lang>/`.
   - Если для пары `(company_id, kind, language)` уже есть active row -- старый row становится `archived`, новый становится `active` с `version + 1`.
   - Создаёт row в `company_document_templates` со списком `asset_files` (имена .png/.jpg, найденные в папке).

**Формат `_meta.cbsmeta.json`:**

```json
{
  "kind": "purchase_agreement",
  "language": "de",
  "title": "Договор покупки опционов IPI AG",
  "status": "active"
}
```

**Pydantic-схема `TemplateInboxMetadata`:**

| Поле | Required | Validation |
|------|----------|------------|
| `kind` | yes | enum `DocumentTemplateKind` |
| `language` | yes | ISO 639-1 (`en/ru/de/ar`) |
| `title` | yes | min_length=1, max_length=500 |
| `status` | yes | `draft` / `active` (archived в JSON не указывается -- архивирование автоматическое при появлении нового active) |

Все поля required. У template'ов нет safety-defaults как у attachments -- ошибки в template = ошибки рендера договоров = юридические проблемы, поэтому жёсткие требования.

**Post-MVP** -- полный UI editor (`TemplatesEditor.vue`, см. §6.3) с textarea + live preview, та же Pydantic-схема `TemplateInboxMetadata` принимается через POST endpoint.

### 4.9. Platform default templates

Platform default templates -- общие fallback-шаблоны для всех компаний. Лежат в MinIO под префиксом `_platform/templates/`, в БД представлены rows с `company_id=NULL`.

**Структура в репо** (источник truth для install-скрипта):

```
backend/scripts/seed_data/templates/_default/
├── purchase_agreement/
│   ├── en/
│   │   ├── template.html
│   │   ├── logo.png       # placeholder (1x1 transparent или generic logo)
│   │   ├── signature.png  # placeholder
│   │   └── stamp.png      # placeholder
│   ├── de/...
│   ├── ru/...
│   └── ar/...
├── gift_certificate/
│   └── ...
├── installment_subcontract/
│   └── ...
└── ownership_certificate/
    └── ...
```

Bootstrap-данные лежат под `backend/scripts/seed_data/`, рядом со seed-скриптами в `backend/scripts/`. В корне `backend/` отдельной папки `seed/` нет -- структура backend держится на двух top-level директориях `app/` (runtime) и `scripts/` (seed/management/dev tools).

**Установка (часть install_cbshome.sh, см. §1.4):**

1. `mc cp -r backend/scripts/seed_data/templates/_default/ local/cbshome-attachments/_platform/templates/` -- заливает все файлы.
2. `python backend/scripts/seed_platform_templates.py` -- создаёт rows для каждой пары `(kind, language)` с `company_id=NULL`, `storage_prefix='_platform/templates/<kind>/<lang>/'`, `status=active`. Идемпотентен.

**Обновление platform default'ов (если юристы платформы захотят поправить общий шаблон):**

Те же inbox + reconcile, но на платформенном уровне:

1. Staff/админ платформы заходит в MinIO Web UI -> `_platform/templates-inbox/<kind>__<lang>/`.
2. Заливает `template.html + ассеты + _meta.cbsmeta.json`.
3. Запускает `cbshome storage reconcile-platform-templates`.
4. Скрипт перемещает файлы в `_platform/templates/<kind>/<lang>/`, обновляет row с `company_id=NULL` (старый -> archived, новый -> active с version+1).

**Что в placeholder-ассетах при первой установке:** в репо лежат честные dummy-картинки (1x1 transparent PNG для logo/signature/stamp). При первом запуске тестовая компания получает рендер с прозрачными местами на месте печати/подписи -- юридически невалидно, но рендер не падает. В production юристы платформы заменят placeholder'ы на реальные generic-ассеты через reconcile-platform-templates до старта продаж.

**Per-company override.** Когда у компании появляются свои подписант/печать -- через MinIO Web UI заливает в `companies/<id>/templates-inbox/`, после reconcile появляется row с `company_id=<id>`. С этого момента fallback ступень 1 (per-company, локаль юзера) находит свой шаблон, platform default используется только если language юзера не покрыт per-company версиями.

### 4.10. Кэширование

Чтение `template.html` из MinIO при каждом рендере -- не оптимально (плата ~50-100ms latency). Делаем простой кэш:

- В Redis: ключ `template_html:<storage_prefix>` с TTL 5 минут (константа `TEMPLATE_HTML_CACHE_TTL_SECONDS = 300` в `companies/constants.py`). Redis-клиент проекта инициализируется с `decode_responses=True`, поэтому значение хранится как **base64-encoded string** (на запись `b64encode(html_bytes).decode("ascii")`, на чтение `b64decode(cached_str)` -> bytes).
- При reconcile (любого типа: per-company или platform) -- скрипт инвалидирует кэш для затронутых prefix'ов через `redis.delete(key)` (helper `invalidate_template_html_cache(storage_prefix)` в `companies/service.py`).
- В тестах кэш контролируется через `monkeypatch` константы `TEMPLATE_HTML_CACHE_TTL_SECONDS` (на 0 для отключения) либо очищается autouse-фикстурой по ключу.

Ассеты не кэшируем в Redis -- они большие (могут быть до 500KB-1MB на ассет), пуляем через `storage.get_object_bytes()` каждый раз. Если потребуется оптимизация -- кэшируем в process-memory с LRU, но это post-MVP.

---

## 5. Backend: Purchase docs fix

**Впереди (iter 2.4).** Зависит от §4 (templates module).

### 5.1. Изменения в модели `Purchase`

Добавляется поле:

| Поле | Тип | Назначение |
|------|-----|------------|
| `purchase_agreement_template_id` | FK CompanyDocumentTemplate, **nullable**, ondelete=SET NULL | snapshot id шаблона (per-company или platform default), использованного на момент создания Purchase |

Поле **NULLABLE** по техническим причинам -- ondelete=SET NULL для устойчивости к удалению старых archived rows. Но в **штатной production-логике** значение всегда non-NULL:

- При создании Purchase -- `find_active_template()` (4-ступенчатый fallback, см. §4.7) гарантированно находит template, потому что platform default есть для всех `(kind, language)` пар, заданных в `install_cbshome.sh`.
- Если `find_active_template()` возвращает None -- это **ошибка инфраструктуры** (что-то сломалось в seed'е или MinIO). Логика создания Purchase в этом случае:
  - Пишет structured лог через `structlog`: `logger.error("template_missing", company_id=X, kind=Y, language=Z)`.
  - Пишет audit event `purchase.template_missing` (через `record_audit`) с теми же полями + `purchase_id` -- так Staff видит broken Purchase в audit dashboard.
  - Создаёт Purchase с `purchase_agreement_template_id=NULL`. Продажа всё равно проходит -- финансовая транзакция важнее, чем рендер документа.
  - При попытке сделать `GET /purchases/{id}/agreement` -- 500 (system error, см. §5.3).

Mapping `Purchase.legal_basis -> DocumentTemplateKind`:
- `sale` -> `purchase_agreement`
- `gift` -> `gift_certificate`
- `installment_tranche` -> `installment_subcontract`

`ondelete=SET NULL` потому что Staff/seed может удалить старую `archived` запись template'а -- история Purchase важнее, чем история template.

### 5.2. Логика в `purchase_processor` (Sprint 6.1)

В `app/modules/purchases/service.py`, в момент создания Purchase row:

```
# Pseudocode: not actual code
template = await find_active_template(
    company_id=purchase.company_id,
    kind=BASIS_TO_KIND[purchase.legal_basis],
    language=investor.profile.language or "en",
    session=session,
)
purchase.purchase_agreement_template_id = template.id if template else None
```

`find_active_template()` -- helper в `companies/service.py`, реализует 4-ступенчатый fallback (см. §4.7): per-company-locale, per-company-en, platform-default-locale, platform-default-en. Если ничего не нашёл -- возвращает None. **Не raise.**

### 5.3. Эндпоинты вместо `GET /purchases/{id}/certificate`

Старый эндпоинт `GET /api/v1/purchases/{id}/certificate` **переименовывается** в `GET /api/v1/purchases/{id}/agreement`. То же с `/email`. Никаких redirect'ов из старого URL -- breaking change, фронт правится синхронно.

Новые эндпоинты:

**Per-Purchase agreement (snapshot):**
- `GET /api/v1/purchases/{id}/agreement` -- HTML рендер. Использует `purchase.purchase_agreement_template_id`. Если NULL -- **500** с сообщением "Договор для этой покупки не сконфигурирован (system error)". Это не штатный 404, потому что в production NULL не должен встречаться (см. §5.1 -- platform default гарантирует non-NULL). Staff видит broken Purchase в audit/dashboard, починяется через `cbshome storage reconcile-platform-templates` или загрузкой шаблона + ручным backfill `purchase.purchase_agreement_template_id` через service-script.
- `POST /api/v1/purchases/{id}/agreement/email` -- PDF на email. Если template_id NULL -- 500 (та же логика).

**Per investor-company ownership certificate (live aggregate):**
- `GET /api/v1/companies/{id}/ownership-certificate` -- HTML рендер. Live-агрегат всех `Purchase WHERE investor_id=current_user AND company_id={id} AND status != reversed`. Шаблон ищется на лету через `find_active_template(company_id, kind=ownership_certificate, language=user_language)` (4-ступенчатый fallback). Если ничего не нашлось -- **500** (то же значение -- platform default должен быть).
- `POST /api/v1/companies/{id}/ownership-certificate/email` -- PDF на email.

Для `ownership_certificate` НЕТ snapshot'а -- сертификат отражает текущее состояние портфеля, не момент в прошлом. Каждый запрос ищет шаблон заново (с кэшем HTML, см. §4.10).

### 5.4. Удаление старого

- `backend/app/modules/purchases/templates/certificate.html` -- удаляется (перестаёт использоваться, на смену приходит per-company / platform default template из MinIO).
- `backend/app/modules/purchases/certificate_router.py` -- переименовывается, эндпоинты перепиливаются.
- `backend/app/modules/purchases/certificate_service.py` -- основная логика остаётся (Jinja2 рендер, xhtml2pdf, send_email), но:
  - `_LEGAL_BASIS_DISPLAY` уходит (заголовок теперь часть template'а).
  - Шаблон ищется через `find_active_template()` в БД (4-ступенчатый fallback, см. §4.7), HTML body читается из MinIO по `<storage_prefix>/template.html` (с Redis-кэшем, см. §4.10).
  - Регистрируется Jinja-функция `asset_data_uri(filename)` через `make_asset_data_uri_func(storage_prefix, asset_files)` (см. §4.4).
  - Ассеты embed'аются inline base64 в HTML/PDF.

### 5.5. Frontend контракт

`frontend/src/api/certificates.ts` переписывается:
- `fetchAgreementBlob(purchaseId)` вместо `fetchCertificateBlob`.
- `emailAgreement(purchaseId)` вместо `emailCertificate`.
- Новые: `fetchOwnershipCertificateBlob(companyId)`, `emailOwnershipCertificate(companyId)`.

`CompanyPositionView` сейчас отображает один "сертификат" на весь экран позиции. После рефакторинга:
- Шапка экрана -- кнопка "Сертификат владения" (ownership_certificate).
- В списке Purchase -- на каждой строке кнопка "Договор" (per-purchase agreement).

## 6. Frontend: Staff UI

### 6.1. Контекст

Часть `StaffCompanyDetailView` (определена в родительском refactor-документе, §4.6). Здесь добавляются ДВЕ новые секции к тем, что уже описаны в родителе:

- **Documents** -- управление `company_attachments`.
- **Templates** -- управление `company_doc_templates`.

В родительском документе (v0.2, §4.2) эти секции лежат в "вне MVP". Текущим refactor-ом они переезжают в MVP. **Соответствующая правка родительского документа -- отдельной задачей, после фиксации этого draft'а.**

### 6.2. Секция Documents (`AttachmentsEditor.vue`)

**MVP scope:**

В MVP полноценный загрузчик файлов через UI приложения **не делается** -- Staff загружает через MinIO Web UI + companion JSON + `cbshome storage reconcile` (см. §3.7). Эта секция в Staff UI в MVP служит для:

- Просмотра существующих attachment'ов компании (включая unpublished и deleted).
- Редактирования метаданных уже созданных rows: `title`, `description`, `category` (с path-tree autocomplete), `language`, `is_published`, `is_public`, `order`. Через `PATCH /staff/companies/{id}/attachments/{att_id}`.
- Soft-delete через `DELETE`.
- Drag-and-drop reorder внутри одной category.

**Post-MVP** добавляется полная форма загрузки (multipart `POST /staff/companies/{id}/attachments` с file + metadata) -- та же Pydantic-схема, что у `.cbsmeta.json` в §3.7. После этого Staff может выбирать любой из путей: Web UI + reconcile (для bulk) или UI приложения (для одиночных).

**Структура (MVP):**

- Header: фильтр по category (chip-row с известными paths из `KNOWN_ATTACHMENT_PATHS`), фильтр по language, индикатор "Документы загружаются через MinIO Web UI -- см. инструкции".
- Список карточек attachment'ов: иконка mime-type, title, language-бейдж, category-path (как breadcrumb `legal > licenses > business`), размер, индикатор "Public" (если is_public), индикатор "Draft" (если !is_published), кнопки `Edit / Delete`.
- Drag-and-drop для reorder внутри одной category.

**Модалка редактирования метаданных:**

- Поля: title, description, category (autocomplete из `KNOWN_ATTACHMENT_PATHS` + custom с regex-валидацией), language (en/ru/de/ar/null), is_published, is_public.
- Никакого file input -- замена файла идёт через Web UI (загрузить новый файл с тем же `(title, category, language)` -> reconcile сделает replace, см. §3.7).

Permissions: гейт по `company_manage`.

### 6.3. Секция Templates (`TemplatesEditor.vue`)

**MVP scope:** только read-only inspection. Полноценный editor -- post-MVP.

**MVP-структура:**
- Tab-bar по `kind` (4 таба).
- Внутри таба -- список row'ов из `GET /staff/companies/{id}/templates` (см. §4.5):
  - Per-company active template'ы (`is_platform_default=false`) -- title, version, language, статус.
  - Если по какому-то `(kind, language)` нет per-company active -- показывается "Используется platform default" (read-only inspection через storage_prefix `_platform/...`).
- Кнопка "Открыть в MinIO Web UI" -- ведёт на `https://storage-mc-admin.cbshome.org/browser/cbshome-attachments/companies/<id>/templates-inbox/<kind>__<lang>/`. Staff там готовит новую версию шаблона + загружает.
- Подпись "После загрузки запустите `cbshome storage reconcile-templates <company_id>`".

Никакого textarea / preview / save buttons в MVP -- всё через MinIO Web UI + reconcile-script.

**Post-MVP** -- полный editor с textarea, live preview через POST endpoint, version history. Pydantic-схема та же, что в `_meta.cbsmeta.json` (см. §4.8) -- единый формат.

Permissions: `company_manage` (read-only listing). Post-MVP edit -- `company_manage`.

### 6.4. Layout секций в StaffCompanyDetailView

Это связано с Q4 родительского документа (sub-tabs / accordion / nested routes). Решение там определит компоновку и здесь -- никакого отдельного решения для Documents/Templates не требуется.

---

## 7. Frontend: Investor UI

### 7.1. Секция "Документы" на CompanyOverviewView

Источник данных: `GET /api/v1/companies/{id}/attachments` (auth) -- возвращает только published, любой `is_public`, отсортированный по `(category, order)`.

**Структура секции:**

- **L1-группировка** по верхнему сегменту path-tree (`legal`, `marketing`, `patents`, `reports`, ...). Внутри группы -- плоский список карточек.
- Заголовок группы -- локализованный через i18n: `inv.path.legal -> "Юридические"`, `inv.path.marketing -> "Маркетинг"` и т.д. Custom-paths без i18n-ключа -- title-case fallback (`custom_xyz -> Custom Xyz`).
- Карточка attachment'а:
  - Mime-based иконка по типу файла: PDF -> `file-text`, PNG/JPG/WEBP -> `image`, PPTX -> `presentation`, DOCX -> `file-text`, XLSX -> `sheet`, MP4/WEBM -> `video`, прочее -> `file`.
  - Title.
  - Subcategory как breadcrumb под title (например, `marketing / presentations`) -- маленький серый текст.
  - Размер файла, mime-тип.
  - Description (если есть, в expanded состоянии).
- Клик по карточке -- `GET /api/v1/companies/{id}/attachments/{att_id}/download` -> 302 на presigned URL -> браузер открывает / скачивает.

**Фильтрация по языку:** клиентский фильтр `language === userLocale || language === null`. Юзер видит документы на своей локали + language-agnostic. Никаких UI-табов / переключателей языка -- язык юзера прибит к юзеру.

Если у документа есть только `language=de`, а юзер на `ru` -- этого документа в его представлении нет. Это контентная задача Staff'а: либо обеспечивает переводы, либо помечает `language=null`.

**Empty state:** если у компании 0 published attachments (после language-фильтра) -- секция "Документы компании" **скрывается целиком**. Никакого empty placeholder'а. Контентом управляет Staff.

### 7.2. Public deep-link

URL вида `https://cbshome.org/public/companies/{id}/attachments/{att_id}` -- статический landing-page (Vue route `/public/companies/:id/attachments/:attId`), без auth-guard. Делает `GET /api/v1/public/companies/{id}/attachments/{att_id}/download`. Если 404 (не public или не published) -- показывает "Документ недоступен или удалён".

Используется в маркетинге: Заказчик публикует ссылку на презентацию в LinkedIn -- кто угодно открывает, видит документ, без регистрации.

## 8. Backend changes: сводка

| Задача | Источник |
|--------|----------|
| Storage abstraction `app/core/storage.py` | §2 |
| Зависимость `aiobotocore` в pyproject.toml | §2.3 |
| Модель `CompanyAttachment` + миграция | §3.2 |
| Эндпоинты company_attachments (auth) | §3.3 |
| Эндпоинты company_attachments (public) | §3.4 |
| Mime-types whitelist для upload | §10 Closed |
| Reconcile-script `backend/scripts/reconcile_attachments.py` | §3.7 |
| Pydantic-схема `AttachmentInboxMetadata` | §3.7 |
| Модель `CompanyDocumentTemplate` (`company_id` nullable, `storage_prefix`, `asset_files`, без `body`) + миграция | §4.2 |
| MVP read-only эндпоинты `GET /staff/companies/{id}/templates` | §4.5 |
| Pydantic-схема `TemplateInboxMetadata` | §4.8 |
| Reconcile-script `backend/scripts/reconcile_templates.py` (per-company) | §4.8 |
| Reconcile-script `backend/scripts/reconcile_platform_templates.py` | §4.9 |
| Seed-script `backend/scripts/seed_platform_templates.py` (idempotent) | §4.9 |
| Bootstrap файлы в `backend/scripts/seed_data/templates/_default/<kind>/<lang>/` (HTML + 3 placeholder PNG для всех 4 kinds × 4 lang) | §4.9 |
| Jinja-функция `asset_data_uri(filename)` + helper `make_asset_data_uri_func()` | §4.4 |
| Redis-кэш `template_html:<storage_prefix>` (TTL 5 мин), invalidation в reconcile-скриптах | §4.10 |
| `find_active_template()` 4-stage fallback с `company_id IS NULL` | §4.7 |
| Поле `Purchase.purchase_agreement_template_id` (nullable, ondelete=SET NULL) + миграция | §5.1 |
| Логика snapshot template_id в `purchase_processor` (с structlog + audit event на NULL fallthrough) | §5.1 |
| Переименование эндпоинтов purchase certificate -> agreement (breaking change) | §5.3 |
| Новые эндпоинты ownership_certificate | §5.3 |
| 500 (а не 404) при `purchase.template_id IS NULL` -- сигнал поломки инфраструктуры | §5.3 |
| Удаление `purchases/templates/certificate.html` | §5.4 |
| Перезапись `certificate_service.py`: чтение HTML из MinIO + Jinja-функция `asset_data_uri` | §5.4 |

Миграции:
1. Добавление `purchase_agreement_template_id` в `purchases` (nullable, FK с ondelete=SET NULL).
2. Создание таблицы `company_attachments`.
3. Создание таблицы `company_document_templates` (с `company_id NULL`, без `body`, с `storage_prefix` + `asset_files`).

---

## 9. Frontend changes: сводка

| Задача | Источник |
|--------|----------|
| `AttachmentsEditor.vue` (Staff, MVP -- метаданные + reorder, без upload) | §6.2 |
| `TemplatesEditor.vue` (Staff, MVP -- read-only listing с ссылкой на MinIO Web UI) | §6.3 |
| Секция "Документы" в `CompanyOverviewView` (Investor) -- L1-группировка с локализацией, mime-иконки, скрытие при empty | §7.1 |
| Public landing-page `/public/companies/:id/attachments/:attId` | §7.2 |
| Переписать `frontend/src/api/certificates.ts` (rename to `agreements.ts`) | §5.5 |
| Изменить `CompanyPositionView` (отдельные кнопки Договор / Сертификат владения) | §5.5 |
| API клиент `frontend/src/api/attachments.ts` (новый) | §3 |
| API клиент `frontend/src/api/templates.ts` (новый, read-only списки) | §4.5 |
| Store `frontend/src/stores/attachments.ts` (новый) | §3 |
| Store `frontend/src/stores/templates.ts` (новый, read-only) | §4.5 |
| i18n-ключи `inv.path.<segment>` для известных path-сегментов (legal/marketing/patents/...) + title-case fallback в коде | §7.1 |

Post-MVP (вне scope refactor'а):
- Полноценный editor шаблонов с textarea + live preview.
- Полноценный uploader attachments (multipart форма) в UI вместо MinIO Web UI.

---

## 10. Открытые вопросы / отложенные решения

**Все вопросы закрыты.** Документ decision-locked.

**Closed (решения зафиксированы):**

### v0.4 -- templates в MinIO с ассетами и platform default

- **Templates лежат в MinIO как файлы (HTML + бинарные ассеты), не в БД как TEXT** (§4.1, §4.2). Поле `body: Text` в `CompanyDocumentTemplate` удалено, добавлены `storage_prefix: String(500)` и `asset_files: JSONB list`.
- **Platform default templates существуют как fallback** (§4.7, §4.9). Переворачивает решение из v0.2/v0.3 ("Platform default -- НЕТ"). Обоснование: тесты создают компании на лету, без platform default рендер договоров ломается на свежесозданной компании. См. `backend/tests/test_dashboard.py::test_certificate_html`.
- **`company_id` nullable в `CompanyDocumentTemplate`** (§4.2): NULL = platform default, NOT NULL = per-company override.
- **4-ступенчатая fallback логика поиска template'а** (§4.7): per-company-locale -> per-company-en -> platform-locale -> platform-en. Не нашёл -> 500 (system error, в production не должно случаться).
- **Inline base64 ассеты через Jinja-функцию `asset_data_uri(filename)`** (§4.4). Никаких external URLs в HTML/PDF -- self-contained output.
- **Canonical path для template'ов в MinIO** (§2.2): `companies/<id>/templates/<kind>/<lang>/template.html`, `_platform/templates/<kind>/<lang>/template.html`. Один active per `(kind, language)`, версионирование делает БД, MinIO перезаписывает.
- **Workflow Staff per-company templates -- через MinIO Web UI + `cbshome storage reconcile-templates`** (§4.8). Inbox pattern в `companies/<id>/templates-inbox/<kind>__<lang>/`, companion `_meta.cbsmeta.json`. UI editor templates -- post-MVP.
- **Workflow Platform default updates -- через MinIO Web UI + `cbshome storage reconcile-platform-templates`** (§4.9). Inbox pattern в `_platform/templates-inbox/`. Обновляются юристами платформы.
- **Bootstrap defaults в репозитории**: `backend/scripts/seed_data/templates/_default/<kind>/<lang>/{template.html, logo.png, signature.png, stamp.png}` для всех 4 kind × 4 lang. Заливаются в MinIO при `install_cbshome.sh` (§1.4) + `seed_platform_templates.py` создаёт rows с `company_id=NULL`.
- **Redis-кэш HTML template'ов** (§4.10), TTL 5 мин, key `template_html:<storage_prefix>`, инвалидация в reconcile-скриптах. Значение -- base64-encoded строка (Redis-клиент проекта инициализируется с `decode_responses=True`). Ассеты не кэшируем.
- **`Purchase.purchase_agreement_template_id` остаётся nullable** (§5.1) для устойчивости к удалению, но в production гарантированно non-NULL благодаря platform default fallback. NULL = ошибка инфраструктуры -- structlog `error`-event + audit event `purchase.template_missing`.
- **`GET /purchases/{id}/agreement` отдаёт 500 (не 404) при NULL template_id** (§5.3) -- сигнал поломки, не штатное "не сконфигурировано".

### v0.4 -- UI follow-ups закрыты

- **F-A1**: при empty list (после language-фильтра) -- секция "Документы компании" на CompanyOverview **скрывается целиком**. Никакого empty-state. Контентом управляет Staff (§7.1).
- **F-A2**: иконки -- **mime-based** (PDF/PNG/PPTX/...), не category-based (§7.1).
- **F-A3**: **L1-группировка** (один уровень) по верхнему сегменту path-tree, внутри группы -- плоский список карточек. Subcategory как breadcrumb на карточке. Локализация имён сегментов через i18n с title-case fallback. **Без language-табов** -- юзер видит документы своей локали + null. Empty-фильтр результат -> секция скрыта (см. F-A1) (§7.1).
- **F-T1 ОТМЕНЁН**: вопрос про bootstrap для editor'а отпадает -- editor templates в MVP не делаем (§6.3, §4.5). Bootstrap'ы в репо как `backend/scripts/seed_data/templates/_default/` используются install-скриптом для platform default'ов, не для editor'а.

### v0.3 closed (без изменений в v0.4)

- **MinIO Web UI наружу через nginx + basic-auth** (§1.1, §1.4): поддомен `storage-mc-admin.cbshome.org`, login `admin`, пароль из `MINIO_CONSOLE_BASIC_AUTH_PASSWORD`. Let's Encrypt через certbot. DNS pre-flight check.
- **`cbshome storage console`** -- печатает URL+credentials Web UI.
- **`cbshome storage reconcile <company_id>`** -- двунаправленная синхронизация MinIO ↔ БД для attachments (§3.7). Опции `--all`, `--dry-run`, `--orphans-only`, `--broken-only`.
- **Path-tree категории** (§3.2, §3.2.1): `category` это string(200) с разделителем `/`, max 5 уровней, regex `^[a-z0-9_-]+(/[a-z0-9_-]+){0,4}$`.
- **Фильтр API**: `?category=X` (exact) и `?category_prefix=Y` (LIKE prefix-match).
- **Мультиязычность как pattern** (§3.6): один attachment per language, group-by `(category, title)` на фронте.
- **Workflow Staff attachments в MVP -- через MinIO Web UI** (§3.7): Inbox pattern + companion `.cbsmeta.json`. Slug-имена произвольные.
- **Missing `.cbsmeta.json`** при reconcile = skip + WARNING. Файл остаётся в inbox.
- **AttachmentInboxMetadata Pydantic-схема** -- mirror будущего `POST /staff/.../attachments` body. Required: title only. Defaults safety-first: `is_published=false`, `is_public=false`.

### Architectural decisions (общие)

- **Q-INFRA-1** (вариант A): MinIO service account создаётся в `install_cbshome.sh` через `mc admin user svcacct add`. Root credentials живут только в `.env`.
- **Q-INFRA-2** (вариант A): Backup стратегия -- `mc mirror local/cbshome-attachments` в tarball рядом с `pg_dump`.
- **Q-STOR-1**: Multipart upload через `aiobotocore.upload_fileobj` всегда.
- **Q-STOR-2**: Presigned PUT не нужен. Frontend всегда грузит через backend.
- **Q-ATT-1**: Hard-delete -- только admin.
- **Q-ATT-2**: Rate-limit public endpoints: `60 req/min/IP` для list, `300 req/min/IP` для download.
- **Q-ATT-3**: Mime-type whitelist: `pdf, png, jpg, jpeg, webp, gif, svg, pptx, docx, xlsx, mp4, webm, txt, md`.
- **Q-ATT-4**: `order` per-category (уникальность в скоупе `(company_id, category)`).
- **Q-PUB**: Два независимых булевых флага `is_published + is_public` (не enum).
- **Q-PUR-1**: Bulk download договоров (zip) -- не делаем в MVP, follow-up.
- **Q-INV-1**: Inline iframe для PDF / image / video, скачивание для pptx / docx / xlsx / прочего.
- **Q-INV-2**: Public deep-link `/public/companies/:id/attachments/:attId` показывает один конкретный attachment + кнопка "Перейти к Компании".

**Reverted (отменённые ранее решения):**

- **Q-TPL-1, Q-TPL-2**: вопросы про preview-эндпоинт с реальными данными и WYSIWYG vs textarea -- **отменены** в v0.4. UI editor templates в MVP не делается, эти вопросы переезжают в post-MVP.
- **"Платформенный default-шаблон -- НЕТ"** (закрыто в v0.2) -- **перевёрнуто в v0.4**. Platform default ЕСТЬ (§4.9), для гарантированного fallback на свежесозданных компаниях и в тестах. См. v0.4 closed выше.
