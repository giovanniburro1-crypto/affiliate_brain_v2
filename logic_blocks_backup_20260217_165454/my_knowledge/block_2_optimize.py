class AffiliateOptimizationEngine:
    """
    БЛОК 2: Движок Оптимизации.
    Расчет долей трафика, выбор формата лендингов и стартовый биддинг.
    """

    def calculate_traffic_share(self, path_weights):
        """
        РАСПРЕДЕЛЕНИЕ ТРАФИКА (Правило весов):
        Превращает веса (100/50/100) в реальные проценты (40%/20%/40%).
        """
        total_weight = sum(path_weights)
        if total_weight == 0:
            return [0] * len(path_weights)

        shares = [round((w / total_weight) * 100, 1) for w in path_weights]

        return {
            "input_weights": path_weights,
            "traffic_shares_percent": shares,
            "logic": "Вес 50 при наличии 100 — это не половина, а треть или четверть трафика. Считаем от суммы."
        }

    def determine_bid_strategy(self, current_epc, current_bid, days_running):
        """
        СТРАТЕГИЯ СТАВКИ ПО ДНЯМ:
        День 1-2: Не задирать CPC (Интуитивная защита).
        День 3+: Можно повышать агрессивно по EPC.
        """
        if days_running < 2:
            # Осторожность на старте
            return {
                "strategy": "Conservative",
                "recommended_bid": current_bid, # Или +10% максимум
                "reason": "Первые дни теста. Не знаем объем и скорость выгорания. Оставляем текущий бид."
            }
        else:
            # Агрессия на опыте
            margin_buffer = 0.06
            if current_epc <= margin_buffer:
                rec_bid = 0.001 # Минималка, если EPC низок
            else:
                rec_bid = round(current_epc - margin_buffer, 3)
                
            return {
                "strategy": "Aggressive",
                "recommended_bid": rec_bid,
                "reason": "Статистика подтверждена. Выжимаем максимум объема."
            }

    def set_testing_budget(self):
        """
        БЮДЖЕТИРОВАНИЕ ТЕСТА:
        """
        return {
            "daily_budget": "$20 - $30",
            "total_budget": "UNLIMITED (Do not set)",
            "reason": "Никогда не ставим Total Budget на тесте, чтобы случайно не стопнуть кампанию на разгоне."
        }