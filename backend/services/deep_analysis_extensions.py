"""
Deep Analysis Extensions - расширенные функции анализа для страницы Company Analysis.
Дополняет campaign_analysis_service.py без breaking changes.
Принцип: "Один мозг, много модификаций выдачи ответа в разные блоки"
"""
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import math


def analyze_parameter_interconnections(
    breakdown: Dict[str, Any],
    campaign_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Анализирует взаимосвязи между 26 параметрами breakdown.
    Выявляет сильные корреляции между параметрами.
    
    Returns:
        Dict с анализом взаимосвязей, весами влияния и паттернами.
    """
    # Группируем параметры по категориям
    categories = {
        "demographics": ["country", "language"],
        "device": ["device_type", "os", "os_version", "browser_name"],
        "traffic": ["path", "rule", "token2", "token3", "token4", "token5"],
        "content": ["offer_id", "lander_id"],
        "technical": ["token6", "token7", "token8", "token9", "token10"]
    }
    
    # Собираем все параметры для анализа
    from backend.brain import KnowledgeBase
    brain = KnowledgeBase()
    source = campaign_summary.get("traffic_source", "default")
    active_columns = set(brain.get_segment_columns(source))

    all_params = {}
    param_sources = [
        ("by_path", "path"),
        ("by_rule", "rule"),
        ("by_offer_id", "offer_id"),
        ("by_lander_id_jump", "lander_id"),
        ("by_device_type", "device_type"),
        ("by_country", "name"),
        ("by_os", "os"),
        ("by_os_version", "os_version"),
        ("by_browser_name", "browser_name"),
        ("by_language", "language"),
        ("by_token2", "name"),
    ]
    
    for i in range(3, 11):
        param_sources.append((f"by_token{i}", f"token{i}"))
    
    # Оставляем только активные параметры
    active_param_sources = []
    for p in param_sources:
        param_name = p[0].replace("by_", "").replace("_jump", "")
        col_name = "offer" if param_name == "offer_id" else param_name
        if col_name in active_columns:
            active_param_sources.append(p)
            
    for source_key, name_key in active_param_sources:
        items = breakdown.get(source_key, [])
        if not items:
            continue
            
        param_name = source_key.replace("by_", "").replace("_jump", "")
        param_values = []
        
        for item in items:
            value = item.get(name_key) or item.get("name") or "(empty)"
            profit = item.get("profit", 0) or 0
            spend = item.get("spend", 0) or 0
            conversions = item.get("conversions", 0) or 0
            
            param_values.append({
                "value": str(value),
                "profit": profit,
                "spend": spend,
                "conversions": conversions,
                "roi": (profit / spend * 100) if spend > 0 else 0,
                "cpa": (spend / conversions) if conversions > 0 else 0,
                "epc": (profit / item.get("clicks", 1)) if item.get("clicks", 0) > 0 else 0
            })
        
        if param_values:
            all_params[param_name] = param_values
    
    # Анализируем влияние каждого параметра
    total_spend = campaign_summary.get("spend", 0) or 0
    total_profit = campaign_summary.get("profit", 0) or 0
    
    parameter_impact = {}
    for param_name, values in all_params.items():
        if not values:
            continue
            
        # Рассчитываем дисперсию профита для этого параметра
        profits = [v["profit"] for v in values]
        avg_profit = sum(profits) / len(profits) if profits else 0
        
        # Взвешенное влияние на общий профит
        param_total_profit = sum(profits)
        param_total_spend = sum(v["spend"] for v in values)
        
        impact_score = 0
        if total_profit != 0:
            # Процент вклада в общий профит (положительный или отрицательный)
            impact_score = (param_total_profit / abs(total_profit)) * 100
        elif total_spend > 0:
            # Если общий профит близок к нулю, оцениваем по расходу
            impact_score = (param_total_spend / total_spend) * 100
        
        # Определяем категорию параметра
        category = "other"
        for cat_name, cat_params in categories.items():
            if param_name in cat_params:
                category = cat_name
                break
        
        parameter_impact[param_name] = {
            "category": category,
            "impact_score": round(impact_score, 1),
            "total_profit": round(param_total_profit, 2),
            "total_spend": round(param_total_spend, 2),
            "values_count": len(values),
            "best_value": max(values, key=lambda x: x["profit"])["value"] if values else None,
            "worst_value": min(values, key=lambda x: x["profit"])["value"] if values else None,
            "profit_range": round(max(profits) - min(profits), 2) if profits else 0
        }
    
    # Выявляем паттерны-убийцы (killer patterns)
    killer_patterns = _find_killer_patterns(all_params, campaign_summary, breakdown)
    
    # Выявляем winning combos
    winning_combos = _find_winning_combos(all_params, campaign_summary, breakdown)
    
    # Анализ взаимосвязей между параметрами
    correlations = _analyze_correlations(all_params)
    
    return {
        "parameter_categories": categories,
        "parameter_impact": parameter_impact,
        "killer_patterns": killer_patterns,
        "winning_combos": winning_combos,
        "correlations": correlations,
        "total_parameters_analyzed": len(all_params),
        "most_influential_params": sorted(
            parameter_impact.items(),
            key=lambda x: abs(x[1]["impact_score"]),
            reverse=True
        )[:5]
    }


def get_parameter_category_summary(
    strengths: List[Dict[str, Any]],
    weaknesses: List[Dict[str, Any]],
    breakdown: Dict[str, Any],
    campaign_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Группирует параметры по категориям и вычисляет агрегированные метрики.
    Возвращает компактную сводку для отображения в блоке Key Drivers.
    
    Формат: {param_type: {category, total_profit, avg_roi, total_conversions, traffic_pct, profit_pct, impact_score, ...}}
    """
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
        'offer': 'content',
        'offer_id': 'content',
        'lander_id': 'content'
    }
    
    # Получаем активные колонки
    from backend.brain import KnowledgeBase
    brain = KnowledgeBase()
    source = campaign_summary.get("traffic_source", "default")
    active_columns = set(brain.get_segment_columns(source))
    
    # Собираем данные из breakdown для дополнения strengths/weaknesses
    breakdown_data = {}
    
    all_param_sources = [
        ("by_path", "path"),
        ("by_rule", "rule"),
        ("by_offer_id", "offer_id"),
        ("by_lander_id_jump", "lander_id"),
        ("by_device_type", "device_type"),
        ("by_country", "name"),
        ("by_os", "os"),
        ("by_os_version", "os_version"),
        ("by_browser_name", "browser_name"),
        ("by_language", "language"),
        ("by_token2", "name"),
    ] + [(f"by_token{i}", f"token{i}") for i in range(3, 11)]
    
    active_param_sources = []
    for p in all_param_sources:
        param_name = p[0].replace("by_", "").replace("_jump", "")
        col_name = "offer" if param_name == "offer_id" else param_name
        if col_name in active_columns:
            active_param_sources.append(p)

    for source_key, name_key in active_param_sources:
        items = breakdown.get(source_key, [])
        param_name = source_key.replace("by_", "").replace("_jump", "")
        
        for item in items:
            value = item.get(name_key) or item.get("name") or "(empty)"
            
            # Пропускаем полностью пустые значения, если они не несут информации
            # Значения "(empty)", которые могут быть реальными данными, оставляем
            # Если это не token параметр, и значение "(empty)" - возможно данных нет
            # Но оставим для всех случаев, чтобы не терять информацию
            
            profit = item.get("profit", 0) or 0
            spend = item.get("spend", 0) or 0
            conversions = item.get("conversions", 0) or 0
            clicks = item.get("clicks", 0) or 0
            
            # Рассчитываем ROI правильно
            if spend > 0:
                roi = (profit / spend) * 100
            elif profit != 0:
                # Если spend=0 но есть profit (например, дополнительная монетизация)
                roi = float('inf') if profit > 0 else float('-inf')
            else:
                roi = 0
            
            # Трафик процент - оцениваем по кликам относительно общего количества
            total_clicks = campaign_summary.get("clicks", 1)
            traffic_pct = (clicks / total_clicks * 100) if total_clicks > 0 else 0
            
            # Профит процент - относительно общего профита
            total_profit = campaign_summary.get("profit", 0) or 0
            if total_profit != 0:
                profit_pct = (profit / abs(total_profit)) * 100
            else:
                profit_pct = 0
            
            breakdown_data[(param_name, value)] = {
                'profit': profit,
                'spend': spend,
                'conversions': conversions,
                'clicks': clicks,
                'roi': roi,
                'traffic_pct': traffic_pct,
                'profit_pct': profit_pct
            }
    
    # Группируем все параметры
    all_params = []
    
    # Добавляем strengths
    for s in strengths:
        param_type = s.get('type', '').lower()
        if param_type:
            value = s.get('value', '')
            key = (param_type, value)
            
            # Используем данные из breakdown если они есть, иначе из strengths
            if key in breakdown_data:
                bd = breakdown_data[key]
                profit = bd['profit']
                spend = bd['spend']
                conversions = bd['conversions']
                clicks = bd['clicks']
                roi = bd['roi']
                traffic_pct = bd['traffic_pct']
                profit_pct = bd['profit_pct']
            else:
                profit = s.get('profit', 0)
                spend = s.get('spend', 0)
                conversions = s.get('conversions', 0)
                clicks = s.get('clicks', 0)
                roi = s.get('roi', 0)
                traffic_pct = s.get('traffic_pct', 0)
                profit_pct = s.get('profit_pct', 0)
            
            all_params.append({
                'type': param_type,
                'value': value,
                'profit': profit,
                'spend': spend,
                'conversions': conversions,
                'clicks': clicks,
                'roi': roi,
                'traffic_pct': traffic_pct,
                'profit_pct': profit_pct,
                'is_positive': profit >= 0
            })
    
    # Добавляем weaknesses
    for w in weaknesses:
        param_type = w.get('type', '').lower()
        if param_type:
            value = w.get('value', '')
            key = (param_type, value)
            
            if key in breakdown_data:
                bd = breakdown_data[key]
                profit = bd['profit']
                spend = bd['spend']
                conversions = bd['conversions']
                clicks = bd['clicks']
                roi = bd['roi']
                traffic_pct = bd['traffic_pct']
                profit_pct = bd['profit_pct']
            else:
                profit = w.get('profit', 0)
                spend = w.get('spend', 0)
                conversions = w.get('conversions', 0)
                clicks = w.get('clicks', 0)
                roi = w.get('roi', 0)
                traffic_pct = w.get('traffic_pct', 0)
                profit_pct = w.get('profit_pct', 0)
            
            all_params.append({
                'type': param_type,
                'value': value,
                'profit': profit,
                'spend': spend,
                'conversions': conversions,
                'clicks': clicks,
                'roi': roi,
                'traffic_pct': traffic_pct,
                'profit_pct': profit_pct,
                'is_positive': profit >= 0
            })
    
    # Добавляем оставшиеся данные из breakdown
    for (param_type, value), data in breakdown_data.items():
        # Проверяем, не добавлен ли уже этот параметр
        if not any(p['type'] == param_type and p['value'] == value for p in all_params):
            all_params.append({
                'type': param_type,
                'value': value,
                'profit': data['profit'],
                'spend': data['spend'],
                'conversions': data['conversions'],
                'clicks': data['clicks'],
                'roi': data['roi'],
                'traffic_pct': data['traffic_pct'],
                'profit_pct': data['profit_pct'],
                'is_positive': data['profit'] >= 0
            })
    
    # Группируем по типу параметра
    from collections import defaultdict
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
        
        # ROI (целое число) - рассчитываем правильно
        if total_spend > 0:
            avg_roi = int(total_profit / total_spend * 100)
        elif total_profit != 0:
            # Если spend=0 но есть profit (дополнительная монетизация)
            avg_roi = 999 if total_profit > 0 else -999
        else:
            avg_roi = 0
        
        # Влияние - используем profit_pct или traffic_pct
        impact_score = min(abs(total_profit_pct), 100) * (1 if total_profit_pct >= 0 else -1) if abs(total_profit_pct) > 1 else min(total_traffic_pct, 100)
        
        # Количество положительных/отрицательных элементов
        positive_count = sum(1 for item in items if item['is_positive'])
        negative_count = len(items) - positive_count
        
        # Категория
        category = category_mapping.get(param_type, 'other')
        
        # Иконки для категорий
        category_icons = {
            'traffic': '🔵',
            'device': '🟢', 
            'demographics': '🟣',
            'content': '🟠',
            'technical': '⚙️',
            'other': '⚫'
        }
        category_icon = category_icons.get(category, '⚫')
        
        # Детализация по значениям (топ-3 по абсолютному profit)
        top_values = sorted(items, key=lambda x: abs(x['profit']), reverse=True)[:3]
        value_details = []
        for item in top_values:
            # Определяем рекомендацию для конкретного значения
            # Обрабатываем случай с бесконечным ROI
            roi_value = item['roi']
            # \u0417\u0430\u0449\u0438\u0442\u0430 \u043e\u0442 float('inf') — \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u043c \u0434\u043e \u0432\u044b\u0437\u043e\u0432\u0430 round()
            if isinstance(roi_value, float) and (roi_value != roi_value or roi_value == float('inf') or roi_value == float('-inf')):
                roi_display = '\u221e' if roi_value == float('inf') else ('-\u221e' if roi_value == float('-inf') else '?')
                roi_for_recommendation = 999 if roi_value == float('inf') else -999
            elif isinstance(roi_value, (int, float)):
                roi_display = round(roi_value)
                roi_for_recommendation = roi_value
            else:
                roi_display = roi_value
                roi_for_recommendation = 0
            
            val_recommendation = "SCALE" if item['profit'] > 0 and roi_for_recommendation > 50 else \
                               "OPTIMIZE" if item['profit'] > 0 else \
                               "FIX" if item['profit'] < 0 else "TEST"
            
            value_details.append({
                'value': item['value'],
                'profit': round(item['profit'], 2),
                'profit_pct': round(item['profit_pct'], 1),
                'traffic_pct': round(item['traffic_pct'], 1),
                'conversions': item['conversions'],
                'roi': roi_display,
                'recommendation': val_recommendation
            })
        
        # Общая рекомендация для категории
        overall_recommendation = _get_category_recommendation(
            total_profit, positive_count, negative_count, avg_roi
        )
        
        # Стиль отображения на основе рекомендации
        display_style = {
            'SCALE': {'color': 'green', 'icon': '🚀'},
            'OPTIMIZE': {'color': 'blue', 'icon': '📈'},
            'FIX': {'color': 'red', 'icon': '⚠️'},
            'TEST': {'color': 'yellow', 'icon': '🧪'},
            'HOLD': {'color': 'gray', 'icon': '⏸️'}
        }.get(overall_recommendation, {'color': 'gray', 'icon': '⏸️'})
        
        category_summary[param_type] = {
            'category': category,
            'icon': category_icon,
            'total_profit': round(total_profit, 2),
            'total_spend': round(total_spend, 2),
            'total_conversions': total_conversions,
            'total_clicks': total_clicks,
            'avg_roi': avg_roi,
            'traffic_pct': round(total_traffic_pct, 1),
            'profit_pct': round(total_profit_pct, 1),
            'impact_score': round(impact_score, 1),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'total_values': len(items),
            'top_values': value_details,
            'recommendation': overall_recommendation,
            'display_style': display_style,
            'compact_label': f"{category_icon} {param_type.upper()}",
            'compact_metrics': (lambda roi_str: f"ROI {roi_str} • {total_conversions} конв • {total_traffic_pct:.1f}% траф • {total_profit_pct:.1f}% проф • {impact_score:.1f}% влияние")("∞" if avg_roi >= 999 else ("-∞" if avg_roi <= -999 else f"{avg_roi}%")),
            'is_informative': True  # Все параметры считаем информативными, фильтрация на фронтенде
        }
    
    # Сортируем категории по impact_score (убывание)
    sorted_categories = dict(sorted(
        category_summary.items(),
        key=lambda x: abs(x[1]['impact_score']),
        reverse=True
    ))
    
    return sorted_categories


