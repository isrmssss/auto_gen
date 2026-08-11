# past — история экспериментов

Сюда пишутся отчёты после прогонов. На старте шаблона история пуста.

## Как читать

1. [`INDEX.md`](INDEX.md) — scorecard (читай первым).
2. Отчёты `hxx_slug.md` / `NNN_slug.md` — один файл на гипотезу.
3. По мере роста: заводить `line_*.md` (выжимки линий) и cemetery опровергнутых механик; ссылки держать в INDEX.

## Обязательные поля отчёта

```markdown
# Hxx — название
Статус: ✅/⚠️/❌ | Primary: <split> | Holdout: … | N: …
Идея: 1–2 предложения (механизм, без id)
Метрики: primary (+ holdout) vs champion — имена из METRICS.md
Вердикт: принять / отклонить / доработать
Почему:
- persist=…, fixed=…, regress=… vs champion
- топ срезы: …
Repro: run_id, arm, путь к meta/логу
Next: что в brief / future
```

Отчёт без persist/fixed/regress (или эквивалента из METRICS) — **невалиден**.

## Статусы

- ✅ — acceptance + holdout (если требуется config).
- ⚠️ — прогресс на primary без подтверждённого holdout / частичный критерий.
- ❌ — hard-constraint / чистый regress / провал идеи.
