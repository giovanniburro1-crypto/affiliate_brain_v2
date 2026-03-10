class AffiliateVolatilityPhase4:
    """
    БЛОК 4: Стабилизация и Волатильность.
    Управление бюджетом при скачках ROI и правила допустимых отклонений.
    """

    def analyze_volatility_and_budget(self, daily_roi_history, current_budget):
        """
        УПРАВЛЕНИЕ БЮДЖЕТОМ ПРИ ВОЛАТИЛЬНОСТИ:
        Если общий тренд за 3 дня положительный (>15%), повышаем бюджет,
        даже если вчера был минус.
        """
        if not daily_roi_history:
            return {"action": "Wait for data"}

        avg_roi = sum(daily_roi_history) / len(daily_roi_history)

        if avg_roi > 15.0:
            return {
                "action": "INCREASE BUDGET (Volatility Logic)",
                "new_daily_limit": current_budget + 20, # Шаг +$20 для сглаживания
                "reason": f"Средний ROI {avg_roi}% (несмотря на скачки). Нужен объем для статистики."
            }
        return {"action": "Hold Budget", "reason": "ROI нестабилен и низок."}

    def epc_cpc_deviation_rule(self, offer_epc, current_cpc, current_budget=0):
        """
        ПРАВИЛО ОТКЛОНЕНИЯ (DEVIATION RULE):
        Допустимый убыток оффера перед отключением с учетом текущего бюджета.
        """
        if current_cpc == 0: return "Unknown CPC"
        
        loss_percent = (current_cpc - offer_epc) / current_cpc
        
        # Динамические пороги отклонения в зависимости от бюджета
        if current_budget < 50:
            critical_limit = 0.15 # 15% на микро-бюджете (стадия разгона/теста)
            warning_limit = 0.10
        elif current_budget > 500:
            critical_limit = 0.05 # 5% на большом спенде (жесткий контроль)
            warning_limit = 0.03
        else:
            critical_limit = 0.08 # Стандартные 8%
            warning_limit = 0.05

        if loss_percent > critical_limit:
            return f"KILL OFFER (Critical Deviation > {critical_limit*100}%)"
        elif loss_percent > warning_limit:
            return f"WARNING (Deviation {warning_limit*100}-{critical_limit*100}%. Reduce weight)"
        else:
            return "ACCEPTABLE (Micro-loss or Profit. Keep working)"

    def probability_concentration_rule(self, current_offer_count):
        """
        ПРАВИЛО КОНЦЕНТРАЦИИ:
        На малом бюджете (<$50) не распыляемся.
        """
        if current_offer_count > 4:
            return {
                "action": "REDUCE OFFERS",
                "instruction": "Оставить только Топ-4 по EPC. Иначе не соберем статистику.",
            }
        return {"action": "Optimal Count"}