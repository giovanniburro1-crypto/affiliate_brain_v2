# Logic_Blocks — база знаний Affiliate Brain

Эта папка содержит правила, паттерны и конфигурацию для анализа кампаний.

## Структура

- **01_Rules/** — жёсткие правила (killer_rules, scaler_rules, zacep_rules)
- **02_Patterns/** — winning_combos, killer_patterns, trend_analysis
- **03_Decision_Memory/** — snapshots, user_choices, outcomes
- **05_Learning/** — model_weights (обновляется при обучении)
- **segment_config.json** — какие колонки анализировать по traffic source

## Использование

Модули (TOP-5 Bot, Company Analytics) читают данные через `backend.brain.KnowledgeBase`.
Не привязывайтесь к конкретным файлам — Brain предоставляет единый API.

## Обновление

При добавлении/изменении файлов Brain подхватывает изменения при следующем запросе
(с учётом кэша; для сброса: `brain.invalidate_cache()`).
