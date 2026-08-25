# Дизайн-система CBSHOME — реестр решений и план правок

**Источник:** `observed.yaml` от `ui-extractor alpha-b2 barrel-aware`, репозиторий `aivis-one/cbshome@main` (100 компонентов).
**Метод идентичности:** «один элемент или разные?» решается по **контракту (props/emits/slots) + композиции/поведению**, а не по визуальному сходству.
**Статус документа:** рабочая затравка. Правки здесь — *запланированы, но не применены*.

## Как читать статусы
- **✅ подтверждено** — проверено по исходникам, решено делать (готово к реализации).
- **❌ отклонено** — проверено по исходникам, решено НЕ делать (с обоснованием), чтобы не переоткрывать заново.
- **🔍 кандидат** — выявлено скелетом, но требует чтения исходников перед решением.
- **⚠ слепая зона** — статический анализ не видит цель (динамические компоненты), нужен ручной взгляд.

**Связь с техдолгом команды.** У команды есть собственный бэклог техдолга (`TD-F*` в `CBSHOME-Frontend.md`). Мы его *учитываем*: где наши находки пересекаются — ставим кросс-ссылку (`см. TD-Fxx`), но не дублируем его. Фокус нашего реестра — идентичность/консолидация компонентов, которой в `TD-F` нет.

---

## Итог и порядок действий

Разобрано 7 кластеров. Сводка:

| ID | Кластер | Решение | Действие |
|----|---------|---------|----------|
| DS-001 | 4 аутентифицированных шелла | ✅ слить | один `AppShell`, табы из `meta.shell`; −3 файла |
| DS-002 | `CCard` / `CDivider` / `HomeView` | ✅ удалить | мёртвый код (греп-подтверждён); −3 файла |
| DS-C2 | форм-поля `CInput`/`CTextarea`/`CSelect` | ✅ дедуп обёртки | вынести `CField` (markup+CSS трижды) |
| DS-C4 | `EventEditor` / `PostListEditor` | ❌ не сливать → извлечь | `useCrudModal` + `usePaginatedList` |
| DS-C3 | оверлеи + детальные шиты | ❌ не сливать | `useDetailSheet` пограничен (2 экз.) |
| DS-C1 | Attachments | ❌ не сливать | их **TD-F18** (хелпер `formatBytes`) |

**Рекомендуемый порядок** (от низкого риска/высокой ценности к большему радиусу):
1. **DS-002** — удалить 3 мёртвых файла. Нулевой риск, греп-подтверждён. Не забыть строки экспорта в баррель-индексе.
2. **DS-C2** — `CField`. Убирает тройной дубль обёртки, локально.
3. **DS-001** — `AppShell`. −3 файла; дискриминатор (`meta.shell`) уже в коде.
4. **DS-C4** — `useCrudModal` / `usePaginatedList`. ROI подтверждён, но трогает несколько секций — аккуратно.
5. **DS-C3** `useDetailSheet` — отложить до 3-го экземпляра (`CertificateSheet`).

**Что показал эксперимент (методология):**
- Скелет надёжен в **структуре**: сироты (`usedBy=0`), маршрутизация (`routed`), граф композиции (после фикса бочки) — всё подтвердилось исходником.
- Скелет — генератор **кандидатов**, но каждый вопрос «это одно и то же?» решался только исходником. Из 6 «merge?»-кандидатов слиянием оказался **один** (шеллы); остальные — «держать раздельно», а ценность вышла в **извлечениях** (композаблы/`CField`) и **удалениях**.
- Скелет **слеп** к дублированию CSS/markup (DS-C2) и к расходящейся проводке (Attachments: API/store/toast). Для этого — исходник либо CSS-level инструмент.
- Реестр одинаково ценен и для «делать», и для обоснованных **«НЕ делать»** — чтобы их не переоткрывали в каждом новом чате.

**Не разобрано:** 10 слепых зон `<component :is>` (ниже) — каждая требует чтения файла; низкий приоритет.

---

## DS-001 — Слить четыре аутентифицированных шелла в один `AppShell` — ✅ подтверждено

**Что обнаружено (по исходникам).** `InvestorShell`, `AgentShell`, `CompanyShell`, `StaffShell` совпадают **дословно**, отличаясь ровно одной строкой — какой константой табов кормится `CTabBar`:

