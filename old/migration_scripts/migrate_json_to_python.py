#!/usr/bin/env python3
"""
Миграция JSON-конфигов в Python-блоки для KnowledgeBaseV2.
Преобразует существующие JSON файлы в Python классы блоков знаний.
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any


def create_python_block_from_json(json_path: str, output_dir: str) -> str:
    """
    Создать Python блок из JSON конфига.
    
    Args:
        json_path: Путь к JSON файлу
        output_dir: Директория для сохранения Python блоков
    
    Returns:
        Имя созданного файла
    """
    # Читаем JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Определяем тип блока по имени файла
    filename = os.path.basename(json_path)
    block_name = os.path.splitext(filename)[0]
    
    # Определяем категорию по пути
    if '01_Rules' in json_path:
        category = 'rules'
        block_type = 'rule'
    elif '02_Patterns' in json_path:
        category = 'patterns'
        block_type = 'pattern'
    elif '05_Learning' in json_path:
        category = 'learning'
        block_type = 'learning'
    else:
        category = 'general'
        block_type = 'general'
    
    # Создаем имя класса
    class_name = ''.join(word.capitalize() for word in re.split(r'[_\s]+', block_name))
    class_name = f"{class_name}Block"
    
    # Создаем описание
    description = f"Блок знаний из {filename}"
    
    # Безопасно сериализуем данные для вставки в код
    import json as json_module
    json_data_str = json_module.dumps(data, ensure_ascii=False, indent=2)
    # Экранируем тройные кавычки
    json_data_str = json_data_str.replace('"""', '\\"\\"\\"')
    
    # Создаем код блока
    python_code = f'''"""
{block_name} - мигрированный блок из JSON конфига.
Категория: {category}
Тип: {block_type}
"""

from typing import Dict, List, Optional, Any
from backend.brain.knowledge_base_v2_complete import KnowledgeBlock
import json


class {class_name}(KnowledgeBlock):
    """{description}"""
    
    def __init__(self):
        super().__init__(
            name="{block_name}",
            description="{description}",
            weight=1.0,
            category="{category}"
        )
        # Сохраняем исходные данные
        self.json_data = json.loads(\"\"\"{json_data_str}\"\"\")
    
    def analyze(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализировать кампанию на основе правил из JSON.
        
        Args:
            campaign_data: Данные кампании
        
        Returns:
            Словарь с вердиктом и уверенностью
        """
        roi = campaign_data.get("roi", 0)
        profit = campaign_data.get("profit", 0)
        spend = campaign_data.get("spend", 0)
        clicks = campaign_data.get("clicks", 0)
        conversions = campaign_data.get("conversions", 0)
        volatility = campaign_data.get("volatility", 0)
        
        # Инициализируем результат
        verdict = "HOLD"
        confidence = 50.0
        reasoning = []
        
        # Применяем правила из JSON
        try:
            # Правила для killer_rules
            if "killer_rules" in self.json_data:
                killer = self.json_data["killer_rules"]
                if spend > 0 and conversions == 0 and spend >= 2.0 * (spend / max(1, clicks)):
                    # Потратили 2x payout без конверсий
                    verdict = "STOP"
                    confidence = 85.0
                    reasoning.append("Потратили 2x payout без конверсий")
                elif roi < killer.get("roi_threshold", -20):
                    verdict = "STOP"
                    confidence = 80.0
                    reasoning.append(f"ROI ({roi:.1f}%) ниже порога {killer.get('roi_threshold', -20)}%")
            
            # Правила для scaler_rules
            if "scaler_rules" in self.json_data:
                scaler = self.json_data["scaler_rules"]
                if (roi > scaler.get("min_roi", 30) and 
                    conversions >= scaler.get("min_conversions", 3)):
                    verdict = "SCALE"
                    confidence = 75.0
                    reasoning.append(f"ROI ({roi:.1f}%) выше порога {scaler.get('min_roi', 30)}% с {conversions} конверсиями")
            
            # Правила для optimizer_rules
            if "optimizer_rules" in self.json_data:
                optimizer = self.json_data["optimizer_rules"]
                epc = profit / clicks if clicks > 0 else 0
                cpa = spend / conversions if conversions > 0 else 0
                
                if epc < optimizer.get("epc_threshold", 0.15):
                    verdict = "OPTIMIZE"
                    confidence = 70.0
                    reasoning.append(f"EPC ({epc:.3f}) ниже порога {optimizer.get('epc_threshold', 0.15)}")
                elif conversions > 0 and cpa > optimizer.get("cpa_max", 5.0):
                    verdict = "OPTIMIZE"
                    confidence = 65.0
                    reasoning.append(f"CPA ({cpa:.2f}) выше порога {optimizer.get('cpa_max', 5.0)}")
            
            # Правила для zacep_rules
            if "zacep_rules" in self.json_data:
                zacep = self.json_data["zacep_rules"]
                if conversions >= zacep.get("min_conversions", 3):
                    verdict = "SCALE"
                    confidence = 60.0
                    reasoning.append(f"Найдено {conversions} конверсий - зацеп для скейла")
            
            # Общие правила для patterns
            if "patterns" in self.json_data:
                patterns = self.json_data["patterns"]
                for pattern_name, pattern_rules in patterns.items():
                    if isinstance(pattern_rules, dict):
                        # Проверяем условия паттерна
                        conditions_met = 0
                        total_conditions = 0
                        
                        if "min_roi" in pattern_rules and roi >= pattern_rules["min_roi"]:
                            conditions_met += 1
                        total_conditions += 1 if "min_roi" in pattern_rules else 0
                        
                        if "min_conversions" in pattern_rules and conversions >= pattern_rules["min_conversions"]:
                            conditions_met += 1
                        total_conditions += 1 if "min_conversions" in pattern_rules else 0
                        
                        if "max_volatility" in pattern_rules and volatility <= pattern_rules["max_volatility"]:
                            conditions_met += 1
                        total_conditions += 1 if "max_volatility" in pattern_rules else 0
                        
                        if total_conditions > 0 and conditions_met == total_conditions:
                            # Все условия выполнены
                            if pattern_name.lower().find("scale") != -1 or pattern_name.lower().find("winning") != -1:
                                verdict = "SCALE"
                                confidence = max(confidence, 70.0)
                                reasoning.append(f"Паттерн '{pattern_name}' обнаружен")
                            elif pattern_name.lower().find("stop") != -1 or pattern_name.lower().find("killer") != -1:
                                verdict = "STOP"
                                confidence = max(confidence, 70.0)
                                reasoning.append(f"Паттерн '{pattern_name}' обнаружен")
            
            # Если нет конкретных правил, используем общую логику
            if not reasoning:
                if roi > 20:
                    verdict = "SCALE"
                    confidence = 60.0
                    reasoning.append(f"Высокий ROI: {roi:.1f}%")
                elif roi < -10:
                    verdict = "STOP"
                    confidence = 55.0
                    reasoning.append(f"Отрицательный ROI: {roi:.1f}%")
                elif -5 <= roi <= 15:
                    verdict = "HOLD"
                    confidence = 50.0
                    reasoning.append(f"Стабильный ROI: {roi:.1f}%")
                else:
                    verdict = "OPTIMIZE"
                    confidence = 45.0
                    reasoning.append(f"ROI требует оптимизации: {roi:.1f}%")
                    
        except Exception as e:
            # В случае ошибки возвращаем консервативный вердикт
            verdict = "HOLD"
            confidence = 30.0
            reasoning.append(f"Ошибка анализа: {str(e)}")
        
        return {{
            "verdict": verdict,
            "confidence": min(100.0, max(0.0, confidence)),
            "reasoning": reasoning,
            "block_name": self.name
        }}
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Получить сводку конфигурации блока."""
        return {{
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "category": self.category,
            "source_file": "{filename}",
            "json_data_keys": list(self.json_data.keys()) if isinstance(self.json_data, dict) else []
        }}


# Функция для регистрации блока
def register_block():
    """Функция для регистрации блока в KnowledgeBaseV2."""
    return {class_name}()


if __name__ == "__main__":
    # Тестирование блока
    block = {class_name}()
    print(f"Блок создан: {{block.name}}")
    print(f"Описание: {{block.description}}")
    print(f"Категория: {{block.category}}")
    print(f"Вес: {{block.weight}}")
    
    # Тестовые данные
    test_data = {{
        "roi": 35.5,
        "profit": 150.0,
        "spend": 100.0,
        "clicks": 1000,
        "conversions": 5,
        "volatility": 15.0
    }}
    
    result = block.analyze(test_data)
    print(f"\\nТестовый анализ:")
    print(f"Вердикт: {{result['verdict']}}")
    print(f"Уверенность: {{result['confidence']:.1f}}%")
    print(f"Обоснование: {{', '.join(result['reasoning'])}}")
'''
    
    # Создаем директорию для мигрированных блоков
    migrated_dir = os.path.join(output_dir, "migrated_blocks")
    os.makedirs(migrated_dir, exist_ok=True)
    
    # Сохраняем файл
    output_path = os.path.join(migrated_dir, f"{block_name}.py")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(python_code)
    
    return output_path


