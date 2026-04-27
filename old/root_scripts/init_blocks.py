import sys
import json
from pathlib import Path
from datetime import datetime
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))

from backend.database import engine
from backend.brain.knowledge_base_v2 import KnowledgeBaseV2

def initialize_blocks():
    print("Initializing blocks in database...")
    kb = KnowledgeBaseV2()
    blocks = kb.get_available_blocks()
    
    with engine.connect() as conn:
        for block in blocks:
            # Check if block exists
            result = conn.execute(
                text("SELECT COUNT(*) FROM block_knowledge WHERE block_id = :block_id"),
                {"block_id": block["id"]}
            )
            exists = result.scalar() > 0
            
            if not exists:
                conn.execute(text("""
                    INSERT INTO block_knowledge (
                        block_id, block_name, class_name, description,
                        current_weight, base_weight, priority, enabled,
                        total_votes, correct_votes, accuracy,
                        created_at, last_used, block_metadata
                    ) VALUES (
                        :block_id, :block_name, :class_name, :description,
                        :current_weight, :base_weight, :priority, :enabled,
                        :total_votes, :correct_votes, :accuracy,
                        :created_at, :last_used, :block_metadata
                    )
                """), {
                    "block_id": block["id"],
                    "block_name": block["id"].replace("_", " ").title(),
                    "class_name": block["class_name"],
                    "description": block.get("description", f"Block {block['id']}"),
                    "current_weight": 1.0,
                    "base_weight": 1.0,
                    "priority": 5,
                    "enabled": True,
                    "total_votes": 0,
                    "correct_votes": 0,
                    "accuracy": 0.0,
                    "created_at": datetime.now(),
                    "last_used": None,
                    "block_metadata": json.dumps({
                        "loaded": True,
                        "file_path": f"logic_blocks/my_knowledge/{block['id']}.py"
                    })
                })
                print(f"  Added block: {block['id']}")
        conn.commit()
    print("✅ Blocks initialized.")

if __name__ == "__main__":
    initialize_blocks()
