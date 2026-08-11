# Протокол агента: цикл гипотез

Эксперименты и раннеры — в **целевом ML-проекте** (пути и команды задаёт проект). Этот репозиторий — knowledge-цикл и протокол. Конфиг: [`config.yaml`](config.yaml). Определения KPI: [`knowledge/METRICS.md`](knowledge/METRICS.md). Пороги и acceptance — **только** в `config.yaml` (не дублировать числа в этом файле).

## Preflight (каждый запуск)

1. Прочитай `config.yaml`: `workers`, `max_cycles`, `baselines`, `acceptance`, `banned_lines`, `preflight.reminders`.
2. Выполни чеклист из `preflight` (env, данные, доступы) — что указано для **этого** проекта.
3. Убедись, что `knowledge/METRICS.md` и `knowledge/CONTEXT.md` заполнены достаточно, чтобы понимать KPI и продукт. Если пусто — сначала онбординг (заполнить stubs), не генерировать гипотезы.
4. Очередь `knowledge/future/` (кроме README) должна быть доводима до ≥ `workers` runnable идей **после** research; в начале сессии допустима пустая очередь → шаг investigate.

## Один цикл

1. Прочитай [`knowledge/CONTEXT.md`](knowledge/CONTEXT.md), [`knowledge/past/INDEX.md`](knowledge/past/INDEX.md), **активные brief** в [`knowledge/investigate/`](knowledge/investigate/) (`open` / `partially_answered`) и все файлы в [`knowledge/future/`](knowledge/future/) (кроме README).
2. Выбери до **N=`workers`** гипотез из `future/` **разных типов/линий**; не три `refine` одной линии. Не повторяй линии из `banned_lines` и cemetery в past. У каждой — поле **Исследование:** → brief.
3. Реализуй и прогони эксперимент **средствами целевого проекта** (раннер / ноутбук / CI — как принято у продукта). Сохрани воспроизводимый артефакт: идентификатор прогона, параметры treatment, метрики primary (и holdout при необходимости), путь к `meta`/логу.
4. Сравни treatment с `baselines.control` и `baselines.champion` по правилам `acceptance` и [`METRICS.md`](knowledge/METRICS.md). Статус: ✅ / ⚠️ / ❌. Если `require_holdout_for_promote` — без успешного holdout не ставить ✅.
5. Удали протестированное из `future/` (без дублей). Запиши отчёт в `knowledge/past/` и строку в INDEX (шаблон — ниже и в [`past/README.md`](knowledge/past/README.md)).
6. **Исследование (обязательно перед шагом 7):** research pack vs champion (и/или лучший treatment):
   - сводка метрик прогона;
   - cross-run breakdown: **persist** / **fixed** / **regress** по primary error-классам из METRICS;
   - срезы по `slice_dims` из METRICS (если заданы);
   - обновить brief в `investigate/` (шаблон — [`investigate/README.md`](knowledge/investigate/README.md)).
7. Доведи `future/` до **N=`workers`** из открытого brief (квоты refine/pivot/explore). Manifest и сторонние списки **не** источник идей. Без открытого brief — сначала investigate (и analytics при нехватке цифр), не `future/`.
8. Общий вывод → до **3 bullets** в [`knowledge/CONTEXT.md`](knowledge/CONTEXT.md) (лимит CONTEXT — см. файл).

## Исследование (перед гипотезами)

**Цель:** понять *что сломано* и *что проверить*, затем писать `future/`. Не генерировать идеи «от балды».

**Минимум за цикл (после шага 5):** research pack на champion и/или лучший treatment; в brief — persist/fixed/regress, топ срезов, ❌ из INDEX; только после brief — кандидаты → развёрнутые файлы в `future/`.

**Когда brief обязателен:** очередь `future/` пуста или идеи без **Исследование:**; после серии ❌ по одной линии; перед explore/pivot вне текущего champion.

