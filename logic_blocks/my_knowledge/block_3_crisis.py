class AffiliateBlacklistEngine:
    """
    БЛОК 3: Чистка и Гипотезы.
    Правила отключения источников (Blacklist) и тестирование Direct Link.
    """

    def analyze_source_for_blacklist(self, clicks, roi, spend):
        """
        ЛОГИКА ЧЕРНОГО СПИСКА:
        Если источник слил бюджет и ROI критически низкий — в бан.
        """
        # Условия из практики: 50+ кликов и ROI хуже -50%
        if clicks > 50 and roi < -50.0:
            return {
                "action": "EXCLUDE (Blacklist)",
                "reason": f"Source burned ${spend} with ROI {roi}%. Шансов на восстановление нет."
            }
        return {"action": "Monitor", "reason": "Мало данных или ROI в пределах нормы."}

    def hypothesis_direct_link_test(self, offer_name):
        """
        ТЕСТ DIRECT LINK (Без лендинга):
        Применяется, когда есть подозрение на выгорание лендингов.
        """
        return {
            "strategy": "Create Direct Link Path",
            "execution": [
                f"Создать новый Путь только с оффером {offer_name}.",
                "Убрать лендинги (Lander -> Direct).",
                "Вес: ~30% от основного потока."
            ],
            "goal": "Проверить 'чистую' конверсию оффера. Если лидов нет даже так — оффер мертв."
        }

    def multi_offer_strategy(self, offer_list):
        """
        РОТАЦИЯ ОФФЕРОВ:
        Если лидер нестабилен, держим 2-3 запасных оффера в ротации.
        """
        active = [o for o in offer_list if o['roi'] > -10.0]
        return {
            "action": "Keep Active",
            "offers_count": len(active),
            "advice": "Не держать все яйца в одной корзине при волатильном трафике."
        }