def _get_category_recommendation(total_profit, positive_count, negative_count, avg_roi):
    """Генерирует рекомендацию для категории параметров"""
    if total_profit > 0 and avg_roi > 50 and positive_count > negative_count * 2:
        return "SCALE"
    elif total_profit > 0 and avg_roi > 20:
        return "OPTIMIZE"
    elif total_profit < 0 and negative_count > 0:
        return "FIX"
    elif total_profit == 0 or (positive_count == 0 and negative_count == 0):
        return "TEST"
    else:
        return "HOLD"


def _find_killer_patterns(
    all_params: Dict[str, List[Dict]],
    campaign_summary: Dict[str, Any],
    breakdown_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Выявляет паттерны-убийцы - комбинации параметров, которые сливают бюджет.
    В первую очередь ищет СИНЕРГИИ (Связки).
    """
    killer_patterns = []
    seen_killer_keys = set()
    total_spend = campaign_summary.get("spend", 0) or 0
    
    # 1. СИНЕРГИИ И СВЯЗКИ (Наивысший приоритет)
    if breakdown_data:
        combos = breakdown_data.get("top_combinations_token2_offer_id_jump", [])
        for c in combos:
            c_profit = c.get("profit", 0)
            c_spend = c.get("spend", 0)
            c_conversions = c.get("conversions", 0)
            
            # Токсичная связка: сжигает бюджет без конверсий
            if c_spend > 20 and c_conversions == 0:
                token2 = c.get("token2") or c.get("name") or "(empty)"
                offer = c.get("offer_id") or "(empty)"
                lander = c.get("lander_id") or "(empty)"
                parts = [p for p in [token2, offer, lander] if p and p != "(empty)"]
                combo_name = " + ".join(parts) if len(parts) > 1 else (parts[0] if parts else "(empty)")
                combo_label = "SOURCE" if len(parts) == 1 and token2 != "(empty)" else "СВЯЗКА"
                
                _killer_key = ("combo", combo_name)
                seen_killer_keys.add(_killer_key)
                
                killer_patterns.append({
                    "pattern_type": "zero_conversions_synergy",
                    "parameter": combo_label,
                    "value": combo_name,
                    "profit": round(c_profit, 2),
                    "spend": round(c_spend, 2),
                    "reason": f"Токсичная: сжигает {c_spend:.0f}$ без конверсий",
                    "severity": "critical" if c_spend > 35 else "high"
                })
    
    # 2. ОДИНОЧНЫЕ ПАРАМЕТРЫ (Технические игнорируем, если они не критичны)
    tech_params = ["by_os", "by_device_type", "by_browser_name", "by_language", "by_os_version"]
    
    for param_name, values in all_params.items():
        for value_data in values:
            profit = value_data["profit"]
            spend = value_data["spend"]
            conversions = value_data["conversions"]
            
            # Критерии killer pattern:
            # 1. Профит < -$10 и 0 конверсий
            # 2. Spend > $20 и ROI < -50%
            # 3. Более 10% общего бюджета потрачено впустую
            
            _killer_key = (param_name, value_data["value"])
            is_tech = any(t in param_name for t in tech_params)
            
            if conversions == 0 and profit < -10:
                # Одиночные мусорные параметры выводим только если они ОЧЕНЬ убыточны (spend > $35)
                if is_tech and spend < 35:
                    continue
                    
                if _killer_key not in seen_killer_keys:
                    killer_patterns.append({
                        "pattern_type": "zero_conversions",
                        "parameter": param_name,
                        "value": value_data["value"],
                        "profit": round(profit, 2),
                        "spend": round(spend, 2),
                        "reason": f"0 конверсий при потере ${abs(profit):.2f}",
                        "severity": "high" if spend > 20 else "medium"
                    })
                    seen_killer_keys.add(_killer_key)
            
            elif spend > 0:
                roi = (profit / spend) * 100
                spend_pct = (spend / total_spend * 100) if total_spend > 0 else 0
                
                if roi < -50 and spend > 15:
                    # Одиночные мусорные параметры выводим только если они ОЧЕНЬ убыточны (spend_pct > 20%)
                    if is_tech and spend_pct < 20:
                        continue
                        
                    if _killer_key not in seen_killer_keys:
                        killer_patterns.append({
                            "pattern_type": "critical_roi",
                            "parameter": param_name,
                            "value": value_data["value"],
                            "roi": round(roi, 1),
                            "spend": round(spend, 2),
                            "spend_percentage": round(spend_pct, 1),
                            "reason": f"ROI {roi:.1f}% при spend ${spend:.2f}",
                            "severity": "critical" if spend_pct > 15 else "high"
                        })
                        seen_killer_keys.add(_killer_key)
                
                if spend_pct > 10 and profit < -5:
                    if is_tech and spend_pct < 15:
                        continue
                        
                    if _killer_key not in seen_killer_keys:
                        killer_patterns.append({
                            "pattern_type": "budget_drain",
                            "parameter": param_name,
                            "value": value_data["value"],
                            "spend_percentage": round(spend_pct, 1),
                            "profit": round(profit, 2),
                            "reason": f"{spend_pct:.1f}% бюджета слито (потеря ${abs(profit):.2f})",
                            "severity": "high" if spend_pct > 15 else "medium"
                        })
                        seen_killer_keys.add(_killer_key)
    
    # Сортируем по severity и размеру потерь
    severity_order = {"critical": 1, "high": 2, "medium": 3, "low": 4}
    killer_patterns.sort(key=lambda x: (
        severity_order.get(x["severity"], 5),
        abs(x.get("profit", 0))
    ))
    
    return killer_patterns[:10]  # Ограничиваем топ-10


def _find_winning_combos(
    all_params: Dict[str, List[Dict]],
    campaign_summary: Dict[str, Any],
    breakdown_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Выявляет winning combos - успешные комбинации параметров для масштабирования.
    В первую очередь ищет СИНЕРГИИ (Связки).
    """
    winning_combos = []
    seen_winning_keys = set()
    
    # 1. СИНЕРГИИ И СВЯЗКИ (Наивысший приоритет)
    if breakdown_data:
        combos = breakdown_data.get("top_combinations_token2_offer_id_jump", [])
        for c in combos:
            c_profit = c.get("profit", 0)
            c_spend = c.get("spend", 0)
            c_conversions = c.get("conversions", 0)
            
            # Успешная связка: ROI > 30%
            if c_spend > 15 and c_conversions >= 3 and c_profit > 10:
                c_roi = (c_profit / c_spend) * 100
                if c_roi > 30:
                    token2 = c.get("token2") or c.get("name") or "(empty)"
                    offer = c.get("offer_id") or "(empty)"
                    lander = c.get("lander_id") or "(empty)"
                    parts = [p for p in [token2, offer, lander] if p and p != "(empty)"]
                    combo_name = " + ".join(parts) if len(parts) > 1 else (parts[0] if parts else "(empty)")
                    combo_label = "SOURCE" if len(parts) == 1 and token2 != "(empty)" else "СВЯЗКУ"
                    
                    seen_winning_keys.add(combo_name)
                    
                    winning_combos.append({
                        "combo_type": "synergy",
                        "parameter": combo_label,
                        "value": combo_name,
                        "roi": round(c_roi, 1),
                        "profit": round(c_profit, 2),
                        "conversions": c_conversions,
                        "spend": round(c_spend, 2),
                        "reason": f"+{c_profit:.0f}$ (ROI {c_roi:.0f}%)",
                        "potential": "scale" if c_roi > 50 else "optimize"
                    })
    
    # 2. ОДИНОЧНЫЕ ПАРАМЕТРЫ 
    tech_params = ["by_os", "by_device_type", "by_browser_name", "by_language", "by_os_version"]
    
    # Ищем параметры с положительным ROI и достаточным объемом
    for param_name, values in all_params.items():
        for value_data in values:
            profit = value_data["profit"]
            spend = value_data["spend"]
            conversions = value_data["conversions"]
            
            if spend > 0 and conversions > 0:
                roi = (profit / spend) * 100
                epc = value_data.get("epc", 0)
                cpa = value_data.get("cpa", 0)
                
                # Критерии winning combo:
                # 1. ROI > 30% и минимум 2 конверсии
                # 2. EPC > $0.20 и spend > $10
                # 3. CPA < $3 и conversions >= 3
                
                
                is_tech = any(t in param_name for t in tech_params)
                
                if roi > 30 and conversions >= 2 and spend > 15:
                    # Технические параметры игнорируем, если ROI < 100%
                    if is_tech and roi < 100:
                        continue
                        
                    winning_combos.append({
                        "combo_type": "high_roi",
                        "parameter": param_name,
                        "value": value_data["value"],
                        "roi": round(roi, 1),
                        "profit": round(profit, 2),
                        "conversions": conversions,
                        "spend": round(spend, 2),
                        "reason": f"ROI {roi:.1f}% с {conversions} конверсиями",
                        "potential": "scale" if roi > 50 else "optimize"
                    })
                
                elif epc > 0.20 and spend > 10:
                    winning_combos.append({
                        "combo_type": "high_epc",
                        "parameter": param_name,
                        "value": value_data["value"],
                        "epc": round(epc, 3),
                        "profit": round(profit, 2),
                        "spend": round(spend, 2),
                        "reason": f"EPC ${epc:.3f} при spend ${spend:.2f}",
                        "potential": "scale" if epc > 0.35 else "test_more"
                    })
                
                elif cpa < 3.0 and conversions >= 3:
                    winning_combos.append({
                        "combo_type": "low_cpa",
                        "parameter": param_name,
                        "value": value_data["value"],
                        "cpa": round(cpa, 2),
                        "conversions": conversions,
                        "profit": round(profit, 2),
                        "reason": f"CPA ${cpa:.2f} с {conversions} конверсиями",
                        "potential": "scale" if cpa < 2.0 else "optimize"
                    })
    
    # Сортируем по потенциалу и прибыли
    potential_order = {"scale": 1, "optimize": 2, "test_more": 3}
    winning_combos.sort(key=lambda x: (
        potential_order.get(x["potential"], 4),
        -x.get("profit", 0)  # Отрицательное для сортировки по убыванию
    ))
    
    return winning_combos[:10]  # Ограничиваем топ-10


def _analyze_correlations(all_params: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """
    Анализирует корреляции между параметрами.
    Упрощенная версия - ищет параметры с похожим распределением прибыли.
    """
    correlations = []
    
    # Преобразуем данные в матрицу значений для анализа
    param_names = list(all_params.keys())
    
    if len(param_names) < 2:
        return correlations
    
    # Для каждой пары параметров проверяем, есть ли общие паттерны
    for i in range(len(param_names)):
        for j in range(i + 1, len(param_names)):
            param1 = param_names[i]
            param2 = param_names[j]
            
            values1 = all_params[param1]
            values2 = all_params[param2]
            
            if not values1 or not values2:
                continue
            
            # Простой анализ: если оба параметра имеют сильные положительные/отрицательные значения
            avg_profit1 = sum(v["profit"] for v in values1) / len(values1)
            avg_profit2 = sum(v["profit"] for v in values2) / len(values2)
            
            # Определяем направление (положительное/отрицательное)
            direction1 = "positive" if avg_profit1 > 0 else "negative"
            direction2 = "positive" if avg_profit2 > 0 else "negative"
            
            if direction1 == direction2:
                # Рассчитываем силу корреляции (упрощенно)
                profit_range1 = max(v["profit"] for v in values1) - min(v["profit"] for v in values1)
                profit_range2 = max(v["profit"] for v in values2) - min(v["profit"] for v in values2)
                
                if profit_range1 > 0 and profit_range2 > 0:
                    # Нормализованная разница в диапазонах
                    range_diff = abs(profit_range1 - profit_range2) / max(profit_range1, profit_range2)
                    
                    if range_diff < 0.5:  # Если диапазоны похожи
                        correlation_strength = "medium" if range_diff < 0.3 else "weak"
                        
                        correlations.append({
                            "parameter1": param1,
                            "parameter2": param2,
                            "direction": direction1,
                            "correlation_strength": correlation_strength,
                            "avg_profit1": round(avg_profit1, 2),
                            "avg_profit2": round(avg_profit2, 2),
                            "insight": f"Оба параметра имеют {direction1} влияние на профит"
                        })
    
    return correlations[:5]  # Ограничиваем топ-5 корреляций


def _calculate_confidence_score(
    profit: float,
    spend: float,
    conversions: int,
    action_type: str,
    campaign_volatility: float = 0,
    impact_score: float = 0
) -> int:
    """
    Высчитывает процент уверенности (0-100%) для рекомендации.
    Базируется на объеме данных, статистической значимости и волатильности среды.
    """
    score = 50.0  # Базовая уверенность
    
    # 1. Объем данных (Conversions)
    if conversions == 0:
        if spend > 30 and action_type == "kill":
            score += 30  # Чем больше спенд без конверсий, тем мы увереннее отключаем
        elif spend > 15 and action_type == "kill":
            score += 15
        else:
            score -= 20  # Мало данных
    elif conversions >= 5:
        score += 20
    elif conversions >= 3:
        score += 10
    
    # 2. Объем денег (Spend) - статистическая значимость
    if spend > 100:
        score += 15
    elif spend > 50:
        score += 10
    elif spend < 15:
        score -= 15  # Слишком мало потрачено для уверенных выводов
        
    # 3. Волатильность кампании (неустойчивость среды снижает уверенность)
    if campaign_volatility > 30:
        score -= 15
    elif campaign_volatility > 15:
        score -= 5
    elif campaign_volatility < 10:
        score += 5  # Размеренная среда — прогнозам можно верить
        
    # 4. Специфика действий
    roi = (profit / spend * 100) if spend > 0 else 0
    
    if action_type == "kill":
        if roi < -80:
            score += 15
        elif roi < -50:
            score += 5
    elif action_type == "scale":
        if roi > 100:
            score += 15
        elif roi > 50:
            score += 10
            
    # Влияние параметра на всю кампанию
    if abs(impact_score) > 30:
        score += 10
            
    return max(10, min(99, int(score)))


def generate_prioritized_recommendations(
    analysis: Dict[str, Any],
    deep_analysis: Dict[str, Any],
    brain: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Генерирует приоритетные рекомендации с оценкой влияния.
    Использует глубокий анализ для определения наиболее эффективных действий
    И снабжает действия процентом уверенности (confidence score).
    """
    recommendations = []
    volatility = analysis.get("volatility", 0) or 0
    
    # 1. Рекомендации на основе killer patterns
    for pattern in deep_analysis.get("killer_patterns", []):
        if pattern["severity"] in ["critical", "high"]:
            action = "kill" if pattern["severity"] == "critical" else "optimize"
            profit = pattern.get("profit", 0)
            spend = pattern.get("spend", 0)
            
            # Рассчитываем уверенность: если 0 конверсий, передаем 0, иначе пытаемся достать (но в паттернах-убийцах обычно их 0)
            confidence = _calculate_confidence_score(
                profit=profit,
                spend=spend,
                conversions=0 if pattern.get("pattern_type") == "zero_conversions" else 1,
                action_type=action,
                campaign_volatility=volatility
            )
            
            recommendations.append({
                "priority": 1 if pattern["severity"] == "critical" else 2,
                "action": action,
                "parameter": pattern["parameter"],
                "value": pattern["value"],
                "description": f"Устранить паттерн-убийцу: {pattern['reason']}",
                "confidence_score": confidence,
                "expected_impact": {
                    "profit_improvement": abs(profit),
                    "risk_reduction": "high" if pattern["severity"] == "critical" else "medium"
                },
                "implementation_steps": [
                    f"Отключить {pattern['parameter']} = {pattern['value']}",
                    "Проверить аналогичные сегменты",
                    "Снизить bid на 50% если нельзя отключить полностью"
                ]
            })
    
    # 2. Рекомендации на основе winning combos
    for combo in deep_analysis.get("winning_combos", []):
        if combo["potential"] == "scale":
            profit = combo.get("profit", 0)
            spend = combo.get("spend", 0)
            conversions = combo.get("conversions", 2)
            
            confidence = _calculate_confidence_score(
                profit=profit,
                spend=spend,
                conversions=conversions,
                action_type="scale",
                campaign_volatility=volatility
            )
            
            recommendations.append({
                "priority": 2,
                "action": "scale",
                "parameter": combo["parameter"],
                "value": combo["value"],
                "description": f"Масштабировать winning combo: {combo['reason']}",
                "confidence_score": confidence,
                "expected_impact": {
                    "profit_improvement": profit * 0.3,  # 30% от текущей прибыли
                    "risk": "low"
                },
                "implementation_steps": [
                    f"Увеличить бюджет для {combo['parameter']} = {combo['value']} на 20%",
                    "Создать отдельный campaign для этого сегмента",
                    "Мониторить ROI ежедневно в течение 3 дней"
                ]
            })
    
    # 3. Рекомендации на основе анализа влияния параметров
    for param_name, impact in deep_analysis.get("most_influential_params", []):
        if abs(impact["impact_score"]) > 10:  # Значительное влияние
            action = "optimize" if impact["total_profit"] < 0 else "scale"
            
            confidence = _calculate_confidence_score(
                profit=impact["total_profit"],
                spend=impact.get("total_spend", 0),
                conversions=2, # Approximate for general influential params
                action_type=action,
                campaign_volatility=volatility,
                impact_score=impact["impact_score"]
            )
            
            recommendations.append({
                "priority": 2 if abs(impact["impact_score"]) > 20 else 3,
                "action": action,
                "parameter": param_name,
                "description": f"Параметр влияет на {abs(impact['impact_score'])}% профита",
                "confidence_score": confidence,
                "expected_impact": {
                    "profit_improvement": abs(impact["total_profit"]) * 0.2,  # 20% от текущего влияния
                    "parameter_impact": impact["impact_score"]
                },
                "implementation_steps": [
                    f"Проанализировать все значения {param_name}",
                    f"Сфокусироваться на {impact['best_value']} (лучшее значение)",
                    f"Исключить {impact['worst_value']} (худшее значение)"
                ]
            })
    
    # Сортируем по приоритету и ожидаемому влиянию
    recommendations.sort(key=lambda x: (
        x["priority"],
        -x["expected_impact"]["profit_improvement"]
    ))
    
    return recommendations


def get_deep_key_drivers(
    breakdown: Dict[str, Any],
    campaign_summary: Dict[str, Any],
    analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Генерирует расширенную версию Key Drivers с глубоким анализом.
    """
    # Получаем глубокий анализ
    deep_analysis = analyze_parameter_interconnections(breakdown, campaign_summary)
    
    # Группируем драйверы по категориям
    key_drivers = {
        "killer_patterns": deep_analysis.get("killer_patterns", []),
        "winning_combos": deep_analysis.get("winning_combos", []),
        "most_influential": deep_analysis.get("most_influential_params", []),
        "correlations": deep_analysis.get("correlations", []),
        "summary": {
            "total_parameters": deep_analysis.get("total_parameters_analyzed", 0),
            "killer_patterns_count": len(deep_analysis.get("killer_patterns", [])),
            "winning_combos_count": len(deep_analysis.get("winning_combos", [])),
            "high_impact_params": sum(
                1 for impact in deep_analysis.get("parameter_impact", {}).values()
                if abs(impact.get("impact_score", 0)) > 15
            )
        }
    }
    
    return key_drivers