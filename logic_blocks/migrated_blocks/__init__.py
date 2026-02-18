"""
Модуль мигрированных блоков знаний.
Содержит блоки, мигрированные из JSON конфигов.
"""
import sys
import os
from pathlib import Path

# Добавляем путь к backend для импорта KnowledgeBlock
backend_path = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from backend.brain.knowledge_base_v2_complete import KnowledgeBlock

__all__ = ['KnowledgeBlock', 'load_migrated_blocks']


def load_migrated_blocks():
    """
    Загрузить все мигрированные блоки.
    Возвращает список функций для регистрации блоков.
    """
    import importlib.util
    import inspect
    
    blocks_dir = Path(__file__).parent
    register_functions = []
    
    for py_file in blocks_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        try:
            # Динамически импортируем модуль
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec is None:
                continue
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[py_file.stem] = module
            spec.loader.exec_module(module)
            
            # Ищем функцию регистрации блока
            if hasattr(module, 'register_block'):
                register_functions.append(module.register_block)
            else:
                # Ищем класс KnowledgeBlock
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        not name.startswith('_') and
                        hasattr(obj, 'analyze') and
                        hasattr(obj, 'name')):
                        
                        # Создаем функцию регистрации
                        def create_register_func(cls=obj):
                            def register():
                                return cls()
                            return register
                            
                        register_functions.append(create_register_func())
                        break
                        
        except Exception as e:
            print(f"Error loading migrated block {py_file.name}: {e}")
            
    return register_functions