
from sqlalchemy import create_mock_engine
from sqlalchemy.orm import sessionmaker
from backend.routers.metrics import get_campaigns_table
import asyncio
from datetime import date
from sqlalchemy import create_engine

# Use the real database to see the real error
engine = create_engine("sqlite:////Users/andreylp/affiliate_brain/database.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

async def test():
    try:
        res = await get_campaigns_table(period=14, date_from_param=None, date_to_param=None, source="Advery", db=db)
        print("Success")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test())