```
import { INVESTOR_TABS } from '@/router/tabs'  →  <CTabBar :items="INVESTOR_TABS" />
import { AGENT_TABS }    ...                    →  <CTabBar :items="AGENT_TABS" />
import { COMPANY_TABS }  ...                    →  <CTabBar :items="COMPANY_TABS" />
import { STAFF_TABS }    ...                    →  <CTabBar :items="STAFF_TABS" />
```

Контракт у всех четырёх пустой (нет props/emits/slots), композиция идентична (`CHeader` + `<RouterView>` + `CTabBar` + `CToast`), стили идентичны. По правилу «одинаковый контракт + одинаковое поведение» — это **один компонент в четырёх копиях**.

**Дискриминатор уже существует в коде.** В `router/index.ts` каждая shell-запись несёт `meta.shell` — ровно ключ роли, наследуемый всеми детьми через merge мета:

```
/investor → meta: { roles: ['investor','agent'], shell: 'investor' }
/agent    → meta: { roles: ['agent'],            shell: 'agent' }
/company  → meta: { roles: ['company'],          shell: 'company' }
/staff    → meta: { roles: ['staff'],            shell: 'staff' }
```

А `tabs.ts` держит четыре конфига, которые маппятся на эти ключи один-в-один. Значит параметризация бесплатна: `AppShell` читает `route.meta.shell` и выбирает табы из карты.

**`PublicShell` — НЕ входит в слияние.** Другой контракт и поведение: нет `CTabBar` (у анонима нет навигации между табами), `CHeader` несёт CTA «Sign in» в слоте `right`, есть реальная логика (`safeNavigate`, расчёт `?next=`, фильтрация `NavigationFailure`), `meta.public`. Это отдельный элемент.

**Запланированные правки:**
- [ ] `frontend/src/router/tabs.ts` — добавить карту `export const TABS_BY_SHELL: Record<string, TabItem[]> = { investor: INVESTOR_TABS, agent: AGENT_TABS, company: COMPANY_TABS, staff: STAFF_TABS }`.
- [ ] `frontend/src/components/layout/AppShell.vue` — новый компонент: `const tabs = computed(() => TABS_BY_SHELL[route.meta.shell] ?? [])`, шаблон/стили как у старых шеллов, `<CTabBar :items="tabs" />`.
- [ ] `frontend/src/router/index.ts` — у четырёх записей (`/investor`, `/agent`, `/company`, `/staff`) поменять **только** `component` на `AppShell`; `meta` не трогать (тег `shell` уже там).
- [ ] Удалить `InvestorShell.vue`, `AgentShell.vue`, `CompanyShell.vue`, `StaffShell.vue`.
- [ ] (TS-доводка, опц.) расширить `RouteMeta` полем `shell?: string`.

**Сохранность поведения.** Кейс «агент ходит по investor-экранам» сохраняется 1:1: на `/agent/*` `meta.shell='agent'` → `AGENT_TABS`, на `/investor/*` (доступно агенту) → `INVESTOR_TABS` — ровно как сейчас. Итог: **4 файла → 1**, без изменения поведения.

---

## Кандидаты — требуют чтения исходников 🔍

### DS-C1 — `AttachmentsSection` / `PublicAttachmentsSection` — ❌ не сливать (решено по исходникам)
Скелет дал кандидата на слияние (идентичный контракт `{ companyId }` + идентичная композиция). Исходник отбил: `PublicAttachmentsSection` в шапке несёт раздел **«WHY A SEPARATE COMPONENT (not a parameterised AttachmentsSection)»** — команда осознанно держит их раздельно, потому что между auth- и public-флоу расходятся четыре вещи, невидимые скелету (они в логике скрипта): **API** (`listAttachments` vs `listPublicAttachments`), **скачивание** (`downloadAttachment` vs `downloadPublicAttachment`), **состояние** (`useAttachmentsStore` vs локальный стейт), **тосты** (`useToast` vs `usePublicErrorToast` на 429). Проп `:isPublic` расплескал бы if-ветки по call-site. По нашему правилу «сливаем только при одинаковом поведении» merge не срабатывает: контракт совпадает, поведение — нет.

**Реальный дубль — на уровне хелпера, и он уже у команды.** `formatBytes` дублируется в обеих секциях байт-в-байт при существующем `@/utils/format.ts::formatBytes`. Это их **TD-F18** (заменить копии на импорт) — нам сверх кросс-ссылки тут делать нечего.

`PublicProductsSection` — отдельный элемент (другой домен: продукты, композит `ProductCard`), в слияние не входил.

