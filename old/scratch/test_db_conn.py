import os
import sqlalchemy
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL").replace(":5432/", ":6543/")
print(f"Testing connection to: {db_url.split('@')[-1]}")

try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print(f"Success: {result.fetchone()}")
except Exception as e:
    print(f"Error: {e}")
