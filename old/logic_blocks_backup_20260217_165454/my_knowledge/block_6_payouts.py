class AffiliatePayoutEnginePhase6:
    """
    БЛОК 6: Точная Стабилизация (Payout Logic).
    Логика очистки по кол-ву выплат и защита 'Зацепа'.
    """

    def calculate_blacklist_threshold_by_payout(self, payout, spend, roi):
        """
        ПРАВИЛО БЛЭКЛИСТА (По выплатам):
        Фиксируем 3-5 выплат.
        """
        # Пороги
        threshold_min = payout * 3
        threshold_max = payout * 5

        if spend > threshold_min:
            if roi < -0.50: # Если слито 3 выплаты и ROI хуже -50%
                return {
                    "action": "BLACKLIST IMMEDIATE",
                    "reason": f"Слито ${spend:.2f} (>3 выплат) с ROI {roi:.1f}%. Шансов нет."
                }
            elif spend > threshold_max and roi < 0: # Если слито 5 выплат и просто минус
                return {
                    "action": "BLACKLIST (Hard Stop)",
                    "reason": f"Слито ${spend:.2f} (>5 выплат). Профита нет. Отключаем."
                }

        return {"action": "Monitor", "status": "Accumulating Data"}

    def calculate_budget_scaling_rounded(self, current_budget):
        """
        ПОВЫШЕНИЕ БЮДЖЕТА (С округлением):
        Шаг +50%, округляем до красивого числа.
        """
        target = current_budget * 1.50 # +50%
        # Округление до ближайших 10 (например 45 -> 50)
        new_budget = round(target / 10) * 10

        return {
            "action": "SCALE BUDGET",
            "new_daily_limit": new_budget,
            "logic": "Тренд положительный. Поднимаем на 50% с округлением."
        }

    def zacep_protection_strategy(self, current_path_has_profit):
        """
        ЗАЩИТА ЗАЦЕПА:
        Если в пути есть профит — РУКИ ПРОЧЬ.
        """
        if current_path_has_profit:
            return {
                "Old Path": "DO NOT TOUCH. Keep Leader & Settings as is.",
                "New Path": "Create NEW Path for testing offers/landers.",
                "Logic": "В старом пути есть 'Зацеп'. Любое изменение сломает карму. Тесты — в новый путь."
            }
        return {"action": "Optimize Current Path"}

    def new_path_test_limit(self, payout):
        """
        ЛИМИТЫ НА ТЕСТ (В новом пути):
        Сколько денег даем новому пути на жизнь.
        """
        limit_min = payout * 2
        limit_max = payout * 3

        return {
            "budget_limit": f"${limit_min} - ${limit_max}",
            "stop_rule": "Если после слива x3 выплат в новом пути ROI отрицательный — выключаем путь."
        }