#!/usr/bin/env python3
"""
Улучшенные варианты расчета волатильности.
Вариант 1: Коэффициент вариации ROI (CV) - стандартное отклонение / среднее
Вариант 2: Среднедневное абсолютное изменение ROI
Вариант 3: Комбинированная метрика с учетом дней в минусе и скачков (улучшенная текущая)
"""
import math
from typing import List, Dict


def volatility_cv(daily_roi: List[float]) -> float:
    """
    Вариант 1: Коэффициент вариации ROI (Coefficient of Variation)
    Стандартный подход для измерения относительной волатильности.
    CV = (стандартное отклонение / |среднее|) * 100
    """
    if len(daily_roi) < 2:
        return 0.0
    
    # Фильтруем нулевые и очень маленькие значения
    valid_roi = [r for r in daily_roi if abs(r) > 0.01]
    if len(valid_roi) < 2:
        return 0.0
    
    mean = sum(valid_roi) / len(valid_roi)
    if abs(mean) < 0.01:
        return 0.0
    
    variance = sum((x - mean) ** 2 for x in valid_roi) / len(valid_roi)
    std_dev = math.sqrt(variance) if variance > 0 else 0
    cv = (std_dev / abs(mean)) * 100
    
    # Ограничиваем 100%
    return min(100.0, round(cv, 2))


def volatility_avg_daily_change(daily_roi: List[float]) -> float:
    """
    Вариант 2: Среднедневное абсолютное изменение ROI
    Измеряет, насколько сильно ROI меняется день ото дня.
    """
    if len(daily_roi) < 2:
        return 0.0
    
    changes = []
    for i in range(1, len(daily_roi)):
        change = abs(daily_roi[i] - daily_roi[i-1])
        changes.append(change)
    
    avg_change = sum(changes) / len(changes) if changes else 0
    
    # Нормализуем: среднее изменение > 20% считается высокой волатильностью
    # Преобразуем в шкалу 0-100
    volatility_score = min(100.0, avg_change * 2)  # 50% изменение = 100 баллов
    
    return round(volatility_score, 2)


def volatility_combined(daily_data: List[Dict[str, float]]) -> float:
    """
    Вариант 3: Комбинированная метрика (улучшенная текущая)
    Учитывает несколько факторов с разными весами:
    1. Дни с отрицательным impact (30%)
    2. Скачки ROI > 15% между днями (30%)
    3. Коэффициент вариации ROI (40%)
    """
    if len(daily_data) < 2:
        return 0.0
    
    # Извлекаем ROI и impact
    daily_roi = [d.get('roi', 0) for d in daily_data]
    daily_impact = [d.get('impact', 0) for d in daily_data]
    
    # 1. Процент дней с отрицательным impact
    negative_days = sum(1 for impact in daily_impact if impact < 0)
    negative_score = (negative_days / len(daily_impact)) * 100
    
    # 2. Процент дней со скачками ROI > 15%
    spike_days = 0
    for i in range(1, len(daily_roi)):
        if abs(daily_roi[i] - daily_roi[i-1]) > 15:
            spike_days += 1
    spike_score = (spike_days / (len(daily_roi) - 1)) * 100 if len(daily_roi) > 1 else 0
    
    # 3. Коэффициент вариации ROI
    cv_score = volatility_cv(daily_roi)
    
    # Комбинируем с весами
    combined = (negative_score * 0.3) + (spike_score * 0.3) + (cv_score * 0.4)
    
    return round(combined, 2)


def volatility_smart(daily_data: List[Dict[str, float]]) -> float:
    """
    Вариант 4: Умная волатильность с адаптивными порогами
    - Учитывает тренд (улучшение/ухудшение)
    - Разные веса для прибыльных и убыточных кампаний
    - Нормализация по среднему ROI
    """
    if len(daily_data) < 3:
        return 0.0
    
    daily_roi = [d.get('roi', 0) for d in daily_data]
    daily_impact = [d.get('impact', 0) for d in daily_data]
    
    # Средний ROI
    avg_roi = sum(daily_roi) / len(daily_roi)
    
    # Адаптивный порог для скачков (зависит от среднего ROI)
    # Для высоких ROI допустимы большие колебания
    adaptive_threshold = max(10, abs(avg_roi) * 0.5)  # минимум 10%, максимум 50% от среднего
    
    # 1. Коэффициент вариации (нормализованный)
    cv = volatility_cv(daily_roi)
    
    # 2. Процент дней со скачками > адаптивного порога
    spike_days = 0
    for i in range(1, len(daily_roi)):
        if abs(daily_roi[i] - daily_roi[i-1]) > adaptive_threshold:
            spike_days += 1
    spike_pct = (spike_days / (len(daily_roi) - 1)) * 100 if len(daily_roi) > 1 else 0
    
    # 3. Последовательность знаков impact (тренд)
    # Считаем последовательности положительных/отрицательных дней
    sign_changes = 0
    for i in range(1, len(daily_impact)):
        if (daily_impact[i] >= 0) != (daily_impact[i-1] >= 0):
            sign_changes += 1
    trend_instability = (sign_changes / (len(daily_impact) - 1)) * 100 if len(daily_impact) > 1 else 0
    
    # Веса зависят от прибыльности
    if avg_roi > 20:
        # Высокоприбыльные: больше вес на CV, меньше на скачки
        weights = [0.5, 0.3, 0.2]  # CV, скачки, тренд
    elif avg_roi > 0:
        # Прибыльные: сбалансированные веса
        weights = [0.4, 0.4, 0.2]
    else:
        # Убыточные: больше вес на скачки и тренд
        weights = [0.3, 0.5, 0.2]
    
    combined = (cv * weights[0]) + (spike_pct * weights[1]) + (trend_instability * weights[2])
    
    # Корректируем по среднему ROI (высокий ROI может иметь большую волатильность)
    if avg_roi > 30:
        combined = combined * 0.8  # снижаем оценку для очень прибыльных
    elif avg_roi < -10:
        combined = min(100, combined * 1.2)  # увеличиваем для очень убыточных
    
    return round(min(100.0, combined), 2)


