# auto_gen — шаблон цикла гипотез

Переиспользуемый **knowledge-протокол** для агента (Cursor и аналоги): исследовать → ставить гипотезы → тестировать → фиксировать выводы. Подходит для любого ML-проекта; раннеры, данные и метрики живут в **целевом** продукте, не здесь.

## Что это

Каркас инструкций и пустая база знаний:

| Файл / папка | Роль |
|--------------|------|
| [`AGENTS.md`](AGENTS.md) | Протокол одного цикла для агента |
| [`config.yaml`](config.yaml) | SoT порогов, baselines, workers, preflight |
| [`knowledge/`](knowledge/) | CONTEXT, METRICS, investigate → future → past |

Порядок работы: **investigate → future → experiment → past**.

## Как подключить к своему проекту

1. Скопируйте этот шаблон рядом с (или внутрь) репозитория ML-продукта.
2. Заполните [`config.yaml`](config.yaml): `project_name`, splits, `metrics`, `acceptance`, `baselines`, `preflight`.
3. Опишите KPI в [`knowledge/METRICS.md`](knowledge/METRICS.md) и продукт в [`knowledge/CONTEXT.md`](knowledge/CONTEXT.md).
4. Решите, **как** гонять эксперименты (скрипт, ноутбук, CI, CLI продукта) — протокол требует только воспроизводимый артефакт (meta + метрики), не конкретные shell-скрипты.
5. Запустите агента с [`AGENTS.md`](AGENTS.md): сначала brief в `investigate/`, потом очередь в `future/`.

## Чего здесь нет

- Кода раннеров, harness, скриптов прогона.
- Истории чужих гипотез и доменных метрик.

Экспериментальный код и артефакты прогонов держите в целевом репозитории; в `knowledge/past/` остаются только отчёты и INDEX.
