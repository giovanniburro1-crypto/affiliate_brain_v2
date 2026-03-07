#!/usr/bin/env python3
"""
Тестирование нового API с parameter_category_summary
"""
import time
import requests

def test_api():
    url = "http://localhost:8001/api/company-analytics/analysis?campaign_id=1205&period=7"
    
    # Даем время серверу перезагрузиться
    time.sleep(3)
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if 'deep_analysis' in data:
                deep = data['deep_analysis']
                
                if 'parameter_category_summary' in deep:
                    print("✅ parameter_category_summary доступен")
                    categories = deep['parameter_category_summary']
                    print(f"Количество категорий: {len(categories)}")
                    
                    for param_type, summary in categories.items():
                        print(f"\n📊 {param_type.upper()}:")
                        print(f"   {summary.get('compact_label', '')}")
                        print(f"   {summary.get('compact_metrics', '')}")
                        print(f"   Категория: {summary.get('category', '')}")
                        print(f"   Profit: ${summary.get('total_profit', 0)}")
                        print(f"   ROI: {summary.get('avg_roi', 0)}%")
                        print(f"   Конверсии: {summary.get('total_conversions', 0)}")
                        print(f"   Трафик: {summary.get('traffic_pct', 0)}%")
                        print(f"   Профит: {summary.get('profit_pct', 0)}%")
                        print(f"   Влияние: {summary.get('impact_score', 0)}%")
                        print(f"   Рекомендация: {summary.get('recommendation', '')}")
                        
                        # Детализация топ значений
                        top_values = summary.get('top_values', [])
                        if top_values:
                            print("   Топ значения:")
                            for val in top_values:
                                print(f"     - {val['value']}: ${val['profit']} ({val['profit_pct']}% профита)")
                else:
                    print("❌ parameter_category_summary не найден")
                    print(f"Доступные ключи в deep_analysis: {list(deep.keys())}")
            else:
                print("❌ deep_analysis не найден")
                print(f"Доступные ключи: {list(data.keys())}")
        else:
            print(f"❌ Ошибка HTTP: {response.status_code}")
            print(f"Response text: {response.text[:200]}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
    except ValueError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"Response text: {response.text[:500]}")

if __name__ == "__main__":
    test_api()