def migrate_all_json_blocks():
    """Мигрировать все JSON блоки в Python."""
    base_dir = Path("logic_blocks")
    output_dir = Path("logic_blocks")
    
    # Находим все JSON файлы
    json_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.json') and file != 'blocks_registry.json' and file != 'segment_config.json':
                json_files.append(os.path.join(root, file))
    
    print(f"Найдено {len(json_files)} JSON файлов для миграции:")
    
    migrated_files = []
    for json_file in json_files:
        try:
            output_file = create_python_block_from_json(json_file, str(output_dir))
            migrated_files.append(output_file)
            print(f"  ✓ {os.path.basename(json_file)} -> {os.path.basename(output_file)}")
        except Exception as e:
            print(f"  ✗ Ошибка миграции {json_file}: {e}")
    
    # Создаем файл регистрации мигрированных блоков
    create_registry_file(migrated_files, output_dir)
    
    return migrated_files


def create_registry_file(migrated_files: List[str], output_dir: Path):
    """Создать файл регистрации мигрированных блоков."""
    registry_content = '''"""
Реестр мигрированных блоков знаний.
Автоматически сгенерирован при миграции JSON -> Python.
"""

import importlib.util
import sys
from pathlib import Path
from typing import List, Dict, Any


def load_migrated_blocks() -> List[Dict[str, Any]]:
    """
    Загрузить все мигрированные блоки.
    
    Returns:
        Список функций регистрации блоков
    """
    blocks_dir = Path(__file__).parent / "migrated_blocks"
    if not blocks_dir.exists():
        return []
    
    blocks = []
    
    for py_file in blocks_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        try:
            # Динамически импортируем модуль
            module_name = f"migrated_blocks.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Получаем функцию регистрации
            if hasattr(module, "register_block"):
                blocks.append({
                    "module": module_name,
                    "register_function": module.register_block,
                    "file": str(py_file)
                })
                print(f"✓ Загружен мигрированный блок: {py_file.stem}")
            else:
                print(f"✗ Блок {py_file.stem} не имеет функции register_block")
                
        except Exception as e:
            print(f"✗ Ошибка загрузки блока {py_file.name}: {e}")
    
    return blocks


def get_migrated_blocks_info() -> List[Dict[str, Any]]:
    """
    Получить информацию о мигрированных блоках.
    
    Returns:
        Список информации о блоках
    """
    blocks = load_migrated_blocks()
    info = []
    
    for block_data in blocks:
        try:
            block = block_data["register_function"]()
            info.append({
                "name": block.name,
                "description": block.description,
                "category": block.category,
                "weight": block.weight,
                "source_file": block_data["file"]
            })
        except Exception as e:
            print(f"Ошибка получения информации о блоке: {e}")
    
    return info


if __name__ == "__main__":
    # Тестирование загрузки блоков
    print("Тестирование загрузки мигрированных блоков...")
    blocks = load_migrated_blocks()
    print(f"Загружено блоков: {len(blocks)}")
    
    if blocks:
        print("\\nИнформация о блоках:")
        for block_info in get_migrated_blocks_info():
            print(f"  • {block_info['name']} ({block_info['category']}): {block_info['description']}")
'''
    
    registry_path = output_dir / "migrated_blocks" / "__init__.py"
    registry_path.parent.mkdir(exist_ok=True)
    
    with open(registry_path, 'w', encoding='utf-8') as f:
        f.write(registry_content)
    
    print(f"\\nСоздан файл регистрации: {registry_path}")