**Когда analytics обязательна** (см. [`knowledge/analytics/README.md`](knowledge/analytics/README.md)): в brief нет цифр по нужному слою; серия ❌ и непонятно что ломается; новая ось без baseline snapshot. Порядок: **analytics → brief → future/**.

## Формирование гипотез

Таксономия (обязательное поле **Тип** в каждом `future/*.md`):

| Тип | Что это | Пример vs champion |
|-----|---------|--------------------|
| **refine** | Тот же механизм, 1–2 параметра / узкий guard | порог, вес, порядок шагов |
| **pivot** | Та же цель KPI, **другой механизм** | другой этап пайплайна, другая loss/feature |
| **explore** | Другая ось архитектуры / данных / обучения | новый слой, retrieval, архитектура |
| **validate** | Holdout / repro champion или ⚠️/✅ | не занимает слот refine |

Различение: «взять Hx и покрутить X» → refine; «тот же KPI иначе» → pivot; «слой, который Hx не трогал» → explore.

**Качество текста:** поля **Идея** и **Почему** — связные абзацы (3–5 предложений), не телеграф. В **Идея**: baseline → условие триггера → действие → что не меняем (safety/guardrails проекта) → ожидаемый эффект на KPI. Опора на investigate/analytics/past. Шаблон — [`knowledge/future/README.md`](knowledge/future/README.md). Кандидат из brief **не** копировать в `future/` без разворота.

**Квоты** (после шага 5 довести очередь до N=`workers`):

- Минимум **1** файл `pivot` **или** `explore`.
- Максимум **1** `refine` от **одной** линии (линия = родительский Hyp id).
- Не больше **2** подряд `refine` по одной линии в `past/` — иначе следующий цикл **без** refine этой линии (только pivot/explore).
- `validate` не занимает слот refine; остальные слоты заполняются до N.
- Типичный портфель из 3: `1 refine + 1 pivot + 1 explore` (или `1 validate + 1 pivot + 1 explore`).

**Анти-зацикливание:**

- Перед генерацией: последние 5 гипотез в INDEX. Если ≥3 из 5 — одна линия → цикл без refine этой линии.
- Не порождать refine от ❌ без нового механизма защиты / ограничения риска.
- Идея обязана указывать **механизм**, **тип**, **Исследование:** и развёрнутую формулировку — не «ещё чуть подкрутить».
- Если безопасного refine нет — слот explore; если нет открытого brief — сначала исследование.

## Параллельность

- До `workers` гипотез **одновременно**, если инфраструктура проекта это позволяет.
- Снижай параллелизм только при явных сбоях инфраструктуры; после стабилизации — верни `workers` из config.
- Не reuse предсказаний/артефактов других arms без явной пометки в meta (`reuse_*`).

## Воспроизводимость и анти-переобучение

**Запрещено:**

- Захардкоженные id/кейсы/категории «под один split» (golden lists только как **holdout**, не для подбора правил).
- Правила вида «если id=…» или подгонка regex/правил под reason конкретного прогона.
- Подгонка гипотезы под один primary split без проверки на holdout (когда holdout задан).
- Офлайн-склейка двух arms без реального прогона treatment — только exploratory; для ✅ нужен полный прогон по правилам проекта.

**Обязательно:**

- Каждый прогон: meta с `hypothesis`, split, параметры treatment, workers/параллелизм, `git_commit` (если есть).
- Treatment = **параметризуемое** изменение (функция/конфиг/флаг), не копипаста под один датасет.
- Primary / holdout splits — из `config.yaml`.
- Идеи в `future/` формулировать **обобщённо** (механизм), не «исправить id …».

## Стоп

- После **`max_cycles` подряд** — остановись и кратко суммируй сессию.
- `future/` пуст и нет безопасных идей без регрессии по hard-constraint из acceptance — стоп.
- Hard-constraint из acceptance нарушен vs champion без явного guard в дизайне — отклонить (❌).

## Шаблон отчёта (`knowledge/past/hxx_slug.md`)

```markdown
# Hxx — название
Статус: ✅/⚠️/❌ | Primary: <split> | Holdout: … | N: …
Идея: 1–2 предложения (обобщённый механизм, без id)
Метрики: primary (+ holdout) vs champion / control — имена из METRICS.md
Вердикт: принять / отклонить / доработать
Почему: 2–4 пункта (persist/fixed/regress, топ срезов)
Repro: run_id, workers, путь к meta/логу
Next: что пробовать дальше
```
