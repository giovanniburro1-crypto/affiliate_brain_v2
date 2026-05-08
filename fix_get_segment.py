import json
import codecs

file_path = "/Users/andreylp/affiliate_brain/app/backend/brain/knowledge_base_v2_complete.py"

with codecs.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

target = """    def get_segment_columns(self, traffic_source: Optional[str] = None) -> List[str]:
        \"\"\"
        Список колонок для сегментного анализа.
        Для traffic_source ищет конфиг, иначе default.
        \"\"\"
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
        return cols if isinstance(cols, list) else list(cols)"""

replacement = """    def get_segment_columns(self, traffic_source: Optional[str] = None) -> List[str]:
        \"\"\"
        Список колонок для сегментного анализа.
        Приоритет: insight_config.json (weight > 0) -> segment_config.json
        \"\"\"
        import os
        from pathlib import Path
        
        insight_path = Path(__file__).parent.parent / "data" / "insight_config.json"
        insight_data = None
        if insight_path.exists():
            try:
                with open(insight_path, "r", encoding="utf-8") as f:
                    insight_data = json.load(f)
            except Exception:
                pass
                
        src = (traffic_source or "").strip().lower()
        
        if insight_data:
            source_key = "default"
            for k in insight_data.keys():
                if k.lower() == src:
                    source_key = k
                    break
            
            if source_key in insight_data and "parameter_weights" in insight_data[source_key]:
                weights = insight_data[source_key]["parameter_weights"]
                cols = [k for k, v in weights.items() if v > 0]
                cols.sort(key=lambda k: weights[k], reverse=True)
                if cols:
                    return cols

        path = self._base / "segment_config.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, TypeError):
            data = None
        if not data or not isinstance(data, dict):
            return ["os", "device_type", "token2", "offer", "lander_id", "country"]
            
        src_orig = (traffic_source or "").strip()
        if src_orig and src_orig in data:
            cols = data[src_orig]
        else:
            cols = data.get("default", ["os", "device_type", "token2", "offer", "lander_id", "country"])
        return cols if isinstance(cols, list) else list(cols)"""

if target in content:
    content = content.replace(target, replacement)
    with codecs.open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully replaced.")
else:
    print("Target not found.")
