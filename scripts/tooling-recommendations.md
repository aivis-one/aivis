# Опенсорс-инструментарий против дрейфа (DRY/консистентность)

**Зачем:** командный вайбкодинг плодит расхождения, когда двое делают одно ТЗ с разных концов. Ниже — готовые OSS-инструменты, привязанные к находкам из нашего разбора дизайн-системы CBSHOME (`design-system-decisions.md`). Для каждого: что он закрывает у нас и как включить — CLI, MCP (агент дёргает во время работы), CI (бэкстоп на мёрже).

**Дата:** июнь 2026. Состояние сверено по вебу, но версии/флаги дрейфуют — перед внедрением проверить актуальную доку.

---

## Сводка

| Инструмент | Что закрывает у нас | MCP | Как включить (старт) |
|---|---|---|---|
| **knip** | DS-002: мёртвые файлы/экспорты (`CCard`/`CDivider`/`HomeView`) | ✅ | `npx knip` |
| **jscpd** | DS-C2 `CField`, TD-F18 `formatBytes`, TD-F17 `.filter-chip` — дубль CSS/markup | ✅ | `jscpd .` |
| **ast-grep** | 10 слепых зон `<component :is>`; линт-правила FP-19/FP-20, «поля только через `CField`» | через napi | `ast-grep scan` |
| **dependency-cruiser** | граф композиции + архитектурные правила (то, что хардкодили в экстракторе) | — | `npx depcruise src` |
| **Storybook** (+ `vue-component-meta`) | discovery: чтобы второй не делал `EventEditor` заново | — | `npx storybook@latest init` |
| **spec-kit** + `constitution.md` | корень «двух концов»: общий spec + место для наших «НЕ делать» | — | `specify init` |
| **ts-morph / jscodeshift** | исполнение правок (`CField`, `AppShell`) по всему репо | — | кодмод-скрипт |
| **Style Dictionary** | дрейф токенов в `variables.css` | — | `style-dictionary build` |

---

## Слой 1. Сканеры-улики (собирают факты, идентичность НЕ решают)

### knip — мёртвый код
Находит неиспользуемые файлы, экспорты и зависимости в JS/TS. `ts-prune`, `depcheck`, `tsr` заархивированы и сами рекомендуют knip. 150+ плагинов (Vue/Vite/Storybook), auto-fix.
- **Наша привязка:** DS-002 — `CCard`/`CDivider`/`HomeView` он выдал бы сам, включая «висящие» экспорты в баррель-индексе.
- **CLI:** `npx knip` (zero-config старт; тонкая настройка — `knip.json`).
- **MCP:** есть MCP-сервер (в расширении для редактора) — агент сам пишет `knip.json` и спрашивает «что мёртвое».
- **CI:** шаг `npx knip` в пайплайне (ненулевой выход при находках).

### jscpd — копипаст (то, к чему скелет слеп)
Текстовый/токенный детектор дублей. С v4.2 ловит **кросс-форматно**: блок `<script>` в `.vue` матчится против `.ts`. v5 — на Rust, v4 с Node-API ещё жив.
- **Наша привязка:** тройной `CField` (обёртка `.c-input-group`/`.c-input-label`/`.c-input-error` + базовые стили поля), `formatBytes` (их TD-F18), `.filter-chip` (TD-F17). Это дубль CSS/markup, который контракты не видят.
- **CLI:** `jscpd .` (v5) или `npx jscpd@4 src` (Node-API). Порог в `.jscpd.json` (`minTokens`, `threshold`).
- **MCP:** с v4.1 — MCP-сервер + Agent Skill + `--reporters ai`; Claude/Cursor гоняют проверку дублей в своём процессе.
- **CI:** `jscpd . --threshold <бюджет%>` — падает при превышении.

### ast-grep — структурный поиск/линт/переписывание
По AST (tree-sitter, Rust), Node-биндинг `@ast-grep/napi`. AST-aware, в отличие от текстового Comby.
- **Наша привязка:** (1) добить 10 слепых зон `<component :is>` одним паттерном; (2) превратить словесные правила в линтер — «поле формы обязано идти через `CField`», «инлайновый back-link запрещён, только `CBackLink`» (их FP-19/FP-20).
- **CLI:** поиск — `ast-grep run -p '<pattern>'`; правка — добавить `-r '<rewrite>'`; проект-правила — `ast-grep scan` (`sgconfig.yml` + `rules/*.yml`).
- **MCP:** официального можно не ждать — оборачивается в кастомный MCP-тул через napi-биндинг.
- **CI:** `ast-grep scan` с `severity: error` на правилах.

### dependency-cruiser (+ madge) — граф и архитектурные правила
Резолвит импорт-граф и валидирует правила связности декларативно.
- **Наша привязка:** это наш граф композиции из коробки. Правила-`forbidden`: «вью не импортит другой вью», «примитив (`ui/`) не тянет `domain/`», «нет циклов».
- **CLI:** `npx depcruise --init` (скаффолд конфига) → `npx depcruise src`; картинка — `npx depcruise src --output-type dot | dot -Tsvg -o graph.svg`. Циклы быстро — `npx madge --circular src`.
- **CI:** нарушение `forbidden`-правила → ненулевой выход.

