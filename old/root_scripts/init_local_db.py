import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.database import engine, Base
from backend.models_v2 import (
    TrafficStats, AdditionalMonetization, Orphan, AIMemoryV2, 
    BlockKnowledge, BlockVoteHistory, LearningCycle, RecheckQueue, AIAgent
)

def init_db():
    print("Initializing local database...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully in:", engine.url)
    except Exception as e:
        print(f"❌ Error creating tables: {e}")

if __name__ == "__main__":
    init_db()
