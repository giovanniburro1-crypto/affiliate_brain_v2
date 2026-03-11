import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "insight_config.json")

DEFAULT_TEMPLATE = {
    "parameter_weights": {
        "token1": 1,
        "token2": 1,
        "token3": 1,
        "token4": 2,
        "token5": 2,
        "token6": 0,
        "token7": 0,
        "token8": 0,
        "token9": 0,
        "token10": 0,
        "offer": 1,
        "lander_id": 1,
        "os": 2,
        "device_type": 2,
        "browser_name": 0,
        "country": 2,
        "language": 2,
        "rule": 2,
        "path": 2,
        "campaign": 0,
        "traffic_source": 0
    },
    "thresholds": {
        "scale_min_roi": 20,
        "scale_min_conversions": 3,
        "scale_min_profit": 5,
        "kill_min_spend": 20,
        "kill_max_roi": -40
    }
}

def get_all_configs():
    if not os.path.exists(CONFIG_PATH):
        # Create default generic config
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        default_data = {"default": DEFAULT_TEMPLATE}
        with open(CONFIG_PATH, "w") as f:
            json.dump(default_data, f, indent=4)
        return default_data
    
    with open(CONFIG_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"default": DEFAULT_TEMPLATE}

def get_config_for_source(source_name: str):
    configs = get_all_configs()
    # Normalize source name (case insensitive matching if possible, or exact)
    # If source_name doesn't exist, fallback to "default"
    if source_name in configs:
        return configs[source_name]
    
    # Try case-insensitive
    for key, val in configs.items():
        if key.lower() == source_name.lower():
            return val
            
    return configs.get("default", DEFAULT_TEMPLATE)

def save_config_for_source(source_name: str, config_data: dict):
    configs = get_all_configs()
    
    # Validate the structure has parameter_weights and thresholds
    if "parameter_weights" not in config_data:
        config_data["parameter_weights"] = DEFAULT_TEMPLATE["parameter_weights"].copy()
    if "thresholds" not in config_data:
        config_data["thresholds"] = DEFAULT_TEMPLATE["thresholds"].copy()
        
    configs[source_name] = config_data
    with open(CONFIG_PATH, "w") as f:
        json.dump(configs, f, indent=4)
    return configs

def delete_config_for_source(source_name: str):
    if source_name == "default":
        raise ValueError("Cannot delete the default template")
    configs = get_all_configs()
    if source_name in configs:
        del configs[source_name]
        with open(CONFIG_PATH, "w") as f:
            json.dump(configs, f, indent=4)
    return configs