**Урок методологии:** скелет видит контракт и композицию, но не видит проводку (API/store/toast). На шеллах эта проводка совпадала → сливать; здесь расходится → не сливать. Решает поход в исходники, а не отпечаток.

### DS-C2 — Форм-поля — не сливать ✅; тройной дубль обёртки → `CField`

Исходник уточнил картину. `CInput` / `CTextarea` / `CSelect` — разные типы полей (не слияние), но у всех трёх **тройная копия обёртки**: и markup (`<div class="c-input-group"><label class="c-input-label">…</label>{control}<div class="c-input-error">…</div></div>`), и CSS (`.c-input-group` / `.c-input-label` / `.c-input-error` + базовые стили поля с `:focus`/`--error`) — байт-в-байт в трёх файлах. Это за порогом «2-3».

**Действие:** вынести обёртку в `CField` (слот под контрол + `:label`/`:error`); каждый примитив рендерит внутри только свой `<input>`/`<select>`/`<textarea>`. Либо легче — общие CSS-классы поля в один стиль-файл. Нейминг пропов уже консистентен (дрейфа нет). `CCheckbox` — **не** из этого семейства (boolean-тоггл, своя разметка).

> Этот дубль — в CSS/markup, которого скелет не видит вовсе; всплыл только в исходнике. В бэклоге `TD-F` его, похоже, нет — реестр нашёл новое.

### DS-C3 — Оверлеи (`CModal` / `CBottomSheet`) + детальные шиты — не сливать ✅; шит-композабл пограничный (ROI 🔍)

**Оверлеи — не сливать.** `CBottomSheet` в шапке прямо: «Matches CModal's API shape for familiarity: same open prop, same close event» — **намеренная пара-близнецы**, делящие *форму API*, но не один параметрический компонент. Общее — только механика (`Teleport` + оверлей + close-on-overlay, 3 строки `onOverlay`); расходится **основная масса**: centered+scale+кнопка-X (`showClose`) у Modal против bottom+slide-up+drag-handle+`title`/`header`-слот у Sheet. Слить в один `variant` = гейтить расходящийся chrome пропами (тот же if-scatter, что отбили на Attachments) ради 3 строк. Правильный уровень общего здесь — **совпадение контракта, а не кода** (в русле их FP-19/FP-20: purpose-built держим раздельно).

**Детальные шиты — не сливать; малый композабл-кандидат.** `AgreementSheet` (`{open, mode, id, legalBasis}`, богаче: действие + `CButton`) и `TransactionDetailSheet` (`{open, transactionId}`) — разные сущности. Общее ядро — «fetch-on-open»: `watch([open,id]) → fetch → loading/error → reset-on-close` (+ epoch-инвалидация in-flight). Кандидат на `useDetailSheet(fetchFn)`. **Но экземпляров пока 2** → ровно на пороге «2-3», не явный выигрыш (в отличие от `useCrudModal`). Ждать 3-й (в доке упоминается `CertificateSheet` — построят, перевесит).

### DS-C4 — `EventEditor` / `PostListEditor` — не сливать ✅; CRUD-скелет → два композабла (ROI ✅)

Исходник: оба — **один паттерн** «пагинированный список + create/edit/delete через модалку, гейт `canEdit`». Идентична вся стейт-машина: список (`items/total/page/perPage=20/loading/error`), модалка (`showEditor/editId` null=создание/`saving`), удаление (`deleteTarget/deleting`), гейт FP-23 (оба бейлят с `[XxxEditor] … blocked: no content_manage`), пагинация со «шагом назад при удалении последней строки» (в PostListEditor это BUG-38-01), `watch(page)`/`onMounted`. Расходятся только **сущность/форма/API**: events — datetime-поля + фильтр upcoming; posts — owner-picker (`CSelect`), теги, проп `fixedOwner`.

**Не сливать** — два разных элемента (разные сущности и формы), как Attachments. Но разница принципиальная: у Attachments был задокументированный «WHY A SEPARATE COMPONENT» и расходилась *проводка*; здесь общая часть — **поведенческая и крупная** (вся CRUD-стейт-машина идентична).

**Цель — не общий компонент, а композабл.** `useCrudList<T>({ fetch, create, update, remove, canEdit })` забирает идентичную стейт-машину; форму каждый редактор оставляет себе. Чище компонентной базы (формы расходятся), идиоматично для Vue 3, переиспользуемо будущими staff-редакторами. (Прецедент культуры: `PostListEditor` уже делят `StaffNewsView` + `StaffCompanyPostsSection` через `fixedOwner`.)

