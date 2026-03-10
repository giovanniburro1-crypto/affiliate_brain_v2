class AffiliateKnowledgeBase:
    """
    БЛОК 1: Основа стратегии.
    Логика стоп-лоссов, поиска 'Зацепа' и расчета ставки для Whitelist.
    """

    def __init__(self):
        self.rules = {
            "stop_loss_multiplier": 2.0,    # Лимит слива = 2 выплаты
            "zacep_threshold": 3,           # Минимум 3 конверсии для зацепа
            "whitelist_bid_increase": 0.20  # Старт Whitelist с +20% к биду
        }

    def analyze_stop_loss(self, spend, payout, conversions):
        """
        ПРАВИЛО СТОПА (Money Management):
        Смотрим только на деньги. Если слито 2 выплаты без лидов — стоп.
        """
        loss_limit = payout * self.rules["stop_loss_multiplier"]
        
        # Минимальный бюджет для стопа, чтобы не стопать новые кампании на копейках
        min_spend_limit = 10.0
        actual_limit = max(loss_limit, min_spend_limit)

        if conversions == 0 and spend >= actual_limit:
            return {
                "action": "STOP IMMEDIATELY",
                "reason": f"Слито {spend} (Лимит {round(actual_limit, 1)}, Payout {round(payout, 1)}). Нет смысла держать дальше."
            }
            
        reason_msg = f"В тесте (Слито {spend} из {round(actual_limit, 1)})" if conversions == 0 else f"Есть лиды ({conversions})"
        return {"action": "CONTINUE", "status": "Testing in progress", "reason": reason_msg}

    def scaling_strategy_whitelist(self, current_bid, source_epc, has_jump_monetization):
        """
        СТРАТЕГИЯ ВАЙТЛИСТА И СТАВКИ:
        Повышаем ставку, чтобы компенсировать потерю объема при сужении таргета.
        """
        # Базовое повышение
        proposed_bid = current_bid * (1 + self.rules["whitelist_bid_increase"])

        # Потолок ставки (Max Bid)
        if has_jump_monetization:
            # С Джампом можем ставить в ноль по EPC (заработок с домонетизации)
            max_bid = source_epc
        else:
            # Без Джампа нужна чистая маржа (оставляем 6 копеек)
            max_bid = source_epc - 0.06

        # Защита от отрицательного бида
        if max_bid <= 0: max_bid = 0.001
        
        final_bid = min(proposed_bid, max_bid)

        return {
            "action": "Create Whitelist Campaign",
            "bid": round(final_bid, 3),
            "logic": f"Повысили ставку на 20% (но не выше EPC), чтобы выкупить 100% качественного трафика."
        }

    def find_zacep(self, conversions, spend=0, payout=0):
        """
        ПОИСК ЗАЦЕПА (HOOK):
        Главная цель тестов — найти сорс или оффер с достаточным кол-вом лидов.
        Используется динамический порог.
        """
        import math
        
        # Динамический порог: ожидаем 20% конверсии от потраченного
        if payout > 0:
            expected_conversions_by_spend = math.ceil((spend / payout) * 0.2)
            dynamic_threshold = max(self.rules["zacep_threshold"], expected_conversions_by_spend)
        else:
            dynamic_threshold = self.rules["zacep_threshold"]
            
        if conversions >= dynamic_threshold:
            return {
                "status": "ZACEP FOUND!",
                "next_steps": [
                    "Изолировать в отдельный путь/кампанию.",
                    "Подключить Jump (домонетизацию) для разгона профита.",
                    "Убрать конкурентов из ротации."
                ]
            }
        return {"status": "Searching...", "reason": f"Конверсий: {conversions}, Требуется: {dynamic_threshold}"}