---

## Слой 2. Каталог (чтобы ВИДЕТЬ, что уже есть — против повторного изобретения)

### Storybook (+ docgen `vue-component-meta`) / Histoire
Каталог компонентов в изоляции. Storybook на `vue3-vite` использует ровно `vue-component-meta` как docgen — ту же либу, что наш экстрактор, так что контракты в сторибуке и в `observed.yaml` совпадают. Histoire — Vite-native под Vue, легче, но альфа-зрелость и меньше аддонов.
- **Наша привязка:** бьёт прямо в discovery-провал «двух концов» — второй разработчик видит `EventEditor`/`CButton` и не делает их заново.
- **CLI (Storybook):** `npx storybook@latest init`; docgen-плагин `vue-component-meta` прописывается в `.storybook/main.ts` (важно указать `tsconfig.app.json`, иначе не резолвятся `@/...`-алиасы). Билд — `npm run build-storybook`, деплой статикой.
- **CLI (Histoire):** `npm i -D histoire @histoire/plugin-vue` → `histoire dev` / `histoire build`.

---

## Слой 3. Координация (бьёт в корень «двух концов»)

### GitHub spec-kit + AGENTS.md / CLAUDE.md
Spec-driven development для агентов (30+ агентов, вкл. Claude Code). Поток: spec → plan → tasks → `analyze` → имплементация, где спецификация — единый источник правды для всех агентов.
- **Ключевое — `constitution.md`:** «non-negotiable» принципы, которым агент следует на каждой фазе, явно включая следование внутренней дизайн-системе. **Это место, где живут наши решения** — `design-system-decisions.md` (особенно «НЕ сливать» DS-C1/C3) и нормы FP-19/FP-20, «выносить на 2-3-м дублировании».
- **Наша привязка:** spec → plan → tasks = «декомпозировать ОДИН раз против общих артефактов». Оба конца строят из одного spec'а и одной конституции, а не из двух голов. Шаг `analyze` ловит нарушения конституции до кода.
- **CLI:** установить Specify CLI (через `uv`), затем `specify init <project>` с интеграцией под своего агента; далее команды `/speckit.constitution`, `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, `/speckit.analyze`. Точные флаги — в репозитории `github/spec-kit`.

---

## Слой 4. Исполнение (когда решение принято)

- **ts-morph / jscodeshift** — программные кодмоды, чтобы провести `CField`-экстракцию или слияние в `AppShell` по всему репо одним проходом, а не руками. ts-morph — удобный TS-API над компилятором; jscodeshift — `npx jscodeshift -t transform.ts ...`.
- **Style Dictionary** — если поедет дрейф токенов: один источник токенов → генерация `variables.css`/CSS-переменных. `style-dictionary build --config config.json`.

---

## Как это складывается в конвейер

1. **Стандарты — в `constitution.md`** (spec-kit): курируемые решения из нашего реестра, включая обоснованные «НЕ делать».
2. **Во время работы (агент через MCP):** `knip` («это мёртвое?»), `jscpd` («это уже есть текстуально?»), плюс каталог Storybook для глаз. Это и есть проверка «а есть ли уже такое?» ДО мёржа — оба конца получают один инструмент.
3. **На мёрже (CI-бэкстоп):** `knip` + `jscpd` (бюджеты) + `ast-grep scan` (правила-линтер) + `dependency-cruiser` (архитектурные границы). Не блок ради блока, а «сошлись на DS-решение или обоснуй».
4. **Для самих правок:** `ast-grep -r` / `ts-morph` / `jscodeshift`.

## Keystone (в русле эксперимента)

**Ни один из них не решает идентичность за тебя.** knip даёт факт «мёртвое», jscpd — «текстуально дублируется», ast-grep — «структурно совпадает». Но «сливать ли это?» остаётся человеческим решением — вспомни Attachments: контракт идентичен, а сливать нельзя (расходится проводка). Поэтому keystone — `constitution.md` как место курируемых решений, а сканеры — поставщики улик в него.

---

## Источники (проверить актуальность)
- knip — https://knip.dev/ , https://github.com/webpro-nl/knip
- jscpd — https://jscpd.dev/ , https://www.npmjs.com/package/jscpd
- ast-grep — https://ast-grep.github.io/
- dependency-cruiser — https://github.com/sverweij/dependency-cruiser ; madge — https://github.com/pahen/madge
- Storybook (Vue/Vite, docgen) — https://storybook.js.org/docs/get-started/frameworks/vue3-vite ; Histoire — https://histoire.dev/
- spec-kit — https://github.com/github/spec-kit
- ts-morph — https://ts-morph.com/ ; jscodeshift — https://github.com/facebook/jscodeshift ; Style Dictionary — https://amzn.github.io/style-dictionary/
