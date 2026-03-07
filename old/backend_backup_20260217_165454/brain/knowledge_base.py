"""
KnowledgeBase — абстракция над Logic_Blocks.
Сканирует папку logic_blocks, загружает JSON, предоставляет единый API.
При добавлении/изменении файлов в Logic_Blocks меняется только эта реализация.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Путь к logic_blocks относительно корня проекта
_LOGIC_BLOCKS_ROOT = Path(__file__).resolve().parent.parent.parent / "logic_blocks"

# Fallback правила если файлы не найдены
_DEFAULT_CORE_RULES = {
    "killer_rules": {
        "min_spend_multiplier": 2.0,
        "zero_conversions": True,
        "roi_threshold": -20,
    },
    "scaler_rules": {
        "min_roi": 30,
        "min_conversions": 3,
        "stable_days": 3,
    },
    "optimizer_rules": {"epc_threshold": 0.15, "cpa_max": 5.0, "cr_min": 1.5},
    "zacep_rules": {"min_conversions": 3, "min_stability_days": 2},
}


class KnowledgeBase:
    """Единая точка входа к знаниям Logic_Blocks."""

    def __init__(self, base_path: Optional[Path] = None):
        self._base = base_path or _LOGIC_BLOCKS_ROOT
        self._cache: Dict[str, Any] = {}

    def _load_json(self, *parts: str) -> Any:
        """Загружает JSON из logic_blocks/parts[0]/parts[1]/..."""
        path = self._base.joinpath(*parts)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _load_json_cached(self, cache_key: str, *parts: str, default: Any = None) -> Any:
        if cache_key not in self._cache:
            data = self._load_json(*parts)
            self._cache[cache_key] = data if data is not None else default
        return self._cache[cache_key]

    # --- Rules ---

    def get_core_rules(self) -> Dict[str, Any]:
        """Правила из 01_Rules/core_rules.json."""
        rules = self._load_json_cached("core_rules", "01_Rules", "core_rules.json")
        return rules if rules else _DEFAULT_CORE_RULES

    def get_killer_rules(self) -> Dict[str, Any]:
        """Killer rules: min_spend_multiplier, zero_conversions, roi_threshold."""
        core = self.get_core_rules()
        return core.get("killer_rules", _DEFAULT_CORE_RULES["killer_rules"])

    def get_scaler_rules(self) -> Dict[str, Any]:
        """Scaler rules: min_roi, min_conversions, stable_days."""
        core = self.get_core_rules()
        return core.get("scaler_rules", _DEFAULT_CORE_RULES["scaler_rules"])

    def get_zacep_rules(self) -> Dict[str, Any]:
        """Зацеп rules: min_conversions, min_stability_days."""
        core = self.get_core_rules()
        return core.get("zacep_rules", _DEFAULT_CORE_RULES["zacep_rules"])

    # --- Patterns ---

    def get_winning_combos(self) -> List[Dict[str, Any]]:
        """Паттерны победных связок из 02_Patterns/winning_combos.json."""
        data = self._load_json_cached("winning_combos", "02_Patterns", "winning_combos.json", default=[])
        return data if isinstance(data, list) else []

    def get_killer_patterns(self) -> List[Dict[str, Any]]:
        """Паттерны киллеров из 02_Patterns/killer_patterns.json."""
        data = self._load_json_cached("killer_patterns", "02_Patterns", "killer_patterns.json", default=[])
        return data if isinstance(data, list) else []

    def get_trend_analysis(self) -> Dict[str, Any]:
        """Трендовый анализ из 02_Patterns/trend_analysis.json."""
        data = self._load_json_cached("trend_analysis", "02_Patterns", "trend_analysis.json", default={})
        return data if isinstance(data, dict) else {}

    # --- Segment config (какие колонки анализировать по traffic source) ---

    def get_segment_columns(self, traffic_source: Optional[str] = None) -> List[str]:
        """
        Список колонок для сегментного анализа.
        Для traffic_source ищет конфиг, иначе default.
        """
        path = self._base / "segment_config.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, TypeError):
            data = None
        if not data or not isinstance(data, dict):
            return ["os", "device_type", "token2", "offer", "lander_id", "country"]
        # Ищем по точному имени или по части (Approach X, Affmy, etc.)
        src = (traffic_source or "").strip()
        if src and src in data:
            cols = data[src]
        else:
            cols = data.get("default", ["os", "device_type", "token2", "offer", "lander_id", "country"])
        return cols if isinstance(cols, list) else list(cols)

    def get_segment_config_raw(self) -> Dict[str, Any]:
        """Полный конфиг segment_config.json (для настроек)."""
        path = self._base / "segment_config.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, TypeError):
            return {"default": ["os", "device_type", "token2", "offer", "lander_id", "country"]}

    # --- Model weights (learning) ---

    def get_model_weights(self) -> Dict[str, Any]:
        """Веса модели из 05_Learning/model_weights.json."""
        data = self._load_json_cached("model_weights", "05_Learning", "model_weights.json", default={})
        return data if isinstance(data, dict) else {}

    # --- Invalidate cache (при обновлении Logic_Blocks) ---

    def invalidate_cache(self, key: Optional[str] = None) -> None:
        """Сброс кэша (всего или по ключу)."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()
