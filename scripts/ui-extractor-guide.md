# ui-extractor — инструкция (для будущих чатов)

Детерминированный снимок дизайн-системы Vue 3 → `observed.yaml`. Алгоритмический разбор исходников: контракты + граф композиции. Это **генератор кандидатов и структурных фактов**, а не судья идентичности (см. «Чему верить» ниже).

Два файла, лежат рядом:
- **`extractor.mjs`** — сам экстрактор (Node ESM). Запускается внутри окружения, где установлены зависимости фронта.
- **`ui-scan.sh`** — одноразовый рецепт запуска на сервере (поднимает контейнер, отдаёт `observed.yaml`).

---

## TL;DR — снять снимок на сервере

```bash
cbshome update                 # подтянуть свежий код в управляемый чекаут (обычный флоу)
# положить extractor.mjs рядом с ui-scan.sh (напр. в /tmp), затем:
./ui-scan.sh                   # -> ./ui-scan-out/observed.yaml
```

Признак свежего билда в выводе — строка `>> ui-extractor alpha-b2 barrel-aware` и поле `extractor:` в `observed.yaml`. Признак достроенного графа — у примитивов (`CButton`, `CInput`, …) непустой `usedBy`.

---

## Почему `ui-scan.sh` устроен именно так

- **Источник правды — GitHub-репо** `aivis-one/cbshome`, фронт: Vue 3 SFC + TS strict + Vite + Vue Router + Pinia + vue-i18n + lucide.
- **Задеплоенный фронт — статический nginx-образ** (ни node, ни исходников), сканировать внутри него нельзя.
- **Но исходники фронта уже есть на хосте** в управляемом чекауте, который `cbshome update` держит в синке с GitHub: `/opt/cbshome/repo/frontend`.
- Поэтому скрипт **НЕ клонирует**, **НЕ трогает деплой-ключи** и **НЕ exec-ается в рабочие контейнеры.** Он поднимает одноразовый `node:22-slim` поверх этого чекаута: копирует исходники внутрь (копия хоста не меняется — монтируется `:ro`), ставит зависимости фронта + `vue-component-meta`/`js-yaml`, гоняет экстрактор, пишет `observed.yaml` на хост, контейнер выбрасывается.
- **tsconfig подбирается автоматически:** Vite дробит конфиг, и алиасы (`paths`) часто лежат в `tsconfig.app.json`, а `tsconfig.json` держит только project references. Скрипт грепает `"paths"` и берёт тот, где они реально есть.

## Прямой запуск (для других окружений)

```bash
node extractor.mjs <frontendRoot> [outFile] [--repo X] [--ref Y] [--tsconfig FILE]
# пример:
node extractor.mjs /src/frontend /out/observed.yaml --repo aivis-one/cbshome --ref main
```

- `outFile` опущен или `-` → stdout.
- `--tsconfig` по умолчанию `tsconfig.json` (укажи `tsconfig.app.json`, если алиасы там).
- **Требуется установленным в целевом фронте:** `vue`, `typescript`, `vue-component-meta`, `@vue/compiler-sfc`, `@vue/compiler-dom`, `js-yaml`.

---

## Что на выходе (`observed.yaml`)

```
meta:
  repo, ref, generatedAt (ISO), frontendRoot, componentCount
  extractor: "ui-extractor alpha-b2 barrel-aware"   # self-id билда
components[]:
  name, kind, path
  role            # ведущий англоязычный комментарий <script setup> (или null)
  routed          # bool: импортируется ли .vue из src/router/*.ts (lazy import)
  routerViewSeam  # bool: шаблон содержит <RouterView>
  props[]  { name, type, required, default? }
  emits[]  { name, payload }
  slots[]  { name }
  composes[]      # дети-компоненты (по тегам шаблона, резолв через импорты)
  usedBy[]        # обратные рёбра composes
  error?          # если разбор этого файла упал — маркер, файл не теряется
gaps:
  dynamicComponents[]  { in, note }   # <component :is> — цель не статична
  unresolvedTags[]     { in, tag }    # локальный тег, не привязанный к .vue
  extractionErrors[]   { in, error }  # пофайловые падения
```

- **`kind`** по пути: `src/views/` → `view`; `src/components/layout/` → `layout`; `src/components/ui/` → `ui`; прочее в `src/components/` → `domain`; иначе `other`.
- Компоненты отсортированы по `kind` (ui, domain, layout, view, other), затем по имени.

---

## Чему верить, а где слепые зоны

**Надёжно (структура):** сироты (`usedBy=0`), маршрутизация (`routed`), `routerViewSeam`, граф композиции (после фикса бочки). Как генератор кандидатов на консолидацию — тоже надёжно.

**Слеп к:**
- **дублированию CSS/markup** — он не анализирует ни стили, ни разметку дальше тегов. Тройной `CField` (DS-C2) виден только в исходнике или через `jscpd`.
- **расходящейся проводке** — одинаковый контракт может скрывать разные API/store/toast (Attachments, DS-C1).
- **динамике** `<component :is>` — цель уходит в `gaps.dynamicComponents`, её берут руками.

**Вывод:** каждый вопрос «это одно и то же / сливать?» решается **исходником**, а не скелетом. Скелет сужает, источник решает. Инструменты под слепые зоны — в `tooling-recommendations.md` (`jscpd`, `ast-grep`, `dependency-cruiser`).

---

## Внутренности, которые стоит знать (чтобы не переоткрывать)

- **Резолв бочки (barrel).** Примитивы импортятся как `import { CButton } from '@/components/ui'` — это папка/`index.ts`, а не `.vue`. Экстрактор читает реэкспорты `export { default as X } from './X.vue'` и маппит имя экспорта → `.vue`; фолбэк — `<dir>/<Name>.vue`. Без этого у всех примитивов `usedBy` был бы пуст. Уровень реэкспорта пока один.
- **tsconfig — через парсер TypeScript** (`ts.readConfigFile` + `parseJsonConfigFileContent`), не самописный JSONC-стрип: пути содержат `/*` и `*/`, наивная регулярка их съедает. Парсер тянет и `extends`, и trailing commas.
- **Builtins сплющиваются** (lowercase + убрать дефисы), чтобы `<RouterLink>` и `<router-link>` оба матчились; `<component>`/`<RouterView>` обрабатываются отдельно.
- **Пофайловый try/catch:** один битый SFC не валит скан — компонент остаётся с полем `error`, плюс запись в `gaps.extractionErrors`.
- **Контракты:** `vue-component-meta` (`createChecker` + `getComponentMeta`); глобальные пропы отфильтрованы, у опциональных снят хвост ` | undefined`.

---

## Обновить и сравнить с реестром

1. `cbshome update` → `./ui-scan.sh` → новый `observed.yaml`.
2. Сдиффить с `design-system-decisions.md`: новые сироты, изменённые контракты, новые `composes`/`usedBy`.
3. **Расхождения и есть новый дрейф** — то, что попадает в реестр следующим решением.

## Рядом
- `design-system-decisions.md` — реестр решений (✅ делать / ❌ не делать) + порядок правок.
- `tooling-recommendations.md` — OSS-инструменты под слепые зоны и координацию.
