"""
KnowledgeBaseV2 — расширенная система знаний с динамической загрузкой блоков,
системой голосования и автоматическим обучением на основе решений пользователя.
"""
import json
import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
import sys

_LOGIC_BLOCKS_ROOT = Path(__file__).resolve().parent.parent.parent / "logic_blocks"
_MY_KNOWLEDGE_PATH = _LOGIC_BLOCKS_ROOT / "my_knowledge"

# Добавляем путь к my_knowledge в sys.path для динамического импорта
if str(_MY_KNOWLEDGE_PATH) not in sys.path:
    sys.path.insert(0, str(_MY_KNOWLEDGE_PATH))

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
        
        # Загружаем метаданные блоков
        self._load_blocks_metadata()
        
        # Загружаем классы блоков
        self._load_all_blocks()
        
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
        for block_id, metadata in self._blocks_metadata.items():
            if not metadata.enabled:
                continue
                
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
                print(f"Error loading block {block_id}: {e}")
                
    def _save_blocks_metadata(self):
        """Сохранить метаданные блоков в файл."""
        metadata_path = self._base / "blocks_registry.json"
        
        data = {}
        for block_id, metadata in self._blocks_metadata.items():
            data[block_id] = metadata.to_dict()
            
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
                    
                    vote = BlockVote(
                        block_name=block_id,
                        verdict=verdict,
                        confidence=confidence,
                        reason=reason,
                        weight=metadata.weight
                    )
                    
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
               