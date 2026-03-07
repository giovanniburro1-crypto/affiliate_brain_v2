#!/usr/bin/env python3
"""
Тест новой функции расчета волатильности.
"""
import sys
sys.path.append('backend')

from backend.services.top5_service_v2_complete import _calc_instability_index

def test_volatility_calculation():
    """Тестируем расчет волатильности с разными сценариями."""
    
    print("🧪 Тестирование новой функции волатильности")
    print("="*60)
    
    # Тест 1: Стабильные данные (нет волатильности)
    stable_data = [
        {'roi': 20.0, 'impact': 100.0, 'conversions': 5},
        {'roi': 21.0, 'impact': 105.0, 'conversions': 5},
        {'roi': 19.5, 'impact': 98.0, 'conversions': 4},
        {'roi': 20.5, 'impact': 102.0, 'conversions': 5},
        {'roi': 20.0, 'impact': 100.0, 'conversions': 5},
    ]
    volatility1 = _calc_instability_index(stable_data)
    print(f"Тест 1 - Стабильные данные (нет скачков): {volatility1:.1f}%")
    print(f"  Ожидаем ~0-10%")
    
    # Тест 2: День в минусе (impact < 0)
    data_with_loss = [
        {'roi': 20.0, 'impact': 100.0, 'conversions': 5},
        {'roi': 15.0, 'impact': 80.0, 'conversions': 4},
        {'roi': -5.0, 'impact': -50.0, 'conversions': 2},  # день в минусе
        {'roi': 18.0, 'impact': 90.0, 'conversions': 4},
        {'roi': 22.0, 'impact': 110.0, 'conversions': 5},
    ]
    volatility2 = _calc_instability_index(data_with_loss)
    print(f"\nТест 2 - Один день в минусе: {volatility2:.1f}%")
    print(f"  Ожидаем > 20% (1 волатильный день из 5 = 20%)")
    
    # Тест 3: Скачок ROI > 20% между днями
    data_with_spike = [
        {'roi': 10.0, 'impact': 50.0, 'conversions': 3},
        {'roi': 12.0, 'impact': 60.0, 'conversions': 3},
        {'roi': 35.0, 'impact': 150.0, 'conversions': 5},  # скачок от 12% до 35% = +23%
        {'roi': 11.0, 'impact': 55.0, 'conversions': 3},
        {'roi': 10.5, 'impact': 52.0, 'conversions': 3},
    ]
    volatility3 = _calc_instability_index(data_with_spike)
    print(f"\nТест 3 - Скачок ROI > 20%: {volatility3:.1f}%")
    print(f"  Ожидаем > 20% (1 волатильный день из 5 = 20%)")
    
    # Тест 4: Много волатильности (и минус, и скачки)
    volatile_data = [
        {'roi': 5.0, 'impact': 25.0, 'conversions': 2},
        {'roi': -10.0, 'impact': -50.0, 'conversions': 1},  # минус
        {'roi': 30.0, 'impact': 120.0, 'conversions': 4},   # скачок от -10% до 30% = +40%
        {'roi': -5.0, 'impact': -25.0, 'conversions': 1},   # минус
        {'roi': 25.0, 'impact': 100.0, 'conversions': 4},   # скачок от -5% до 25% = +30%
    ]
    volatility4 = _calc_instability_index(volatile_data)
    print(f"\nТест 4 - Много волатильности: {volatility4:.1f}%")
    print(f"  Ожидаем > 60% (много волатильных дней)")
    
    # Тест 5: Мало данных (меньше 2 дней)
    little_data = [
        {'roi': 10.0, 'impact': 50.0, 'conversions': 3},
    ]
    volatility5 = _calc_instability_index(little_data)
    print(f"\nТест 5 - Мало данных (1 день): {volatility5:.1f}%")
    print(f"  Ожидаем 0% (по условию функции)")
    
    # Тест 6: Все дни волатильные
    all_volatile = [
        {'roi': -5.0, 'impact': -20.0, 'conversions': 1},   # минус
        {'roi': 25.0, 'impact': 80.0, 'conversions': 3},    # скачок от -5% до 25% = +30%
        {'roi': -8.0, 'impact': -30.0, 'conversions': 1},   # минус + скачок
        {'roi': 30.0, 'impact': 90.0, 'conversions': 3},    # скачок
        {'roi': -3.0, 'impact': -10.0, 'conversions': 1},   # минус
    ]
    volatility6 = _calc_instability_index(all_volatile)
    print(f"\nТест 6 - Все дни волатильные: {volatility6:.1f}%")
    print(f"  Ожидаем 100%")
    
    print("\n" + "="*60)
    print("✅ Тестирование завершено")
    
    # Проверяем интерпретацию
    from backend.services.top5_service_v2_complete import _instability_interpretation
    
    test_values = [0, 10, 15, 25, 40, 60, 80]
    print("\n📊 Интерпретация значений волатильности:")
    for val in test_values:
        interpretation = _instability_interpretation(val)
        print(f"  {val}% → {interpretation['label']} ({interpretation['level']})")

if __name__ == "__main__":
    test_volatility_calculation()