**ROI — подтверждён, форму уточнили (по исходникам).** Скелет-фильтр дал CRUD-сигнатуру (`CModal`+`CEmptyState`+поле) у ≥6 staff-секций; `StaffCompanyRoadmapSection` подтверждён исходником как полноценный 3-й экземпляр (CRUD + reorder, тот же FP-23-гейт `[…] blocked: no company_manage`). Это за порогом «2-3».

Но 3-й экземпляр **уточнил абстракцию**: у Roadmap *другой слой данных* — нет пагинации и своего fetch, он читает roadmap инлайн из родительского контекста (`STAFF_COMPANY_KEY`, PERF-40-01) и зовёт `ctx.reload()`. Единый монолитный `useCrudList` (с fetch+пагинацией) переобучился бы на двух пагинируемых редакторах и не сел бы на Roadmap. Правильнее **разнести на два композабла по ответственностям**:
- `useCrudModal` — модалка create/edit/delete + FP-23-гейт (`openCreate/openEdit/openDelete/handleSave`, `showEditor/editId/saving`, `deleteTarget/deleting`, guard + `console.warn`). Повторяется у **всех** CRUD-секций (≥3-6) — наибольший ROI.
- `usePaginatedList<T>(fetch)` — `items/total/page/loading/error` + `watch(page)` + шаг-назад (BUG-38-01). Только у пагинируемых (EventEditor, PostListEditor, list-вью вроде Users/Payments).

Roadmap взял бы `useCrudModal`, но не `usePaginatedList`. Какие секции пагинируют, а какие читают инлайн — уточняется при самом рефакторе; направление (два композабла) зафиксировано.

**Ортогонально:** `.filter-chip` (EventEditor + TemplatesSection + InvestorEventsView) — их **TD-F17**, отдельный дедуп в `CFilterChip`.

---

## DS-002 — Удалить три мёртвых компонента — ✅ подтверждено (grep)

`grep -rn` по `frontend/src` (за вычетом баррель-индекса и собственного файла) вернул **пусто** по всем трём, и `HomeView` отсутствует в `router/index.ts`. Скелетные `usedBy=0` / `routed=false` подтверждены кодом — ни одного консумера.

- **`HomeView`** (`src/views/HomeView.vue`) — легаси-скаффолд; «домашний» экран вытеснен `LoadingView` + редиректом по роли. Удалить файл.
- **`CCard`** (`src/components/ui/CCard.vue`, `{ hoverable, padding }` + slot) — generic-карточку обходят все реальные карточки (`CompanyCard`/`ProductCard`/`EventCard`/`CStatCard` свёрстаны сами). Мёртвый груз. *(Если решите держать как намеренный примитив про запас — это сознательный выбор.)*
- **`CDivider`** (`src/components/ui/CDivider.vue`, `{ text? }`) — разделитель «— or —», вероятно заскаффолен под отложенную «Войти через Telegram». *(Оставить, если Telegram-логин скоро вернётся.)*

**Запланированные правки:**
- [ ] Удалить `src/views/HomeView.vue`.
- [ ] Удалить `src/components/ui/CCard.vue` **и** строку `export { default as CCard } from './CCard.vue'` из `components/ui/index.ts`.
- [ ] Удалить `src/components/ui/CDivider.vue` **и** строку `export { default as CDivider } from './CDivider.vue'` из `components/ui/index.ts`.

> `CCard`/`CDivider` экспортируются из баррель-индекса — удалить файл без снятия строки экспорта сломает билд.

---

## Слепые зоны `<component :is>` (10) ⚠

Цель динамического компонента статикой не взять — нужен ручной разбор:
`CTabBar`, `AttachmentsSection`, `PublicAttachmentsSection`, `AgentMoreView`, `AgentSettingsView`, `CompanyDashboardView`, `CompanySettingsView`, `InvestorMoreView`, `TransactionsView`, `PublicAttachmentLandingView`.

---

## Как обновить снимок
Перегнать `ui-scan.sh` на сервере (новый `extractor.mjs` рядом с ним). Признак свежего билда — строка `>> ui-extractor alpha-b2 barrel-aware` в выводе и поле `extractor:` в `observed.yaml`. Признак достроенного графа — у примитивов (`CButton`, `CInput`…) непустой `usedBy`.