def update_knowledge_base_to_use_migrated():
    """Обновить KnowledgeBaseV2 для использования мигрированных блоков."""
    # Читаем текущий knowledge_base_v2_complete.py
    kb_path = Path("backend/brain/knowledge_base_v2_complete.py")
    if not kb_path.exists():
        print("Файл knowledge_base_v2_complete.py не найден")
        return
    
    with open(kb_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Находим метод load_blocks_from_directory
    if "def load_blocks_from_directory" in content:
        # Добавляем импорт мигрированных блоков
        if "from logic_blocks.migrated_blocks import load_migrated_blocks" not in content:
            # Находим место для импорта
            import_section = "from typing import Dict, List, Optional, Any"
            if import_section in content:
                new_import = f'{import_section}\nfrom logic_blocks.migrated_blocks import load_migrated_blocks'
                content = content.replace(import_section, new_import)
        
        # Находим метод load_blocks_from_directory и добавляем загрузку мигрированных блоков
        method_start = "def load_blocks_from_directory"
        method_end = "def load_blocks_from_my_knowledge"
        
        if method_start in content and method_end in content:
            start_idx = content.find(method_start)
            end_idx = content.find(method_end, start_idx)
            
            if start_idx != -1 and end_idx != -1:
                method_content = content[start_idx:end_idx]
                
                # Добавляем загрузку мигрированных блоков в конец метода
                if "# Load migrated JSON blocks" not in method_content:
                    new_section = '''
        # Load migrated JSON blocks
        try:
            migrated_blocks = load_migrated_blocks()
            for block_data in migrated_blocks:
                try:
                    block = block_data["register_function"]()
                    self.blocks.append(block)
                    print(f"✓ Загружен мигрированный блок: {{block.name}}")
                except Exception as e:
                    print(f"✗ Ошибка загрузки мигрированного блока: {{e}}")
        except Exception as e:
            print(f"✗ Ошибка загрузки мигрированных блоков: {{e}}")
'''
                    
                    # Вставляем новую секцию перед концом метода
                    insert_pos = method_content.rfind("print(f\"✓ Загружено {len(self.blocks)} блоков знаний\")")
                    if insert_pos != -1:
                        new_method_content = method_content[:insert_pos] + new_section + method_content[insert_pos:]
                        content = content[:start_idx] + new_method_content + content[end_idx:]
        
        # Сохраняем обновленный файл
        with open(kb_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ Обновлен {kb_path} для использования мигрированных блоков")
    
    else:
        print("✗ Не найден метод load_blocks_from_directory в knowledge_base_v2_complete.py")


def main():
    """Основная функция миграции."""
    print("=" * 60)
    print("МИГРАЦИЯ JSON КОНФИГОВ В PYTHON БЛОКИ")
    print("=" * 60)
    
    # Мигрируем все JSON блоки
    migrated_files = migrate_all_json_blocks()
    
    if migrated_files:
        print(f"\\n✓ Успешно мигрировано {len(migrated_files)} блоков")
        
        # Обновляем KnowledgeBaseV2
        update_knowledge_base_to_use_migrated()
        
        print("\\n" + "=" * 60)
        print("МИГРАЦИЯ ЗАВЕРШЕНА")
        print("=" * 60)
        print("\\nСледующие шаги:")
        print("1. Запустите тестирование системы: python test_v2_system.py")
        print("2. Проверьте загрузку блоков в KnowledgeBaseV2")
        print("3. Обновите веса блоков при необходимости")
        print("4. Протестируйте анализ кампаний с новыми блоками")
    else:
        print("\\n✗ Не удалось мигрировать блоки")
    
    return len(migrated_files) > 0


if __name__ == "__main__":
    main()
