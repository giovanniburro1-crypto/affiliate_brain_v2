"""
Affiliate Brain — Knowledge Base / Мозг системы.
Единая точка доступа к Logic_Blocks. Модули (TOP-5 Bot, Company Analytics)
потребляют знания через этот интерфейс, не завися от конкретных файлов.
"""
from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2

# Backward compat alias — company_analytics и другие модули используют старое имя
KnowledgeBase = KnowledgeBaseV2

__all__ = ["KnowledgeBase", "KnowledgeBaseV2"]
