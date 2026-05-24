import os
import sys
import argparse
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "/Users/andreylp/affiliate_brain/database.db"
FILE_PATH = "/Users/andreylp/affiliate_brain/SOLD.xlsx"

def extract_prefix(token1):
    if not token1:
        return ''
    token1_str = str(token1).strip()
    if '_' in token1_str:
        return token1_str.split('_', 1)[0]
    return token1_str

def main():
    parser = argparse.ArgumentParser(description="Import SOLD.xlsx sales data into additional_monetization")
    parser.add_argument("--date", type=str, help="Target date for the sales in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without committing to the database")
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 STARTING SOLD IMPORT UTILITY")
    print("=" * 60)

    if not os.path.exists(FILE_PATH):
        print(f"❌ Error: SOLD.xlsx not found at {FILE_PATH}")
        sys.exit(1)
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: database.db not found at {DB_PATH}")
        sys.exit(1)

    if not args.date:
        print("💡 Tip: You did not provide a --date argument. Exiting.")
        sys.exit(1)

    target_date = args.date
    is_dry_run = args.dry_run
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"❌ Error: Invalid date format '{target_date}'. Must be YYYY-MM-DD.")
        sys.exit(1)

    print("📖 Reading and parsing SOLD.xlsx...")
    try:
        df = pd.read_excel(FILE_PATH)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    df = df.dropna(how='all')
    
    # In SOLD.xlsx the columns are: T1, T5, Clicks, CPC, Revenue,
    df = df.rename(columns={
        df.columns[0]: 'token1',
        df.columns[4]: 'revenue'
    })
    
    df['token1'] = df['token1'].astype(str).str.strip()
    
    def is_valid_token(t):
        if not t or t == 'nan' or t == 'None':
            return False
        tl = t.lower()
        if 'итого' in tl or 'sub id' in tl or 'date' in tl:
            return False
        return True

    df = df[df['token1'].apply(is_valid_token)]
    print(f"✅ Loaded {len(df)} valid sales rows.")

    print("🛢️  Connecting to database.db...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT
            CASE WHEN instr(token1, '_') > 0 THEN substr(token1, 1, instr(token1, '_') - 1) ELSE token1 END as prefix,
            campaign_id
        FROM traffic_stats
        WHERE token1 IS NOT NULL AND token1 != ''
    """)
    rows = cursor.fetchall()
    prefix_to_campaign = {}
    for prefix, campaign_id in rows:
        if prefix and campaign_id:
            prefix_to_campaign[prefix] = campaign_id
    
    matched_rows = []
    orphan_rows = []
    total_revenue = 0.0

    date_compact = target_date.replace('-', '')

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        token1 = row['token1']
        revenue = float(row['revenue']) if pd.notna(row['revenue']) else 0.0
        
        prefix = extract_prefix(token1)
        suffix = token1.split('_', 1)[1] if '_' in token1 else ''
        
        campaign_id = prefix_to_campaign.get(prefix)
        total_revenue += revenue

        if campaign_id:
            click_id = f"sale_{prefix}_{date_compact}_{suffix};sold_{idx}_{revenue}"
            matched_rows.append({
                'click_id': click_id,
                'campaign_id': campaign_id,
                'token1': token1,
                'date': target_date,
                'revenue': revenue,
                'source': 'sales'
            })
        else:
            orphan_rows.append({
                'token1': token1,
                'date': target_date,
                'revenue': revenue,
                'source': 'sales'
            })

    print("-" * 60)
    print("📊 Matching Summary:")
    print(f"   - Total Rows: {len(df)}")
    print(f"   - Matched Rows (inserted to additional_monetization): {len(matched_rows)}")
    print(f"   - Orphaned Rows (inserted to orphans): {len(orphan_rows)}")
    print(f"   - Total Revenue: ${total_revenue:.2f}")
    print("-" * 60)

    if is_dry_run:
        print("⚠️  DRY RUN: No database changes were made.")
    else:
        print("💾 Saving records to database...")
        if matched_rows:
            values = []
            for r in matched_rows:
                cid = r['click_id'].replace("'", "''")
                camp = r['campaign_id'].replace("'", "''")
                t1 = r['token1'].replace("'", "''")
                d = r['date']
                rev = r['revenue']
                src = r['source']
                values.append(f"('{cid}', '{camp}', '{t1}', '{d}', {rev}, '{src}')")
            
            sql = f"""
                INSERT OR REPLACE INTO additional_monetization (click_id, campaign_id, token1, date, revenue, source)
                VALUES {', '.join(values)}
            """
            cursor.execute(sql)
            print(f"   ✅ Successfully upserted {len(matched_rows)} records into 'additional_monetization'.")

        if orphan_rows:
            orphan_values = []
            for r in orphan_rows:
                t1 = r['token1'].replace("'", "''")
                d = r['date']
                rev = r['revenue']
                src = r['source']
                orphan_values.append(f"('{t1}', '{d}', {rev}, '{src}')")
            
            sql_orphan = f"""
                INSERT INTO orphans (token1, date, revenue, source)
                VALUES {', '.join(orphan_values)}
            """
            cursor.execute(sql_orphan)
            print(f"   ✅ Successfully inserted {len(orphan_rows)} records into 'orphans'.")

        conn.commit()
        print("🎉 LIVE IMPORT COMPLETED SUCCESSFULLY!")

    conn.close()

if __name__ == "__main__":
    main()
