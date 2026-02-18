#!/usr/bin/env python3
"""
Упрощенная миграция JSON-конфигов в Python-блоки.
"""
import json
import os
import re
from pathlib import Path


def create_simple_block(json_path: str, output_dir: str) -> str:
    """Создать простой Python блок из JSON."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    filename = os.path.basename(json_path)
    block_name = os.path.splitext(filename)[0]
    
    # Определяем категорию
    if '01_Rules' in json_path:
        category = 'rules'
    elif '02_Patterns' in json_path:
        category = 'patterns'
    elif '05_Learning' in json_path:
        category = 'learning'
    else:
        category = 'general'
    
    # Имя класса
    class_name = ''.join(word.capitalize() for word in re.split(r'[_\s]+', block_name))
    class_name = f"{class_name}Block"
    
    # JSON как строка
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    
    # Простой шаблон без сложных f-строк
    template = f'''"""
{block_name} - мигрированный блок из JSON.
"""

from typing import Dict, List, Optional, Any
from backend.brain.knowledge_base_v2_complete import KnowledgeBlock
import json


class {class_name}(KnowledgeBlock):
    """Блок знаний из {filename}"""
    
    def __init__(self):
        super().__init__(
            name="{block_name}",
            description="Блок знаний из {filename}",
            weight=1.0,
            category="{category}"
        )
        self.json_data = json.loads("""{json_str}""")
    
    def analyze(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        roi = campaign_data.get("roi", 0)
        profit = campaign_data.get("profit", 0)
        spend = campaign_data.get("spend", 0)
        clicks = campaign_data.get("clicks", 0)
        conversions = campaign_data.get("conversions", 0)
        volatility = campaign_data.get("volatility", 0)
        
        verdict = "HOLD"
        confidence = 50.0
        reasoning = []
        
        try:
            # Простая логика на основе JSON данных
            if "killer_rules" in self.json_data:
                killer = self.json_data["killer_rules"]
                if roi < killer.get("roi_threshold", -20):
                    verdict = "STOP"
                    confidence = 80.0
                    reasoning.append(f"ROI ниже порога")
            
            if "scaler_rules" in self.json_data:
                scaler = self.json_data["scaler_rules"]
                if roi > scaler.get("min_roi", 30) and conversions >= scaler.get("min_conversions", 3):
                    verdict = "SCALE"
                    confidence = 75.0
                    reasoning.append(f"Хороший ROI и конверсии")
            
            if "optimizer_rules" in self.json_data:
                optimizer = self.json_data["optimizer_rules"]
                epc = profit / clicks if clicks > 0 else 0
                if epc < optimizer.get("epc_threshold", 0.15):
                    verdict = "OPTIMIZE"
                    confidence = 70.0
                    reasoning.append(f"Низкий EPC")
            
            # Общая логика
            if not reasoning:
                if roi > 20:
                    verdict = "SCALE"
                    confidence = 60.0
                elif roi < -10:
                    verdict = "STOP"
                    confidence = 55.0
                elif -5 <= roi <= 15:
                    verdict = "HOLD"
                    confidence = 50.0
                else:
                    verdict = "OPTIMIZE"
                    confidence = 45.0
                    
        except Exception as e:
            verdict = "HOLD"
            confidence = 30.0
            reasoning.append(f"Ошибка: {{str(e)}}")
        
        return {{
            "verdict": verdict,
            "confidence": min(100.0, max(0.0, confidence)),
            "reasoning": reasoning,
            "block_name": self.name
        }}
    
    def get_config_summary(self) -> Dict[str, Any]:
        return {{
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "category": self.category,
            "source_file": "{filename}"
        }}


def register_block():
    return {class_name}()
'''
    
    # Сохраняем
    migrated_dir = os.path.join(output_dir, "migrated_blocks")
    os.makedirs(migrated_dir, exist_ok=True)
    
    output_path = os.path.join(migrated_dir, f"{block_name}.py")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(template)
    
    return output_path


def main():
    print("Упрощенная миграция JSON блоков")
    print("=" * 50)
    
    base_dir = Path("logic_blocks")
    json_files = []
    
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.json') and file not in ['blocks_registry.json', 'segment_config.json']:
                json_files.append(os.path.join(root, file))
    
    print(f"Найдено {len(json_files)} JSON файлов")
    
    for json_file in json_files:
        try:
            output = create_simple_block(json_file, "logic_blocks")
            print(f"✓ Создан: {os.path.basename(output)}")
        except Exception as e:
            print(f"✗ Ошибка {os.path.basename(json_file)}: {{e}}")
    
    # Создаем __init__.py
    init_content = '''"""
Мигрированные блоки.
"""

import importlib.util
import sys
from pathlib import Path


def load_migrated_blocks():
    blocks_dir = Path(__file__).parent
    blocks = []
    
    for py_file in blocks_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        try:
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec is None:
                continue
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[py_file.stem] = module
            spec.loader.exec_module(module)
            
            if hasattr(module, "register_block"):
                blocks.append(module.register_block)
                print(f"Загружен блок: {py_file.stem}")
        except Exception as e:
            print(f"Ошибка загрузки {py_file.name}: {e}")
    
    return blocks
'''
    
    init_path = Path("logic_blocks/migrated_blocks/__init__.py")
    with open(init_path, 'w', encoding='utf-8') as f:
        f.write(init_content)
    
    print(f"\\nСоздан {init_path}")
    print("\\nМиграция завершена!")


if __name__ == "__main__":
    main()