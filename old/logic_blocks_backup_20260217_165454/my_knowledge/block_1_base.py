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

        if conversions == 0 and spend >= loss_limit:
            return {
                "action": "STOP IMMEDIATELY",
                "reason": f"Слито {spend} (Лимит {loss_limit}). Нет смысла держать дальше, даже если прошел 1 час."
            }
        return {"action": "CONTINUE", "status": "Testing in progress"}

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

    def find_zacep(self, conversions):
        """
        ПОИСК ЗАЦЕПА (HOOK):
        Главная цель тестов — найти сорс или оффер с 3+ лидами.
        """
        if conversions >= self.rules["zacep_threshold"]:
            return {
                "status": "ZACEP FOUND!",
                "next_steps": [
                    "Изолировать в отдельный путь/кампанию.",
                    "Подключить Jump (домонетизацию) для разгона профита.",
                    "Убрать конкурентов из ротации."
                ]
            }
        return {"status": "Searching..."}