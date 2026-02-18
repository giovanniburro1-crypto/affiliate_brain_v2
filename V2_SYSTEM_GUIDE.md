# KnowledgeBase V2 System Guide

## Архитектура системы

Система KnowledgeBase V2 — это централизованный "мозг" для анализа affiliate-кампаний, который динамически загружает блоки знаний из папки `my_knowledge` и использует систему голосования для принятия решений.

### Основные компоненты:

1. **KnowledgeBaseV2** (`backend/brain/knowledge_base_v2_complete.py`)
   - Основной класс системы
   - Динамически загружает блоки знаний
   - Управляет системой голосования
   - Поддерживает обучение на основе решений пользователя

2. **Top5ServiceV2** (`backend/services/top5_service_v2_complete.py`)
   - Обновленный сервис для анализа TOP-5 кампаний
   - Использует KnowledgeBaseV2 вместо отдельных конфигов
   - Возвращает голоса блоков в результатах

3. **Динамические блоки** (`logic_blocks/my_knowledge/`)
   - Python-классы с логикой анализа
   - Автоматически загружаются при старте системы

## Добавление нового блока знаний

### Шаг 1: Создание файла блока

Создайте файл в папке `logic_blocks/my_knowledge/` с именем `block_X_name.py`, где:
- `X` — порядковый номер блока (7, 8, 9...)
- `name` — краткое описание функционала

Пример: `block_7_geo_analysis.py`

### Шаг 2: Структура класса блока

```python
class AffiliateGeoAnalysis:
    """Блок для географического анализа кампаний."""
    
    def __init__(self):
        self.name = "block_7_geo_analysis"
        self.description = "Анализ географии трафика и оптимизация по регионам"
        self.weight = 1.0  # Начальный вес (0.1-3.0)
        self.category = "optimization"
    
    def analyze(self, campaign_data: dict) -> dict:
        """
        Анализировать кампанию.
        
        Args:
            campaign_data: Словарь с данными кампании
            
        Returns:
            Словарь с результатом анализа:
            {
                "verdict": "SCALE|HOLD|STOP|OPTIMIZE",
                "confidence": 0.0-1.0,
                "reason": "Объяснение решения",
                "action": "Рекомендуемое действие",
                "details": {...}  # Дополнительные детали
            }
        """
        # Логика анализа
        roi = campaign_data.get('roi', 0)
        geo_performance = campaign_data.get('geo_stats', {})
        
        if roi > 50 and geo_performance.get('best_region'):
            return {
                "verdict": "SCALE",
                "confidence": 0.8,
                "reason": "Высокий ROI и наличие лучшего региона",
                "action": "Увеличить бюджет для лучшего региона",
                "details": {"best_region": geo_performance['best_region']}
            }
        else:
            return {
                "verdict": "HOLD",
                "confidence": 0.5,
                "reason": "Недостаточно данных для географической оптимизации",
                "action": "Собрать больше данных по регионам"
            }
    
    # Опционально: специализированные методы
    def analyze_region_performance(self, region_data: dict) -> dict:
        """Анализировать производительность региона."""
        # Реализация метода
        pass
```

### Шаг 3: Альтернативные структуры методов

Система поддерживает несколько вариантов сигнатур методов:

1. **Основной метод `analyze()`** — рекомендуется
2. **Специализированные методы** (начинаются с `analyze_`, `get_`, `calculate_`)
3. **Унаследованные методы** для совместимости с существующими блоками

### Шаг 4: Регистрация блока

Система автоматически обнаружит новый блок при следующем запуске. Для принудительной перезагрузки:

```python
from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2

brain = KnowledgeBaseV2()
brain.reload_blocks()
```

## Система голосования

### Как работает голосование:

1. Каждый блок анализирует кампанию независимо
2. Блок возвращает голос с:
   - Вердиктом (SCALE, HOLD, STOP, OPTIMIZE)
   - Уверенностью (0.0-1.0)
   - Объяснением
   - Весом блока (учитывается в финальном решении)

3. Все голоса агрегируются по формуле:
   ```
   Общий счет вердикта = Σ(confidence_i × weight_i) для всех блоков с этим вердиктом
   ```

4. Вердикт с максимальным общим счетом становится финальным решением

### Настройка весов блоков:

```python
# Через API (будущая реализация)
POST /api/knowledge/blocks/{block_id}/weight
{"weight": 2.5}

# Или программно
brain.set_block_weight("block_7_geo_analysis", 2.0)
```

## Обучение системы

### Автоматическое обучение:

Система автоматически обучается на основе решений пользователя:

1. Когда пользователь принимает решение (Apply в интерфейсе)
2. Система записывает:
   - Голоса всех блоков
   - Решение пользователя
   - Контекст кампании

3. Через 7/14 дней система проверяет результат:
   - Сравнивает ROI до и после решения
   - Оценивает правильность рекомендаций блоков
   - Корректирует веса блоков

### Ручное управление обучением:

