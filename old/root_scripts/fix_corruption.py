import codecs
file_path = "/Users/andreylp/affiliate_brain/app/backend/brain/knowledge_base_v2_complete.py"
with codecs.open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """    def get_decision_history(self, limit: int = 100) -> List[Dict]:
        \"\"\"Получит    def get_segment_columns(self, traffic_source: Optional[str] = None) -> List[str]:
        \"\"\"
        Список колонок для сегментного анализа.
        Приоритет: insight_config.json (weight > 0) → segment_config.json → default.
        Insight Factory Settings являются единым источником правды о том, какие
        параметры нужно анализировать для каждого трафик-сорса.
        \"\"\"
        # --- 1. Пробуем insight_config.json ---
        insight_path = self._base.parent / "backend" / "data" / "insight_config.json"
        # Иногда _base = logic_blocks, backend/data — на один уровень выше
        if not insight_path.exists():
            insight_path = self._base.parent / "data" / "insight_config.json"
        if not insight_path.exists():
            # Ищем рядом с logic_blocks
            insight_path = self._base.parent.parent / "backend" / "data" / "insight_config.json"

        src = (traffic_source or "").strip()
        if insight_path.exists():
            try:
                with open(insight_path, "r", encoding="utf-8") as f:
                    insight_data = json.load(f)

                # Ищем конфиг для источника (case-insensitive)
                source_config = None
                if src:
                    if src in insight_data:
                        source_config = insight_data[src]
                    else:
                        for key, val in insight_data.items():
                            if key.lower() == src.lower():
                                source_config = val
                                break

                if source_config and "parameter_weights" in source_config:
                    weights = source_config["parameter_weights"]
                    # Берём только колонки с weight > 0, сортируем по убыванию веса
                    active = [
                        (col, w) for col, w in weights.items()
                        if w > 0 and col in _ALLOWED_SEGMENT_COLS
                    ]
                    active.sort(key=lambda x: x[1], reverse=True)
                    return [col for col, _ in active]
            except (json.JSONDecodeError, IOError, TypeError):
                pass

        # --- 2. Фолбэк: segment_config.json ---
        path = self._base / "segment_config.json\""""

replacement = """    def get_decision_history(self, limit: int = 100) -> List[Dict]:
        \"\"\"Получить историю решений (заглушка).\"\"\"
        return []

"""

# Let's write a smarter regex based replacement
import re
content = re.sub(r'    def get_decision_history\(self, limit: int = 100\) -> List\[Dict\]:\n        """Получит.*?# --- 2\. Фолбэк: segment_config\.json ---', '    def get_decision_history(self, limit: int = 100) -> List[Dict]:\n        """Получить историю решений."""\n        return []\n\n        # --- 2. Фолбэк: segment_config.json ---', content, flags=re.DOTALL)

with codecs.open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
