# Temporary script to generate the correct code to insert into deep_analysis_extensions.py
def _find_synergies(breakdown_data, total_spend):
    """
    Фабрика инсайтов: Ищет синергию (связки) между параметрами.
    Например: Token2 + OS, Token8 + Lander.
    В сыром breakdown_data лежат отдельные параметры, 
    но у нас есть top_combinations_token2_offer_id_jump.
    """
    synergies = []
    
    # 1. Извлекаем готовые комбинации из breakdown
    # В Affiliate Brain V2 они заранее считаются в by_path, by_lander_id_jump, 
    # top_combinations_token2_offer_id_jump
    
    # Обрабатываем token2 + offer_id + lander_id
    combos = breakdown_data.get("top_combinations_token2_offer_id_jump", [])
    for c in combos:
        spend = c.get("spend", 0)
        profit = c.get("profit", 0)
        conversions = c.get("conversions", 0)
        clicks = c.get("clicks", 0)
        
        token2 = c.get("token2") or c.get("name") or "(empty)"
        offer = c.get("offer_id") or "(empty)"
        lander = c.get("lander_id") or "(empty)"
        
        if spend > 15 and conversions >= 3 and profit > 10:
            roi = (profit / spend) * 100
            if roi > 30:
                synergies.append({
                    "synergy_type": "winning_combo",
                    "components": [f"Источник: {token2}", f"Оффер: {offer}", f"Лендинг: {lander}"],
                    "profit": profit,
                    "spend": spend,
                    "conversions": conversions,
                    "roi": roi,
                    "action": "scale",
                    "reason": f"Мощная связка: приносит ${profit:.0f} (ROI {roi:.0f}%)"
                })
        
        # Токсичные связки (Киллеры)
        elif spend > 30 and conversions == 0:
            synergies.append({
                "synergy_type": "toxic_combo",
                "components": [f"Источник: {token2}", f"Оффер: {offer}", f"Лендинг: {lander}"],
                "profit": profit,
                "spend": spend,
                "conversions": conversions,
                "roi": -100,
                "action": "kill",
                "reason": f"Токсичная связка: сжигает бюджет (${spend:.0f} без конверсий)"
            })
            
    # Сортируем по максимальному импакту (модуль профита)
    synergies.sort(key=lambda x: abs(x["profit"]), reverse=True)
    return synergies[:10]
