class AffiliateExperimentsPhase5:
    """
    БЛОК 5: Агрессивное Масштабирование и Эксперименты.
    Правила повышения бюджета на 30-50%, изоляции лидера и жесткие лимиты тестов.
    """

    def calculate_aggressive_budget_increase(self, current_budget, is_main_path_profitable):
        """
        ПРАВИЛО АГРЕССИВНОГО БЮДЖЕТА:
        Поднимаем сегодня же на 30-50%.
        Теория: Основной путь (Winner) вытянет риски тестов.
        """
        if is_main_path_profitable:
            increase_min = 1.30 # +30%
            increase_max = 1.50 # +50%

            new_budget_min = round(current_budget * increase_min, 2)
            new_budget_max = round(current_budget * increase_max, 2)

            return {
                "action": "SCALE IMMEDIATELY",
                "recommendation": f"Поднять бюджет с ${current_budget} до ${new_budget_min} - ${new_budget_max}.",
                "logic": "Кампания в уверенном плюсе. Основной путь перекроет риск тестов. Нам нужен максимальный объем."
            }
        return {"action": "Fix Main Path First", "logic": "Нельзя скейлить убыток."}

    def winner_isolation_strategy(self, winner_has_unique_jump):
        """
        ЛОГИКА ИЗОЛЯЦИИ ЛИДЕРА (Path Karma):
        Обычно оставляем лидера в старом пути (с кармой).
        Переносим ТОЛЬКО если он технически несовместим с другими (свой джамп).
        """
        if winner_has_unique_jump:
            return {
                "action": "MOVE TO NEW PATH",
                "reason": "Лидер требует специфический Jump. Другие офферы на нем не работают."
            }
        else:
            return {
                "action": "KEEP IN OLD PATH",
                "reason": "Сохраняем накопленную оптимизацию (Карму) пути. Аутсайдеров выносим в новый путь."
            }

    def calculate_outsider_weight(self, roi, current_daily_clicks):
        """
        ВЕСА ДЛЯ АУТСАЙДЕРОВ (В песочнице):
        Минусовые: до 30% (но не >100 кликов).
        Плюсовые (слабые): до 50%.
        """
        if roi < 0:
            if current_daily_clicks >= 100:
                return {"weight": 0, "action": "PAUSE (Daily Click Cap Reached)"}
            return {
                "weight": 30,
                "action": "Limit Exposure",
                "logic": "Минусит. Даем до 30% трафика, жесткий контроль (до 100 кликов/день)."
            }
        else:
            return {
                "weight": 50,
                "action": "Maintain Volume",
                "logic": "В плюсе. Можно дать 50% от веса лидера для до-теста."
            }

    def evaluate_lander_test_rules(self, spend, payout, conversions, roi):
        """
        КРИТЕРИЙ ОЖИВЛЕНИЯ ЛЕНДА (Жесткие правила):
        x1 выплата без лидов = СТОП.
        """
        # Сценарий 1: Нет конверсий вообще
        if conversions == 0:
            if spend >= payout: # Слита 1 выплата
                return "STOP IMMEDIATE (Rule: x1 Payout with 0 leads = Dead)"
            else:
                return "CONTINUE (Waiting for x1 spend)"

        # Сценарий 2: Есть конверсии
        else:
            if spend < (payout * 2):
                return "CONTINUE (Test up to x2 payout)"
            else:
                # Если слили x2
                if roi <= 0: # 0 или слабый плюс
                    return "LOW VOLUME MODE (Leave on minimal traffic)"
                else:
                    return "SCALE (Good ROI found)"