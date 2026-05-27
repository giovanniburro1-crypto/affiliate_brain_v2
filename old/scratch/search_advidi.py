import sqlite3

db_path = "/Users/andreylp/affiliate_brain/database.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cursor.fetchall()]

print("Searching for 'Advidi' in database:")
found = False
for table in tables:
    try:
        cursor.execute(f"SELECT * FROM {table} LIMIT 1;")
        cols = [description[0] for description in cursor.description]
        
        for col in cols:
            cursor.execute(f"SELECT DISTINCT {col} FROM {table} WHERE CAST({col} AS TEXT) LIKE '%Advidi%';")
            rows = cursor.fetchall()
            if rows:
                found = True
                print(f"Found in table '{table}', column '{col}': { [r[0] for r in rows] }")
    except Exception as e:
        pass

if not found:
    print("Not found anywhere in the database.")

conn.close()
