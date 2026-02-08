"""
Affiliate Brain — Knowledge Base / Мозг системы.
Единая точка доступа к Logic_Blocks. Модули (TOP-5 Bot, Company Analytics)
потребляют знания через этот интерфейс, не завися от конкретных файлов.
"""
from backend.brain.knowledge_base import KnowledgeBase

__all__ = ["KnowledgeBase"]