def test_all_methods():
    """Тестируем все методы на разных сценариях."""
    print("🧪 Тестирование всех методов расчета волатильности")
    print("=" * 80)
    
    # Тестовые данные
    test_cases = [
        {
            "name": "Стабильные данные",
            "data": [
                {'roi': 20.0, 'impact': 100.0},
                {'roi': 21.0, 'impact': 105.0},
                {'roi': 19.5, 'impact': 98.0},
                {'roi': 20.5, 'impact': 102.0},
                {'roi': 20.0, 'impact': 100.0},
            ]
        },
        {
            "name": "Один день в минусе",
            "data": [
                {'roi': 20.0, 'impact': 100.0},
                {'roi': 15.0, 'impact': 80.0},
                {'roi': -5.0, 'impact': -50.0},
                {'roi': 18.0, 'impact': 90.0},
                {'roi': 22.0, 'impact': 110.0},
            ]
        },
        {
            "name": "Большие скачки",
            "data": [
                {'roi': 10.0, 'impact': 50.0},
                {'roi': 12.0, 'impact': 60.0},
                {'roi': 35.0, 'impact': 150.0},
                {'roi': 11.0, 'impact': 55.0},
                {'roi': 10.5, 'impact': 52.0},
            ]
        },
        {
            "name": "Высокая волатильность",
            "data": [
                {'roi': 5.0, 'impact': 25.0},
                {'roi': -10.0, 'impact': -50.0},
                {'roi': 30.0, 'impact': 120.0},
                {'roi': -5.0, 'impact': -25.0},
                {'roi': 25.0, 'impact': 100.0},
            ]
        },
        {
            "name": "Улучшающийся тренд",
            "data": [
                {'roi': 5.0, 'impact': 25.0},
                {'roi': 10.0, 'impact': 50.0},
                {'roi': 15.0, 'impact': 75.0},
                {'roi': 20.0, 'impact': 100.0},
                {'roi': 25.0, 'impact': 125.0},
            ]
        },
        {
            "name": "Ухудшающийся тренд",
            "data": [
                {'roi': 25.0, 'impact': 125.0},
                {'roi': 20.0, 'impact': 100.0},
                {'roi': 15.0, 'impact': 75.0},
                {'roi': 10.0, 'impact': 50.0},
                {'roi': 5.0, 'impact': 25.0},
            ]
        },
    ]
    
    for test in test_cases:
        print(f"\n📊 {test['name']}:")
        print(f"   Данные: {[(d['roi'], d['impact']) for d in test['data']]}")
        
        # Текущий метод
        from backend.services.top5_service_v2_complete import _calc_instability_index
        current = _calc_instability_index(test['data'])
        
        # Новые методы
        daily_roi = [d['roi'] for d in test['data']]
        cv = volatility_cv(daily_roi)
        avg_change = volatility_avg_daily_change(daily_roi)
        combined = volatility_combined(test['data'])
        smart = volatility_smart(test['data'])
        
        print(f"   Текущий: {current:.1f}%")
        print(f"   CV (Вариант 1): {cv:.1f}%")
        print(f"   Avg Change (Вариант 2): {avg_change:.1f}%")
        print(f"   Combined (Вариант 3): {combined:.1f}%")
        print(f"   Smart (Вариант 4): {smart:.1f}%")
    
    print("\n" + "=" * 80)
    print("📋 Рекомендации:")
    print("1. CV (Вариант 1) - классический статистический подход")
    print("2. Combined (Вариант 3) - баланс между простотой и точностью")
    print("3. Smart (Вариант 4) - наиболее интеллектуальный, но сложный")
    print("\n⚠️  Текущий метод может давать 100% слишком часто из-за строгих правил.")


if __name__ == "__main__":
    test_all_methods()