```python
from backend.services.learning_service import LearningService

# Запись решения пользователя
learning_service.record_user_decision(
    campaign_id="campaign_123",
    user_verdict="SCALE",
    confidence=95.0,
    recheck_after_days=7
)

# Обновление результатов
learning_service.update_outcomes()

# Получение статистики
stats = learning_service.get_learning_stats()
```

## API Endpoints

### Основные endpoints:

1. **GET /api/bot-agent/top5**
   - Возвращает TOP-5 кампаний с голосами блоков
   - Параметры: `period`, `date_from`, `date_to`

2. **POST /api/bot-agent/apply**
   - Применяет решение пользователя
   - Запускает процесс обучения

3. **GET /api/knowledge/blocks** (планируется)
   - Список всех блоков с метаданными

4. **GET /api/knowledge/blocks/{block_id}/stats**
   - Статистика по блоку

## Миграция JSON конфигов в Python блоки

Существующие JSON конфиги автоматически конвертируются в Python блоки:

- `01_Rules/core_rules.json` → `migrated_blocks/core_rules.py`
- `02_Patterns/killer_patterns.json` → `migrated_blocks/killer_patterns.py`
- `02_Patterns/winning_combos.json` → `migrated_blocks/winning_combos.py`
- `02_Patterns/trend_analysis.json` → `migrated_blocks/trend_analysis.py`
- `05_Learning/model_weights.json` → `migrated_blocks/model_weights.py`

### Структура мигрированного блока:

```python
class CoreRulesBlock(KnowledgeBlock):
    def __init__(self):
        super().__init__(
            name="core_rules",
            description="Основные правила анализа кампаний",
            weight=0.9,
            category="rules"
        )
        
    def analyze(self, campaign_data):
        # Логика из core_rules.json
        pass
```

## Мониторинг и отладка

### Логирование:

```python
# Включение детального логгирования
import logging
logging.basicConfig(level=logging.DEBUG)

# Получение статистики системы
stats = brain.get_block_statistics()
print(f"Всего блоков: {len(stats)}")
for block_id, block_stats in stats.items():
    print(f"{block_id}: accuracy={block_stats['accuracy']:.2f}, weight={block_stats['weight']}")
```

### Проверка работы системы:

```bash
# Тестовый скрипт
python3 test_v2_demo.py

# Финальная проверка
python3 final_check_v2.py

# Интеграционное тестирование
python3 test_integration_v2.py
```

## Советы по разработке блоков

### Лучшие практики:

1. **Сохраняйте совместимость** с существующими блоками
2. **Используйте типные аннотации** для лучшей читаемости
3. **Добавляйте docstrings** с описанием логики
4. **Тестируйте блоки изолированно** перед интеграцией
5. **Учитывайте вес блока** при проектировании логики

### Пример теста для блока:

```python
def test_geo_analysis_block():
    from logic_blocks.my_knowledge.block_7_geo_analysis import AffiliateGeoAnalysis
    
    block = AffiliateGeoAnalysis()
    
    # Тестовые данные
    campaign_data = {
        "campaign_id": "test_campaign",
        "roi": 60.0,
        "geo_stats": {
            "best_region": "US",
            "regions": {"US": {"roi": 75, "spend": 1000}}
        }
    }
    
    result = block.analyze(campaign_data)
    assert result["verdict"] == "SCALE"
    assert 0.5 <= result["confidence"] <= 1.0
    assert "reason" in result
```

## Устранение неполадок

### Проблема: Блок не загружается

**Решение:**
1. Проверьте имя файла и класса
2. Убедитесь, что файл в папке `my_knowledge/`
3. Проверьте импорты и зависимости
4. Перезагрузите систему: `brain.reload_blocks()`

### Проблема: Голоса блоков не отображаются

**Решение:**
1. Проверьте метод `analyze()` блока
2. Убедитесь, что возвращаемый словарь содержит ключ `"verdict"`
3. Проверьте логи загрузки блоков
4. Убедитесь, что блок включен: `brain.enable_block(block_id, True)`

### Проблема: Неправильные веса блоков

**Решение:**
1. Проверьте историю обучения: `brain.get_block_statistics()`
2. Скорректируйте вес вручную: `brain.set_block_weight(block_id, new_weight)`
3. Сбросьте историю обучения при необходимости

## Дальнейшее развитие

### Планируемые улучшения:

1. **Веб-интерфейс** для управления блоками
2. **A/B тестирование** алгоритмов блоков
3. **Автоматическая оптимизация** весов блоков
4. **Экспорт/импорт** блоков знаний
5. **Визуализация** процесса голосования

### Контакты и поддержка:

- Документация системы: `V2_SYSTEM_GUIDE.md`
- Примеры блоков: `logic_blocks/my_knowledge/`
- Тестовые скрипты: `test_v2_*.py`
- Резервные копии: `backend_backup_*/`, `logic_blocks_backup_*/`

---

**Система V2 решает ключевую проблему:** Теперь у вас есть **один мозг (KnowledgeBaseV2)**, из которого блоки берут информацию в нужном формате, а не отдельные боты для каждого блока. Это предотвращает путаницу и сбои при ежедневном обновлении 100+ файлов в `my_knowledge`.