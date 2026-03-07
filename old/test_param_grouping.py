#!/usr/bin/env python3
"""
Тестирование группировки параметров по категориям
"""
import sys
import json
from collections import defaultdict

def group_parameters_by_category(strengths, weaknesses):
    """Группирует параметры по категориям и вычисляет агрегированные метрики"""
    
    # Категории параметров
    category_mapping = {
        'token2': 'traffic',
        'token3': 'traffic',
        'token4': 'traffic',
        'token5': 'traffic',
        'token6': 'technical',
        'token7': 'technical',
        'token8': 'technical',
        'token9': 'technical',
        'token10': 'technical',
        'os': 'device',
        'os_version': 'device',
        'device_type': 'device',
        'browser_name': 'device',
        'country': 'demographics',
        'language': 'demographics',
        'path': 'traffic',
        'rule': 'traffic',
        'offer_id': 'content',
        'lander_id': 'content'
    }
    
    # Группируем все параметры
    all_params = []
    
    # Добавляем strengths
    for s in strengths:
        param_type = s.get('type', '').lower()
        if param_type:
            all_params.append({
                'type': param_type,
                'value': s.get('value', ''),
                'profit': s.get('profit', 0),
                'spend': s.get('spend', 0),
                'revenue': s.get('revenue', 0),
                'conversions': s.get('conversions', 0),
                'clicks': s.get('clicks', 0),
                'roi': s.get('roi', 0),
                'traffic_pct': s.get('traffic_pct', 0),
                'profit_pct': s.get('profit_pct', 0),
                'is_positive': True
            })
    
    # Добавляем weaknesses
    for w in weaknesses:
        param_type = w.get('type', '').lower()
        if param_type:
            all_params.append({
                'type': param_type,
                'value': w.get('value', ''),
                'profit': w.get('profit', 0),
                'spend': w.get('spend', 0),
                'revenue': w.get('revenue', 0),
                'conversions': w.get('conversions', 0),
                'clicks': w.get('clicks', 0),
                'roi': w.get('roi', 0),
                'traffic_pct': w.get('traffic_pct', 0),
                'profit_pct': w.get('profit_pct', 0),
                'is_positive': False
            })
    
    # Группируем по типу параметра
    grouped = defaultdict(list)
    for param in all_params:
        grouped[param['type']].append(param)
    
    # Вычисляем агрегированные метрики для каждой группы
    category_summary = {}
    
    for param_type, items in grouped.items():
        if not items:
            continue
            
        # Агрегированные метрики
        total_profit = sum(item['profit'] for item in items)
        total_spend = sum(item['spend'] for item in items)
        total_conversions = sum(item['conversions'] for item in items)
        total_clicks = sum(item['clicks'] for item in items)
        total_traffic_pct = sum(item['traffic_pct'] for item in items)
        total_profit_pct = sum(item['profit_pct'] for item in items)
        
        # ROI (целое число)
        avg_roi = int(total_profit / total_spend * 100) if total_spend > 0 else 0
        
        # Влияние (impact) - комбинированная метрика
        # Берем среднее profit_pct, но можно использовать более сложную формулу
        impact_score = total_profit_pct if total_profit_pct != 0 else total_traffic_pct
        
        # Количество положительных/отрицательных элементов
        positive_count = sum(1 for item in items if item['is_positive'])
        negative_count = len(items) - positive_count
        
        # Категория
        category = category_mapping.get(param_type, 'other')
        
        # Детализация по значениям (топ-3 по абсолютному profit)
        top_values = sorted(items, key=lambda x: abs(x['profit']), reverse=True)[:3]
        value_details = [
            {
                'value': item['value'],
                'profit': item['profit'],
                'profit_pct': item['profit_pct'],
                'traffic_pct': item['traffic_pct'],
                'conversions': item['conversions'],
                'roi': item['roi']
            }
            for item in top_values
        ]
        
        category_summary[param_type] = {
            'category': category,
            'total_profit': total_profit,
            'total_spend': total_spend,
            'total_conversions': total_conversions,
            'total_clicks': total_clicks,
            'avg_roi': avg_roi,
            'traffic_pct': total_traffic_pct,
            'profit_pct': total_profit_pct,
            'impact_score': round(impact_score, 1),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'total_values': len(items),
            'top_values': value_details,
            'recommendation': _get_recommendation(total_profit, positive_count, negative_count, avg_roi)
        }
    
    return category_summary

def _get_recommendation(total_profit, positive_count, negative_count, avg_roi):
    """Генерирует рекомендацию на основе метрик категории"""
    if total_profit > 0 and avg_roi > 30 and positive_count > negative_count:
        return "SCALE"
    elif total_profit > 0 and avg_roi > 10:
        return "OPTIMIZE"
    elif total_profit < 0 and negative_count > 0:
        return "FIX"
    elif total_profit == 0:
        return "TEST"
    else:
        return "HOLD"

# Тестируем на реальных данных
if __name__ == "__main__":
    import requests
    
    # Получаем данные с API
    response = requests.get("http://localhost:8001/api/company-analytics/analysis?campaign_id=1205&period=7")
    data = response.json()
    
    strengths = data.get('analysis', {}).get('strengths', [])
    weaknesses = data.get('analysis', {}).get('weaknesses', [])
    
    print(f"Strengths: {len(strengths)}")
    print(f"Weaknesses: {len(weaknesses)}")
    
    # Группируем
    summary = group_parameters_by_category(strengths, weaknesses)
    
    print("\n=== Группировка параметров ===")
    for param_type, metrics in summary.items():
        print(f"\n{param_type.upper()}:")
        print(f"  Категория: {metrics['category']}")
        print(f"  Profit: ${metrics['total_profit']:.2f}")
        print(f"  ROI: {metrics['avg_roi']}%")
        print(f"  Конверсии: {metrics['total_conversions']}")
        print(f"  Трафик: {metrics['traffic_pct']:.1f}%")
        print(f"  Профит: {metrics['profit_pct']:.1f}%")
        print(f"  Влияние: {metrics['impact_score']}%")
        print(f"  Рекомендация: {metrics['recommendation']}")
        print(f"  Топ значения:")
        for val in metrics['top_values']:
            print(f"    - {val['value']}: ${val['profit']} ({val['profit_pct']}% профита)")