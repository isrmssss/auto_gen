# analytics — данные для гипотез

Сюда складываем **скрипты** (в целевом проекте или локально) и **результаты** (md/json), на которых строятся investigate briefs и `future/`. Не дублирует `past/` (вердикты) и `METRICS.md` (KPI SoT).

```
knowledge/analytics/
  README.md
  scripts/     # опционально: runnable analytics
  results/     # md summaries (+ optional json)
```

## Когда обязательно запускать (до `future/`)

| Ситуация | Действие |
|----------|----------|
| Brief без цифр по нужному слою | снять snapshot слоя → `results/*.md` |
| Серия ❌ по одной линии и непонятно *что* ломается | breakdown + распределения pred/ref / ошибок |
| Новая ось без baseline snapshot | сначала baseline analytics → brief → future |
| Очередь пуста / explore вне champion | минимум distribution / error anatomy по METRICS |

Порядок: **analytics → investigate brief → future/**. Ссылка в гипотезе: `Исследование:` + путь к `results/*.md` или brief.

## Правила

- Не хардкодить id кейсов в results для подбора treatment.
- Results — навигация для brief; acceptance всё равно vs champion по `config.yaml`.
- Старые results не удалять без нужды; для нового цикла — новый файл.

На старте шаблона `scripts/` и `results/` можно создать по мере надобности — обязателен только этот README.
