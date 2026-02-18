"""
Расширенные модели для KnowledgeBaseV2 с поддержкой голосования блоков и обучения.
"""
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, Boolean, JSON, Index
from datetime import datetime
from sqlalchemy.sql import func
from backend.database import Base

class TrafficStats(Base):
    __tablename__ = "traffic_stats"
    id = Column(Integer, primary_key=True)
    click_id = Column(String(255))
    campaign_id = Column(String(100))
    campaign = Column(String(255))
    date = Column(Date)
    token1 = Column(String(255))
    token2 = Column(String(255))
    token3 = Column(String(255))
    token4 = Column(String(255))
    token5 = Column(String(255))
    token6 = Column(String(255))
    token7 = Column(String(255))
    token8 = Column(String(255))
    token9 = Column(String(255))
    token10 = Column(String(255))
    traffic_source = Column(String(255))
    path = Column(String(255))
    rule = Column(String(255))
    offer = Column(String(255))
    lander_id = Column(String(100))
    device_type = Column(String(100))
    os = Column(String(100))
    os_version = Column(String(50))
    browser_name = Column(String(100))
    country = Column(String(10))
    language = Column(String(20))
    cost = Column(Float, default=0)
    revenue = Column(Float, default=0)
    conversions = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

class AdditionalMonetization(Base):
    __tablename__ = "additional_monetization"
    id = Column(Integer, primary_key=True)
    click_id = Column(String(255), unique=True, nullable=True)  # уникален как в traffic_stats; NULL для sale
    campaign_id = Column(String(100))
    token1 = Column(String(255))
    date = Column(Date)
    revenue = Column(Float)
    source = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())

class Orphan(Base):
    __tablename__ = "orphans"
    id = Column(Integer, primary_key=True)
    token1 = Column(String(255))
    date = Column(Date)
    revenue = Column(Float)
    source = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())

class AIMemoryV2(Base):
    """Расширенная таблица AI памяти с поддержкой голосования блоков."""
    __tablename__ = "ai_memory_v2"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(String(100), nullable=False, index=True)
    decision_date = Column(DateTime, server_default=func.now(), index=True)
    
    # Голоса блоков
    block_votes = Column(JSON)  # JSON с голосами всех блоков
    final_verdict = Column(String(50))  # Финальное решение системы
    final_confidence = Column(Float)  # Уверенность финального решения (0-1)
    final_reason = Column(Text)  # Объяснение финального решения
    
    # Решение пользователя
    user_verdict = Column(String(50))  # Решение пользователя (SCALE/HOLD/STOP/OPTIMIZE)
    user_comment = Column(Text)  # Комментарий пользователя
    
    # Контекст кампании
    campaign_snapshot = Column(JSON)  # Снимок данных кампании на момент решения
    metrics_snapshot = Column(JSON)  # Метрики кампании (ROI, клики, расход и т.д.)
    
    # Результаты
    outcome_verdict = Column(String(50))  # Итоговый вердикт через 7 дней
    outcome_roi_7d = Column(Float)  # ROI через 7 дней
    outcome_roi_14d = Column(Float)  # ROI через 14 дней
    outcome_updated_at = Column(DateTime)  # Когда были обновлены результаты
    
    # Флаги
    needs_outcome_update = Column(Boolean, default=True)  # Нужно обновить результаты
    is_training_example = Column(Boolean, default=True)  # Использовать для обучения
    
    # Индексы
    __table_args__ = (
        Index('ix_ai_memory_v2_campaign_date', 'campaign_id', 'decision_date'),
        Index('ix_ai_memory_v2_outcome', 'outcome_verdict'),
        Index('ix_ai_memory_v2_needs_update', 'needs_outcome_update'),
    )

class BlockKnowledge(Base):
    """Таблица для хранения метаданных и статистики блоков знаний."""
    __tablename__ = "block_knowledge"
    id = Column(Integer, primary_key=True)
    block_id = Column(String(100), unique=True, nullable=False, index=True)
    block_name = Column(String(255))
    class_name = Column(String(255))
    description = Column(Text)
    
    # Веса и приоритеты
    current_weight = Column(Float, default=1.0)  # Текущий вес (0.1-3.0)
    base_weight = Column(Float, default=1.0)  # Базовый вес
    priority = Column(Integer, default=5)  # Приоритет (1-10)
    enabled = Column(Boolean, default=True)
    
    # Статистика
    total_votes = Column(Integer, default=0)
    correct_votes = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)  # Точность (correct/total)
    
    # История весов
    weight_history = Column(JSON)  # История изменений веса
    
    # Временные метки
    created_at = Column(DateTime, server_default=func.now())
    last_used = Column(DateTime)
    last_weight_update = Column(DateTime)
    
    # Дополнительные метаданные
    block_metadata = Column(JSON)  # Дополнительные метаданные блока

class BlockVoteHistory(Base):
    """История голосов блоков для детального анализа."""
    __tablename__ = "block_vote_history"
    id = Column(Integer, primary_key=True)
    decision_id = Column(Integer, index=True)  # Ссылка на ai_memory_v2.id
    block_id = Column(String(100), index=True)  # Ссылка на block_knowledge.block_id
    
    # Голос блока
    verdict = Column(String(50))  # SCALE/HOLD/STOP/OPTIMIZE
    confidence = Column(Float)  # Уверенность (0-1)
    reason = Column(Text)  # Причина голоса
    weight_at_time = Column(Float)  # Вес блока на момент голосования
    
    # Результат
    was_correct = Column(Boolean)  # Был ли голос правильным
    user_verdict = Column(String(50))  # Решение пользователя для сравнения
    
    # Временные метки
    voted_at = Column(DateTime, server_default=func.now())
    
    # Индексы
    __table_args__ = (
        Index('ix_block_vote_history_decision_block', 'decision_id', 'block_id'),
        Index('ix_block_vote_history_was_correct', 'was_correct'),
    )

class LearningCycle(Base):
    """Циклы обучения системы."""
    __tablename__ = "learning_cycles"
    id = Column(Integer, primary_key=True)
    cycle_start = Column(DateTime, server_default=func.now())
    cycle_end = Column(DateTime)
    
    # Статистика цикла
    total_decisions = Column(Integer, default=0)
    correct_decisions = Column(Integer, default=0)
    system_accuracy = Column(Float, default=0.0)
    
    # Изменения весов
    weight_updates = Column(JSON)  # Какие веса были изменены и на сколько
    
    # Метрики
    avg_confidence = Column(Float, default=0.0)
    consensus_level = Column(Float, default=0.0)  # Уровень согласия между блоками
    
    # Флаги
    is_completed = Column(Boolean, default=False)
    
    # Комментарии
    notes = Column(Text)

class RecheckQueue(Base):
    __tablename__ = "recheck_queue"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(String(100), nullable=False)
    campaign = Column(String(255))
    verdict = Column(String(50))
    recheck_after_days = Column(Integer, default=0)
    applied_at = Column(DateTime, server_default=func.now())

class AIAgent(Base):
    __tablename__ = 'ai_agents'
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(100), unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    provider = Column(String(50))
    model = Column(String(100))
    system_prompt = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow)
