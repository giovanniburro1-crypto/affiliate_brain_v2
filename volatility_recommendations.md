# Рекомендации по улучшению расчета волатильности

## Проблема
Текущий метод расчета волатильности дает значения 100% слишком часто, что не соответствует реальности. 
Метод использует слишком строгие правила:
1. Любой день с отрицательным impact считается волатильным
2. Скачок ROI > 20% между днями считается волатильным
3. Результат = (волатильные_дни / общее_дни) * 100

## Предлагаемые варианты

### Вариант 1: Коэффициент вариации (CV) - классический статистический
```python
def volatility_cv(daily_roi: List[float]) -> float:
    if len(daily_roi) < 2:
        return 0.0
    
    valid_roi = [r for r in daily_roi if abs(r) > 0.01]
    if len(valid_roi) < 2:
        return 0.0
    
    mean = sum(valid_roi) / len(valid_roi)
    if abs(mean) < 0.01:
        return 0.0
    
    variance = sum((x - mean) ** 2 for x in valid_roi) / len(valid_roi)
    std_dev = math.sqrt(variance) if variance > 0 else 0
    cv = (std_dev / abs(mean)) * 100
    
    return min(100.0, round(cv, 2))
```

**Преимущества:**
- Стандартный статистический метод
- Хорошо измеряет относительную изменчивость
- Понятен аналитикам

**Недостатки:**
- Чувствителен к выбросам
- Может давать высокие значения для растущих/падающих трендов

### Вариант 2: Комбинированная метрика (рекомендуемый)
```python
def volatility_combined(daily_data: List[Dict[str, float]]) -> float:
    if len(daily_data) < 2:
        return 0.0
    
    daily_roi = [d.get('roi', 0) for d in daily_data]
    daily_impact = [d.get('impact', 0) for d in daily_data]
    
    # 1. Процент дней с отрицательным impact (30%)
    negative_days = sum(1 for impact in daily_impact if impact < 0)
    negative_score = (negative_days / len(daily_impact)) * 100
    
    # 2. Процент дней со скачками ROI > 15% (30%)
    spike_days = 0
    for i in range(1, len(daily_roi)):
        if abs(daily_roi[i] - daily_roi[i-1]) > 15:
            spike_days += 1
    spike_score = (spike_days / (len(daily_roi) - 1)) * 100 if len(daily_roi) > 1 else 0
    
    # 3. Коэффициент вариации ROI (40%)
    cv_score = volatility_cv(daily_roi)
    
    # Комбинируем с весами
    combined = (negative_score * 0.3) + (spike_score * 0.3) + (cv_score * 0.4)
    
    return round(combined, 2)
```

**Преимущества:**
- Учитывает несколько факторов с разными весами
- Более сбалансированный подход
- Учитывает как абсолютные убытки, так и относительные колебания

**Недостатки:**
- Сложнее для понимания
- Требует настройки весов

### Вариант 3: Умная адаптивная волатильность
```python
def volatility_smart(daily_data: List[Dict[str, float]]) -> float:
    if len(daily_data) < 3:
        return 0.0
    
    daily_roi = [d.get('roi', 0) for d in daily_data]
    daily_impact = [d.get('impact', 0) for d in daily_data]
    
    # Адаптивный порог для скачков (зависит от среднего ROI)
    avg_roi = sum(daily_roi) / len(daily_roi)
    adaptive_threshold = max(10, abs(avg_roi) * 0.5)
    
    # 1. Коэффициент вариации
    cv = volatility_cv(daily_roi)
    
    # 2. Процент дней со скачками > адаптивного порога
    spike_days = 0
    for i in range(1, len(daily_roi)):
        if abs(daily_roi[i] - daily_roi[i-1]) > adaptive_threshold:
            spike_days += 1
    spike_pct = (spike_days / (len(daily_roi) - 1)) * 100 if len(daily_roi) > 1 else 0
    
    # 3. Частота смены знака impact (трендовая нестабильность)
    sign_changes = 0
    for i in range(1, len(daily_impact)):
        if (daily_impact[i] >= 0) != (daily_impact[i-1] >= 0):
            sign_changes += 1
    trend_instability = (sign_changes / (len(daily_impact) - 1)) * 100 if len(daily_impact) > 1 else 0
    
    # Адаптивные веса в зависимости от прибыльности
    if avg_roi > 20:
        weights = [0.5, 0.3, 0.2]  # Больше вес на CV для высокоприбыльных
    elif avg_roi > 0:
        weights = [0.4, 0.4, 0.2]  # Сбалансированные веса
    else:
        weights = [0.3, 0.5, 0.2]  # Больше вес на скачки для убыточных
    
    combined = (cv * weights[0]) + (spike_pct * weights[1]) + (trend_instability * weights[2])
    
    # Корректировка по среднему ROI
    if avg_roi > 30:
        combined = combined * 0.8  # Снижаем для очень прибыльных
    elif avg_roi < -10:
        combined = min(100, combined * 1.2)  # Увеличиваем для очень убыточных
    
    return round(min(100.0, combined), 2)
```

**Преимущества:**
- Адаптируется к характеристикам кампании
- Учитывает тренды и прибыльность
- Наиболее интеллектуальный подход

**Недостатки:**
- Самый сложный для реализации и понимания
- Требует больше вычислений

## Сравнение методов на тестовых данных

| Сценарий | Текущий | CV | Комбинированный | Умный |
|----------|---------|-----|-----------------|--------|
| Стабильные данные | 0% | 2.5% | 1.0% | 1.3% |
| Один день в минусе | 40% | 69.8% | 48.9% | 57.9% |
| Большие скачки | 40% | 61.6% | 39.6% | 44.6% |
| Высокая волатильность | 80% | 100% | 74.5% | 100% |
| Улучшающийся тренд | 0% | 47.1% | 18.9% | 18.9% |
| Ухудшающийся тренд | 0% | 47.1% | 18.9% | 18.9% |

## Рекомендации

1. **Для быстрого исправления**: использовать **Вариант 2 (Комбинированный)** - он дает наиболее сбалансированные результаты и исправляет проблему с постоянными 100%.

2. **Для лучшего качества**: использовать **Вариант 3 (Умный)** - он лучше адаптируется к разным типам кампаний.

3. **Для простоты**: использовать **Вариант 1 (CV)** - классический подход, но он может переоценивать волатильность для трендовых кампаний.

## Как внедрить

1. Заменить функцию `_calc_instability_index` в `backend/services/top5_service_v2_complete.py` на выбранный вариант.
2. Обновить интерпретацию волатильности в `_instability_interpretation` если нужно.
3. Протестировать на реальных данных.

## Файлы для внедрения

- `improved_volatility.py` - содержит все варианты реализации
- `test_volatility.py` - тесты текущей реализации
- `backend/services/top5_service_v2_complete.py` - основной файл для изменения