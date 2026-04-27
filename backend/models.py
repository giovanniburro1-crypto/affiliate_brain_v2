from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, Boolean
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
    affiliate_network = Column(String(255))
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

class AIMemory(Base):
    __tablename__ = "ai_memory"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(String(100))
    decision_date = Column(DateTime, server_default=func.now())
    bot_verdict = Column(String(50))
    bot_score = Column(Float)
    bot_confidence = Column(Float)
    bot_reasoning = Column(Text)
    ai_verdict = Column(String(50))
    ai_confidence = Column(Float)
    user_choice = Column(String(50))
    user_comment = Column(Text)
    context_snapshot = Column(Text)
    outcome = Column(String(50))
    roi_after_7days = Column(Float)
    roi_after_14days = Column(Float)

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
