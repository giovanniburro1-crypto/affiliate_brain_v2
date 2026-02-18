"""
KnowledgeBaseV2 — расширенная система знаний с динамической загрузкой блоков,
системой голосования и автоматическим обучением на основе решений пользователя.
Совместимость с оригинальным KnowledgeBase для обратной совместимости.
"""
import json
import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
import sys
import importlib.util

_LOGIC_BLOCKS_ROOT = Path(__file__).resolve().parent.parent.parent / "logic_blocks"
_MY_KNOWLEDGE_PATH = _LOGIC_BLOCKS_ROOT / "my_knowledge"

# Добавляем путь к my_knowledge в sys.path для динамического импорта
if str(_MY_KNOWLEDGE_PATH) not in sys.path:
    sys.path.insert(0, str(_MY_KNOWLEDGE_PATH))

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

class KnowledgeBlock:
    """Базовый класс для блоков знаний."""
    
    def __init__(self, name: str, description: str = "", weight: float = 1.0, category: str = "general"):
        self.name = name
        self.description = description
        self.weight = weight
        self.category = category
        
    def analyze(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Анализировать кампанию. Должен быть переопределен в подклассах."""
        raise NotImplementedError("Subclasses must implement analyze method")
        
    def get_config_summary(self) -> Dict[str, Any]:
        """Получить сводку конфигурации блока."""
        return {
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "category": self.category
        }


class BlockVote:
    """Голос одного блока знаний."""
    
    def __init__(self, block_name: str, verdict: str, confidence: float, reason: str, weight: float = 1.0):
        self.block_name = block_name
        self.verdict = verdict.upper()  # SCALE, HOLD, STOP, OPTIMIZE
        self.confidence = max(0.0, min(1.0, confidence))  # 0.0-1.0
        self.reason = reason
        self.weight = max(0.1, min(3.0, weight))  # Вес блока (0.1-3.0)
        
    def weighted_score(self) -> float:
        """Взвешенная оценка голоса."""
        return self.confidence * self.weight
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_name": self.block_name,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reason": self.reason,
            "weight": self.weight,
            "weighted_score": self.weighted_score()
        }

class BlockMetadata:
    """Метаданные блока знаний."""
    
    def __init__(self, block_id: str, class_name: str, file_path: str, 
                 description: str = "", priority: int = 5, enabled: bool = True):
        self.block_id = block_id
        self.class_name = class_name
        self.file_path = file_path
        self.description = description
        self.priority = priority  # 1-10, где 10 - высший приоритет
        self.enabled = enabled
        self.weight = 1.0  # Начальный вес
        self.accuracy_history = []  # История точности решений
        self.last_used = None
        
    def update_weight(self, was_correct: bool, learning_rate: float = 0.1):
        """Обновить вес блока на основе правильности решения."""
        if was_correct:
            self.weight = min(3.0, self.weight + learning_rate)
        else:
            self.weight = max(0.1, self.weight - learning_rate)
            
    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "class_name": self.class_name,
            "description": self.description,
            "priority": self.priority,
            "enabled": self.enabled,
            "weight": self.weight,
            "accuracy_history": self.accuracy_history,
            "last_used": self.last_used.isoformat() if self.last_used else None
        }

class KnowledgeBaseV2:
    """Единая точка входа к знаниям с системой голосования и обучения."""
    
    def __init__(self, base_path: Optional[Path] = None):
        self._base = base_path or _LOGIC_BLOCKS_ROOT
        self._my_knowledge_path = self._base / "my_knowledge"
        self._blocks_metadata: Dict[str, BlockMetadata] = {}
        self._loaded_classes: Dict[str, Any] = {}
        self._decision_history: List[Dict] = []
        self._cache: Dict[str, Any] = {}
        
        # Добавляем пути для импорта модулей
        if str(self._base) not in sys.path:
            sys.path.insert(0, str(self._base))
        
        # Загружаем метаданные блоков
        self._load_blocks_metadata()
        
        # Загружаем классы блоков
        self._load_all_blocks()
        
        # Для обратной совместимости
        self.blocks = self._loaded_classes
        
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
        
    def _load_blocks_metadata(self):
        """Загрузить или создать метаданные блоков."""
        metadata_path = self._base / "blocks_registry.json"
        
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for block_id, block_data in data.items():
                    metadata = BlockMetadata(
                        block_id=block_id,
                        class_name=block_data.get('class_name', ''),
                        file_path=block_data.get('file_path', ''),
                        description=block_data.get('description', ''),
                        priority=block_data.get('priority', 5),
                        enabled=block_data.get('enabled', True)
                    )
                    metadata.weight = block_data.get('weight', 1.0)
                    metadata.accuracy_history = block_data.get('accuracy_history', [])
                    
                    if block_data.get('last_used'):
                        metadata.last_used = datetime.fromisoformat(block_data['last_used'])
                        
                    self._blocks_metadata[block_id] = metadata
            except Exception as e:
                print(f"Error loading blocks metadata: {e}")
                self._blocks_metadata = {}
        else:
            # Создаем начальные метаданные
            self._scan_and_create_metadata()
            
    def _scan_and_create_metadata(self):
        """Сканировать папку my_knowledge и создать метаданные."""
        if not self._my_knowledge_path.exists():
            return
            
        for py_file in self._my_knowledge_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
                
            block_id = py_file.stem
            class_name = self._guess_class_name(block_id)
            
            metadata = BlockMetadata(
                block_id=block_id,
                class_name=class_name,
                file_path=str(py_file.relative_to(self._base)),
                description=f"Блок знаний из {py_file.name}",
                priority=5,
                enabled=True
            )
            
            self._blocks_metadata[block_id] = metadata
            
        # Сохраняем метаданные
        self._save_blocks_metadata()
        
    def _guess_class_name(self, block_id: str) -> str:
        """Угадать имя класса на основе имени файла."""
        # Преобразуем block_1_base в Block1Base или AffiliateKnowledgeBase
        parts = block_id.split('_')
        if len(parts) >= 3 and parts[0] == 'block':
            # Для block_X_name создаем BlockXName
            return f"Block{parts[1].capitalize()}{''.join(p.capitalize() for p in parts[2:])}"
        else:
            # Пробуем стандартные имена
            if 'base' in block_id:
                return "AffiliateKnowledgeBase"
            elif 'scale' in block_id:
                return "AffiliateExperimentsPhase5"
            elif 'crisis' in block_id:
                return "AffiliateBlacklistEngine"
            elif 'payouts' in block_id:
                return "AffiliatePayoutEnginePhase6"
            elif 'optimize' in block_id:
                return "AffiliateOptimizationEngine"
            elif 'volatility' in block_id:
                return "AffiliateVolatilityEngine"
            else:
                return f"{block_id.replace('_', '').capitalize()}Block"
                
    def _load_all_blocks(self):
        """Динамически загрузить все блоки знаний."""
        # Загружаем блоки с учетом их расположения
        for block_id, metadata in self._blocks_metadata.items():
            if not metadata.enabled:
                continue
                
            # Проверяем расположение файла
            file_path = metadata.file_path
            if file_path and file_path.startswith("migrated_blocks/"):
                # Этот блок будет загружен в _load_migrated_blocks
                continue
                
            # Блоки из my_knowledge или без указанного пути
            try:
                # Импортируем модуль
                module_name = metadata.block_id
                module = importlib.import_module(module_name)
                
                # Получаем класс
                cls = getattr(module, metadata.class_name, None)
                if cls is None:
                    # Пробуем найти класс по имени
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and not name.startswith('_'):
                            cls = obj
                            metadata.class_name = name
                            break
                
                if cls:
                    self._loaded_classes[block_id] = cls
                    print(f"Loaded block: {block_id} -> {metadata.class_name}")
                else:
                    print(f"Warning: No class found in {module_name}")
                    
            except Exception as e:
                # Не выводим ошибку для мигрированных блоков - они будут загружены позже
                if not (file_path and file_path.startswith("migrated_blocks/")):
                    print(f"Error loading block {block_id}: {e}")
        
        # Затем загружаем мигрированные блоки из JSON
        self._load_migrated_blocks()
        
    def _load_migrated_blocks(self):
        """Загрузить мигрированные блоки из JSON конфигов."""
        migrated_dir = self._base / "migrated_blocks"
        if not migrated_dir.exists():
            print("No migrated blocks directory found")
            return
            
        # Пробуем импортировать модуль мигрированных блоков
        try:
            # Добавляем путь к migrated_blocks в sys.path
            migrated_path = str(migrated_dir.parent)
            if migrated_path not in sys.path:
                sys.path.insert(0, migrated_path)
            
            # Импортируем модуль мигрированных блоков
            import logic_blocks.migrated_blocks as migrated_module
            
            # Получаем функцию загрузки блоков
            if hasattr(migrated_module, 'load_migrated_blocks'):
                register_functions = migrated_module.load_migrated_blocks()
                
                for register_func in register_functions:
                    try:
                        # Регистрируем блок
                        block_instance = register_func()
                        block_id = block_instance.name
                        
                        # Добавляем в загруженные классы
                        self._loaded_classes[block_id] = type(block_instance)
                        
                        # Создаем метаданные если их нет
                        if block_id not in self._blocks_metadata:
                            metadata = BlockMetadata(
                                block_id=block_id,
                                class_name=type(block_instance).__name__,
                                file_path=f"migrated_blocks/{block_id}.py",
                                description=block_instance.description,
                                priority=5,
                                enabled=True
                            )
                            self._blocks_metadata[block_id] = metadata
                            
                        print(f"Loaded migrated block: {block_id}")
                        
                    except Exception as e:
                        print(f"Error loading migrated block: {e}")
                        
        except Exception as e:
            print(f"Error loading migrated blocks module: {e}")
            
        # Альтернативный способ: сканируем файлы напрямую
        for py_file in migrated_dir.glob("*.py"):
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
                
                # Ищем класс KnowledgeBlock
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        not name.startswith('_') and
                        hasattr(obj, 'analyze') and
                        hasattr(obj, 'name')):
                        
                        # Создаем экземпляр для получения информации
                        instance = obj()
                        block_id = instance.name
                        
                        # Добавляем в загруженные классы
                        self._loaded_classes[block_id] = obj
                        
                        # Создаем метаданные если их нет
                        if block_id not in self._blocks_metadata:
                            metadata = BlockMetadata(
                                block_id=block_id,
                                class_name=name,
                                file_path=str(py_file.relative_to(self._base)),
                                description=instance.description,
                                priority=5,
                                enabled=True
                            )
                            self._blocks_metadata[block_id] = metadata
                            
                        print(f"Loaded migrated block directly: {block_id}")
                        break
                        
            except Exception as e:
                print(f"Error loading migrated block {py_file.name}: {e}")
                
    def _save_blocks_metadata(self):
        """Сохранить метаданные блоков в файл."""
        metadata_path = self._base / "blocks_registry.json"
        
        data = {}
        for block_id, metadata in self._blocks_metadata.items():
            data[block_id] = {
                "block_id": metadata.block_id,
                "class_name": metadata.class_name,
                "file_path": metadata.file_path,
                "description": metadata.description,
                "priority": metadata.priority,
                "enabled": metadata.enabled,
                "weight": metadata.weight,
                "accuracy_history": metadata.accuracy_history,
                "last_used": metadata.last_used.isoformat() if metadata.last_used else None
            }
            
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving blocks metadata: {e}")
            
    def get_block_votes(self, campaign_data: Dict[str, Any]) -> List[BlockVote]:
        """Получить голоса от всех активных блоков для кампании."""
        votes = []
        
        for block_id, cls in self._loaded_classes.items():
            if block_id not in self._blocks_metadata:
                continue
                
            metadata = self._blocks_metadata[block_id]
            if not metadata.enabled:
                continue
                
            try:
                # Создаем экземпляр класса
                instance = cls()
                
                # Получаем голос от блока через адаптер
                vote = self._get_block_vote_adapter(instance, block_id, metadata, campaign_data)
                
                if vote:
                    votes.append(vote)
                    
                    # Обновляем время последнего использования
                    metadata.last_used = datetime.now()
                    
            except Exception as e:
                print(f"Error getting vote from block {block_id}: {e}")
                # Добавляем голос по умолчанию
                vote = BlockVote(
                    block_name=block_id,
                    verdict="HOLD",
                    confidence=0.5,
                    reason=f"Ошибка анализа: {str(e)}",
                    weight=metadata.weight
                )
                votes.append(vote)
                
        return votes
        
    def _get_block_vote_adapter(self, instance, block_id: str, metadata: BlockMetadata, 
                               campaign_data: Dict[str, Any]) -> Optional[BlockVote]:
        """Адаптер для получения голоса от блока с разными сигнатурами методов."""
        
        # Пробуем разные стратегии анализа в зависимости от типа блока
        if block_id == "block_1_base":
            # Блок 1: Анализ стоп-лосса и зацепов
            spend = campaign_data.get('spend', 0)
            payout = campaign_data.get('payout', 0)
            conversions = campaign_data.get('conversions', 0)
            
            try:
                result = instance.analyze_stop_loss(spend, payout, conversions)
                verdict = "STOP" if "STOP" in str(result.get('action', '')).upper() else "HOLD"
                reason = result.get('reason', '')
                confidence = 0.8 if verdict == "STOP" else 0.5
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
            except Exception as e:
                print(f"Error in block_1_base adapter: {e}")
                
        elif block_id == "block_2_optimize":
            # Блок 2: Оптимизация
            try:
                # Пробуем разные методы
                if hasattr(instance, 'optimize_bid'):
                    result = instance.optimize_bid(campaign_data)
                elif hasattr(instance, 'analyze_optimization'):
                    result = instance.analyze_optimization(campaign_data)
                else:
                    # По умолчанию
                    result = {"action": "OPTIMIZE", "reason": "Требуется оптимизация ставок"}
                    
                verdict = self._parse_verdict(result)
                confidence = self._parse_confidence(result)
                reason = self._parse_reason(result)
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
            except Exception as e:
                print(f"Error in block_2_optimize adapter: {e}")
                
        elif block_id == "block_3_crisis":
            # Блок 3: Кризис и черный список
            clicks = campaign_data.get('clicks', 0)
            roi = campaign_data.get('roi', 0)
            spend = campaign_data.get('spend', 0)
            
            try:
                if hasattr(instance, 'analyze_source_for_blacklist'):
                    result = instance.analyze_source_for_blacklist(clicks, roi, spend)
                elif hasattr(instance, 'hypothesis_direct_link_test'):
                    # Пробуем другой метод
                    offer_name = campaign_data.get('offer', 'unknown')
                    result = instance.hypothesis_direct_link_test(offer_name)
                else:
                    result = {"action": "HOLD", "reason": "Анализ кризисной ситуации"}
                    
                verdict = self._parse_verdict(result)
                confidence = self._parse_confidence(result)
                reason = self._parse_reason(result)
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
            except Exception as e:
                print(f"Error in block_3_crisis adapter: {e}")
                
        elif block_id == "block_4_volatility":
            # Блок 4: Волатильность
            # Для этого блока нужна история ROI, но у нас ее нет в campaign_data
            # Используем упрощенный подход
            roi = campaign_data.get('roi', 0)
            current_budget = campaign_data.get('spend', 0)
            
            try:
                if hasattr(instance, 'analyze_volatility_and_budget'):
                    # Создаем фиктивную историю ROI на основе текущего ROI
                    daily_roi_history = [roi * 0.8, roi, roi * 1.2]  # Фиктивные данные
                    result = instance.analyze_volatility_and_budget(daily_roi_history, current_budget)
                elif hasattr(instance, 'epc_cpc_deviation_rule'):
                    # Пробуем другой метод
                    offer_epc = campaign_data.get('epc', 0.1)
                    current_cpc = campaign_data.get('cpc', 0.05)
                    result_str = instance.epc_cpc_deviation_rule(offer_epc, current_cpc)
                    result = {"action": result_str, "reason": f"EPC-CPC анализ: {result_str}"}
                else:
                    result = {"action": "HOLD", "reason": f"Волатильность: {campaign_data.get('volatility', 0)}%"}
                    
                verdict = self._parse_verdict(result)
                confidence = self._parse_confidence(result)
                reason = self._parse_reason(result)
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
            except Exception as e:
                print(f"Error in block_4_volatility adapter: {e}")
                
        elif block_id == "block_5_scale":
            # Блок 5: Скейлинг
            current_budget = campaign_data.get('spend', 0)
            roi = campaign_data.get('roi', 0)
            is_main_path_profitable = roi > 20
            
            try:
                if hasattr(instance, 'calculate_aggressive_budget_increase'):
                    result = instance.calculate_aggressive_budget_increase(current_budget, is_main_path_profitable)
                elif hasattr(instance, 'winner_isolation_strategy'):
                    # Пробуем другой метод
                    winner_has_unique_jump = campaign_data.get('has_jump_monetization', False)
                    result = instance.winner_isolation_strategy(winner_has_unique_jump)
                else:
                    result = {"action": "SCALE" if roi > 30 else "HOLD", "reason": f"ROI: {roi}%"}
                    
                verdict = self._parse_verdict(result)
                confidence = self._parse_confidence(result)
                reason = self._parse_reason(result)
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
            except Exception as e:
                print(f"Error in block_5_scale adapter: {e}")
                
        elif block_id == "block_6_payouts":
            # Блок 6: Выплаты
            payout = campaign_data.get('payout', 100)  # Дефолтное значение выплаты
            spend = campaign_data.get('spend', 0)
            roi = campaign_data.get('roi', 0)
            
            try:
                if hasattr(instance, 'calculate_blacklist_threshold_by_payout'):
                    result = instance.calculate_blacklist_threshold_by_payout(payout, spend, roi)
                elif hasattr(instance, 'calculate_budget_scaling_rounded'):
                    # Пробуем другой метод
                    current_budget = campaign_data.get('spend', 0)
                    result = instance.calculate_budget_scaling_rounded(current_budget)
                else:
                    result = {"action": "HOLD", "reason": "Анализ выплат"}
                    
                verdict = self._parse_verdict(result)
                confidence = self._parse_confidence(result)
                reason = self._parse_reason(result)
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
            except Exception as e:
                print(f"Error in block_6_payouts adapter: {e}")
        
        # Общая стратегия для других блоков
        try:
            # Ищем метод анализа
            analyze_method = None
            for name, method in inspect.getmembers(instance, inspect.ismethod):
                if 'analyze' in name.lower() or 'get_verdict' in name.lower():
                    analyze_method = method
                    break
                    
            if analyze_method is None:
                # Пробуем первый публичный метод
                for name, method in inspect.getmembers(instance, inspect.ismethod):
                    if not name.startswith('_'):
                        analyze_method = method
                        break
            
            if analyze_method:
                # Вызываем метод с данными кампании
                result = analyze_method(campaign_data)
                
                # Парсим результат
                verdict = self._parse_verdict(result)
                confidence = self._parse_confidence(result)
                reason = self._parse_reason(result)
                
                return BlockVote(
                    block_name=block_id,
                    verdict=verdict,
                    confidence=confidence,
                    reason=reason,
                    weight=metadata.weight
                )
        except Exception as e:
            print(f"Error in general adapter for block {block_id}: {e}")
            
        # Если ничего не сработало, возвращаем голос по умолчанию
        return BlockVote(
            block_name=block_id,
            verdict="HOLD",
            confidence=0.5,
            reason="Блок не смог проанализировать данные",
            weight=metadata.weight
        )
        
    def _parse_verdict(self, result) -> str:
        """Извлечь вердикт из результата блока."""
        if isinstance(result, dict):
            # Пробуем разные ключи
            for key in ['verdict', 'action', 'decision', 'recommendation']:
                if key in result:
                    val = str(result[key]).upper()
                    if any(v in val for v in ['SCALE', 'HOLD', 'STOP', 'OPTIMIZE']):
                        for verdict in ['SCALE', 'HOLD', 'STOP', 'OPTIMIZE']:
                            if verdict in val:
                                return verdict
                    return "HOLD"
                    
        elif isinstance(result, str):
            result_upper = result.upper()
            for verdict in ['SCALE', 'HOLD', 'STOP', 'OPTIMIZE']:
                if verdict in result_upper:
                    return verdict
                    
        return "HOLD"
        
    def _parse_confidence(self, result) -> float:
        """Извлечь уверенность из результата блока."""
        if isinstance(result, dict):
            for key in ['confidence', 'score', 'probability']:
                if key in result:
                    try:
                        val = float(result[key])
                        if 0 <= val <= 1:
                            return val
                        elif 0 <= val <= 100:
                            return val / 100.0
                    except (ValueError, TypeError):
                        pass
                        
        # Умолчательная уверенность на основе типа вердикта
        return 0.7
        
    def _parse_reason(self, result) -> str:
        """Извлечь причину из результата блока."""
        if isinstance(result, dict):
            for key in ['reason', 'explanation', 'logic', 'description']:
                if key in result:
                    return str(result[key])
                    
        elif isinstance(result, str):
            return result
            
        return "Нет объяснения"
        
    def get_final_decision(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Получить финальное решение на основе голосов всех блоков."""
        votes = self.get_block_votes(campaign_data)
        
        if not votes:
            return {
                "final_verdict": "HOLD",
                "confidence": 0.5,
                "reason": "Нет активных блоков знаний",
                "votes": [],
                "vote_breakdown": {}
            }
            
        # Группируем голоса по вердиктам
        verdict_scores = {}
        for vote in votes:
            if vote.verdict not in verdict_scores:
                verdict_scores[vote.verdict] = 0.0
            verdict_scores[vote.verdict] += vote.weighted_score()
            
        # Находим вердикт с максимальным взвешенным счетом
        final_verdict = max(verdict_scores.items(), key=lambda x: x[1])[0]
        total_score = sum(verdict_scores.values())
        confidence = verdict_scores[final_verdict] / total_score if total_score > 0 else 0.5
        
        # Собираем причины для финального вердикта
        reasons = [vote.reason for vote in votes if vote.verdict == final_verdict]
        final_reason = " | ".join(reasons[:3])  # Берем до 3 причин
        
        # Детализация голосов
        vote_breakdown = {}
        for verdict in ['SCALE', 'HOLD', 'STOP', 'OPTIMIZE']:
            verdict_votes = [vote.to_dict() for vote in votes if vote.verdict == verdict]
            if verdict_votes:
                vote_breakdown[verdict] = {
                    "count": len(verdict_votes),
                    "total_weighted_score": sum(v['weighted_score'] for v in verdict_votes),
                    "votes": verdict_votes
                }
                
        return {
            "final_verdict": final_verdict,
            "confidence": confidence,
            "reason": final_reason,
            "votes": [vote.to_dict() for vote in votes],
            "vote_breakdown": vote_breakdown,
            "campaign_id": campaign_data.get('campaign_id', 'unknown')
        }
        
    def record_decision(self, campaign_id: str, final_decision: Dict, 
                       user_decision: Optional[str] = None) -> None:
        """Записать решение в историю для обучения."""
        decision_record = {
            "timestamp": datetime.now().isoformat(),
            "campaign_id": campaign_id,
            "final_decision": final_decision,
            "user_decision": user_decision,
            "block_votes": final_decision.get('votes', [])
        }
        
        self._decision_history.append(decision_record)
        
        # Если есть решение пользователя, обновляем веса блоков
        if user_decision:
            self._update_block_weights(campaign_id, final_decision, user_decision)
            
    def _update_block_weights(self, campaign_id: str, final_decision: Dict, user_decision: str):
        """Обновить веса блоков на основе решения пользователя."""
        user_verdict = user_decision.upper()
        
        for vote_data in final_decision.get('votes', []):
            block_id = vote_data['block_name']
            block_verdict = vote_data['verdict']
            
            if block_id in self._blocks_metadata:
                metadata = self._blocks_metadata[block_id]
                
                # Определяем, был ли голос блока правильным
                was_correct = (block_verdict == user_verdict)
                
                # Обновляем вес
                metadata.update_weight(was_correct)
                
                # Записываем в историю точности
                metadata.accuracy_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "campaign_id": campaign_id,
                    "was_correct": was_correct,
                    "block_verdict": block_verdict,
                    "user_verdict": user_verdict
                })
                
                # Ограничиваем историю последними 100 записями
                if len(metadata.accuracy_history) > 100:
                    metadata.accuracy_history = metadata.accuracy_history[-100:]
                    
        # Сохраняем обновленные метаданные
        self._save_blocks_metadata()
        
    def get_block_statistics(self) -> Dict[str, Any]:
        """Получить статистику по всем блокам."""
        stats = {}
        
        for block_id, metadata in self._blocks_metadata.items():
            if metadata.accuracy_history:
                correct_count = sum(1 for h in metadata.accuracy_history if h.get('was_correct', False))
                total_count = len(metadata.accuracy_history)
                accuracy = correct_count / total_count if total_count > 0 else 0.0
            else:
                correct_count = 0
                total_count = 0
                accuracy = 0.0
                
            stats[block_id] = {
                "enabled": metadata.enabled,
                "weight": metadata.weight,
                "priority": metadata.priority,
                "accuracy": accuracy,
                "correct_decisions": correct_count,
                "total_decisions": total_count,
                "last_used": metadata.last_used.isoformat() if metadata.last_used else None,
                "class_name": metadata.class_name,
                "description": metadata.description
            }
            
        return stats
        
    def enable_block(self, block_id: str, enabled: bool = True) -> bool:
        """Включить или выключить блок."""
        if block_id in self._blocks_metadata:
            self._blocks_metadata[block_id].enabled = enabled
            self._save_blocks_metadata()
            return True
        return False
        
    def set_block_weight(self, block_id: str, weight: float) -> bool:
        """Установить вес блока вручную."""
        if block_id in self._blocks_metadata:
            self._blocks_metadata[block_id].weight = max(0.1, min(3.0, weight))
            self._save_blocks_metadata()
            return True
        return False
        
    def set_block_priority(self, block_id: str, priority: int) -> bool:
        """Установить приоритет блока."""
        if block_id in self._blocks_metadata:
            self._blocks_metadata[block_id].priority = max(1, min(10, priority))
            self._save_blocks_metadata()
            return True
        return False
        
    def reload_blocks(self) -> None:
        """Перезагрузить все блоки знаний."""
        self._loaded_classes.clear()
        self._load_all_blocks()
        
    def add_new_block(self, file_path: str, class_name: str, description: str = "") -> bool:
        """Добавить новый блок знаний."""
        try:
            # Копируем файл в my_knowledge
            source_path = Path(file_path)
            dest_path = self._my_knowledge_path / source_path.name
            
            # TODO: Реализовать копирование файла
            # Пока просто создаем метаданные
            
            block_id = source_path.stem
            metadata = BlockMetadata(
                block_id=block_id,
                class_name=class_name,
                file_path=str(dest_path.relative_to(self._base)),
                description=description,
                priority=5,
                enabled=True
            )
            
            self._blocks_metadata[block_id] = metadata
            self._save_blocks_metadata()
            self.reload_blocks()
            
            return True
            
        except Exception as e:
            print(f"Error adding new block: {e}")
            return False
            
    def get_decision_history(self, limit: int = 100) -> List[Dict]:
        """Получить историю решений."""
        return self._decision_history[-limit:] if self._decision_history else []
        
    def clear_decision_history(self) -> None:
        """Очистить историю решений."""
        self._decision_history.clear()
        
    def get_available_blocks(self) -> List[Dict]:
        """Получить список всех доступных блоков."""
        blocks = []
        for block_id, metadata in self._blocks_metadata.items():
            blocks.append({
                "id": block_id,
                "class_name": metadata.class_name,
                "enabled": metadata.enabled,
                "weight": metadata.weight,
                "priority": metadata.priority,
                "description": metadata.description,
                "last_used": metadata.last_used.isoformat() if metadata.last_used else None,
                "loaded": block_id in self._loaded_classes
            })
        return blocks
        
    def analyze_campaign_simple(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Упрощенный анализ кампании для обратной совместимости."""
        decision = self.get_final_decision(campaign_data)
        
        # Преобразуем в формат старого KnowledgeBase
        return {
            "verdict": decision["final_verdict"],
            "confidence": decision["confidence"] * 100,  # В процентах
            "reason": decision["reason"],
            "block_votes": decision["votes"],
            "vote_breakdown": decision["vote_breakdown"]
        }
        
    # --- Методы для совместимости с оригинальным KnowledgeBase ---
    
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

    def get_model_weights(self) -> Dict[str, Any]:
        """Веса модели из 05_Learning/model_weights.json."""
        data = self._load_json_cached("model_weights", "05_Learning", "model_weights.json", default={})
        return data if isinstance(data, dict) else {}

    def invalidate_cache(self, key: Optional[str] = None) -> None:
        """Сброс кэша (всего или по ключу)."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()
            
    # --- Псевдонимы для обратной совместимости ---
    
    def vote_on_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Псевдоним для get_final_decision (обратная совместимость)."""
        return self.get_final_decision(campaign_data)
        
    def get_final_verdict(self, campaign_data: Dict[str, Any]) -> str:
        """Псевдоним для получения только вердикта."""
        decision = self.get_final_decision(campaign_data)
        return decision["final_verdict"]
        
    def analyze_campaign(self, campaign_id: Optional[str] = None, roi: Optional[float] = None, 
                        profit: Optional[float] = None, spend: Optional[float] = None, 
                        clicks: Optional[int] = None, conversions: Optional[int] = None, 
                        volatility: Optional[float] = None, daily_impact: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        Анализ кампании для обратной совместимости с вызовами в Top5ServiceV2 и LearningService.
        Преобразует позиционные параметры в словарь и вызывает analyze_campaign_simple.
        """
        campaign_data = {
            "campaign_id": campaign_id or "unknown",
            "roi": roi or 0.0,
            "profit": profit or 0.0,
            "spend": spend or 0.0,
            "clicks": clicks or 0,
            "conversions": conversions or 0,
            "volatility": volatility or 0.0,
            "daily_impact": daily_impact or []
        }
        return self.analyze_campaign_simple(campaign_data)
