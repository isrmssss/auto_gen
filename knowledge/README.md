# knowledge

База знаний цикла исследований.

| Папка / файл | Содержимое |
|--------------|------------|
| [`CONTEXT.md`](CONTEXT.md) | Продукт, данные, устойчивые выводы (компактно) |
| [`METRICS.md`](METRICS.md) | Определения KPI и смысл acceptance (пороги — в `config.yaml`) |
| [`past/`](past/) | Что уже протестировано: отчёты, INDEX |
| [`investigate/`](investigate/) | Разбор проблемы **до** гипотез: вопрос, цифры, кандидаты |
| [`future/`](future/) | Что тестировать дальше: идеи, привязанные к `investigate/` |
| [`analytics/`](analytics/) | Снимки слоёв данных, когда brief не хватает цифр |

Порядок: **investigate → future → experiment → past**. Агент читает `investigate/` и `future/` каждый цикл. После теста — отчёт в `past/`, файл убрать из `future/`. Новые идеи — только в `future/` и только со ссылкой на brief; без дублей с `past/INDEX.md`.

Параллельность: до `workers` гипотез одновременно (`config.yaml`). Holdout: `holdout_splits` в config.
