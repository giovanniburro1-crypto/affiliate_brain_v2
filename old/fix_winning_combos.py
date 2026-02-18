import json

# Читаем текущий код
with open("backend/services/campaign_analysis_service.py", "r") as f:
    lines = f.readlines()

# Находим функцию get_bot_actions и добавляем логику winning combos
# Ищем строку с "def get_bot_actions"
insert_index = None
for i, line in enumerate(lines):
    if "def get_bot_actions(" in line:
        insert_index = i
        break

if insert_index:
    # Вставляем новую логику после определения переменных
    new_logic = '''
    # === WINNING COMBOS ANALYSIS ===
    # Ищем лучшую связку OS+Device+Offer+Lander с минимум 3 конверсиями
    
    top_combos = breakdown.get("top_combinations_token2_offer_id_jump", [])
    if not top_combos:
        # Пытаемся собрать из отдельных параметров
        by_os = breakdown.get("by_os", [])
        by_device = breakdown.get("by_device_type", [])
        by_offer = breakdown.get("by_offer_id", [])
        by_lander = breakdown.get("by_lander_id_jump", [])
        
        # Находим лучшие по каждому параметру
        best_os = max(by_os, key=lambda x: x.get("profit", 0)) if by_os else None
        best_device = max(by_device, key=lambda x: x.get("profit", 0)) if by_device else None
        best_offer = max(by_offer, key=lambda x: x.get("profit", 0)) if by_offer else None
        best_lander = max(by_lander, key=lambda x: x.get("profit", 0)) if by_lander else None
        
        if best_os and best_device and best_offer and best_lander:
            total_conversions = (best_os.get("conversions", 0) + best_device.get("conversions", 0)) / 2
            total_profit = sum([
                best_os.get("profit", 0),
                best_device.get("profit", 0),
                best_offer.get("profit", 0),
                best_lander.get("profit", 0)
            ]) / 4
            
            if total_conversions >= 3 and total_profit > 10:
                actions.append({
                    "type": "winning_combo",
                    "text": f"💎 WINNING COMBO",
                    "combo": {
                        "os": best_os.get("os", ""),
                        "device": best_device.get("device_type", ""),
                        "offer": best_offer.get("offer_id", ""),
                        "lander": best_lander.get("lander_id", "")
                    },
                    "reason": f"OS: {best_os.get('os')} + Device: {best_device.get('device_type')} + Offer: {best_offer.get('offer_id')} + Lander: {best_lander.get('lander_id')} → Profit ${total_profit:.0f}, {total_conversions:.0f} conv",
                    "confidence": "HIGH"
                })
    else:
        # Анализируем готовые комбинации
        for combo in top_combos[:3]:  # Топ-3
            conversions = combo.get("conversions", 0)
            profit = combo.get("profit", 0)
            roi = combo.get("roi", 0)
            
            if conversions >= 3 and profit > 10:
                actions.append({
                    "type": "winning_combo",
                    "text": f"💎 WINNING COMBO",
                    "combo": {
                        "offer": combo.get("offer_id", ""),
                        "lander": combo.get("lander_id", ""),
                        "creative": combo.get("token2", "")
                    },
                    "reason": f"Offer {combo.get('offer_id')} + Lander {combo.get('lander_id')} → ROI {roi}%, Profit ${profit}, {conversions} conv",
                    "confidence": "HIGH"
                })
    
'''
    
    # Находим где кончается блок действий
    for i in range(insert_index, len(lines)):
        if "return actions" in lines[i]:
            lines.insert(i, new_logic)
            break
    
    # Записываем обратно
    with open("backend/services/campaign_analysis_service.py", "w") as f:
        f.writelines(lines)
    
    print("✅ Winning Combos добавлены!")
else:
    print("❌ Не нашел функцию get_bot_actions")

