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

    def epc_cpc_deviation_rule(self, offer_epc, current_cpc):
        """
        ПРАВИЛО ОТКЛОНЕНИЯ (DEVIATION RULE 5-8%):
        Допустимый убыток оффера перед отключением.
        """
        if current_cpc == 0: return "Unknown CPC"
        
        loss_percent = (current_cpc - offer_epc) / current_cpc

        if loss_percent > 0.08:
            return "KILL OFFER (Critical Deviation > 8%)"
        elif loss_percent > 0.05:
            return "WARNING (Deviation 5-8%. Reduce weight)"
        else:
            return "ACCEPTABLE (Micro-loss < 5% or Profit. Keep working)"

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