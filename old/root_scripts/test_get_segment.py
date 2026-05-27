from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2
kb = KnowledgeBaseV2()
cols = kb.get_segment_columns("traffichunt")
print("Traffichunt cols:", cols)
