# METRICS

Источник истины для **смысла** метрик. Числовые пороги и флаги acceptance — в корневом [`config.yaml`](../config.yaml). Не копировать пороги сюда дубликатом, который разъедется с config.

## Как заполнить

1. Перечислите метрики из `config.metrics` (имена должны совпадать).
2. Для каждой: определение, направление (↑/↓ лучше), как считается из предсказаний/логов.
3. Опишите **hard constraints** vs **soft progress** (что даёт ❌ сразу, что сравнивается с champion).
4. Задайте бакеты research pack:
   - **persist** — ошибка была у baseline и осталась у treatment;
   - **fixed** — ошибка у baseline, у treatment нет;
   - **regress** — у baseline ок, у treatment ошибка.
5. Перечислите `slice_dims` для разборов (категория, этап, длина входа, …).

## Шаблон (заменить)

### Метрики

| Имя | Направление | Определение |
|-----|-------------|-------------|
| _metric_a_ | ↓ лучше | _как считается_ |
| _metric_b_ | ↑ лучше | _как считается_ |

### Acceptance (прозой)

- Champion: `baselines.champion` в config — к чему нельзя регрессировать по hard-constraint.
- Control: опциональная точка «без treatment».
- ✅ — проходит acceptance + holdout (если `require_holdout_for_promote`).
- ⚠️ — прогресс на primary, holdout не подтверждён или частичный критерий.
- ❌ — нарушен hard-constraint или чистый regress без выгоды.

### Research buckets

Определите error-класс(ы) для persist/fixed/regress относительно labeled ref и pred treatment/baseline.

### Срезы

`slice_dims`: _заполнить_.
