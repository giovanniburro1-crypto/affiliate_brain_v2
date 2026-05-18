import os
import sys
import argparse
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "/Users/andreylp/affiliate_brain/database.db"
FILE_PATH = "/Users/andreylp/affiliate_brain/sale_mir.csv"

def extract_prefix(token1):
    if not token1:
        return ''
    token1_str = str(token1).strip()
    if '_' in token1_str:
        return token1_str.split('_', 1)[0]
    return token1_str

def main():
    parser = argparse.ArgumentParser(description="Import sale_mir.csv sales data into additional_monetization")
    parser.add_argument("--date", type=str, help="Target date for the sales in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without committing to the database")
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 STARTING SALE_MIR IMPORT UTILITY")
    print("=" * 60)

    # 1. Check if files exist
    if not os.path.exists(FILE_PATH):
        print(f"❌ Error: sale_mir.csv not found at {FILE_PATH}")
        sys.exit(1)
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: database.db not found at {DB_PATH}")
        sys.exit(1)

    # 2. Ask for date if not provided
    if not args.date:
        print("💡 Tip: You did not provide a --date argument (e.g. --date 2026-05-17).")
        print("We will perform a DRY-RUN analysis using yesterday's date (2026-05-17) as default.")
        target_date = "2026-05-17"
        is_dry_run = True
    else:
        target_date = args.date
        is_dry_run = args.dry_run
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Error: Invalid date format '{target_date}'. Must be YYYY-MM-DD.")
            sys.exit(1)

    print(f"📋 Configuration:")
    print(f"   - File: {FILE_PATH}")
    print(f"   - Target Date: {target_date}")
    print(f"   - Mode: {'DRY RUN (No database modifications)' if is_dry_run else 'LIVE IMPORT'}")
    print("-" * 60)

    # 3. Read sales file
    print("📖 Reading and parsing sale_mir.csv...")
    try:
        # Since it is a .xlsx file under .csv name, read with excel engine
        df = pd.read_excel(FILE_PATH)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    # Clean and rename columns
    # We skip empty header rows (row 0 is nan)
    df = df.dropna(how='all')
    
    # Check if there are at least 4 columns
    if len(df.columns) < 4:
        print(f"❌ Error: Expected at least 4 columns, got {len(df.columns)}")
        print(df.head())
        sys.exit(1)

    # Rename first 4 columns
    df.columns = ['token1', 'clicks', 'payout', 'revenue'] + list(df.columns[4:])
    df['token1'] = df['token1'].astype(str).str.strip()
    
    # Filter out empty or header/summary rows
    def is_valid_token(t):
        if not t or t == 'nan' or t == 'None':
            return False
        tl = t.lower()
        if 'итого' in tl or 'sub id' in tl or 'date' in tl:
            return False
        return True

    df = df[df['token1'].apply(is_valid_token)]
    print(f"✅ Loaded {len(df)} valid sales rows.")

    # 4. Connect to database and fetch campaign prefix-to-id mapping
    print("🛢️  Connecting to database.db...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔍 Fetching campaign matching map from traffic_stats (might take ~10-15s due to 1.7M rows)...")
    start_time = datetime.now()
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
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"✅ Loaded {len(prefix_to_campaign)} active campaign prefixes in {elapsed:.2f} seconds.")

    # 5. Classify and prepare rows
    matched_rows = []
    orphan_rows = []
    total_revenue = 0.0

    date_compact = target_date.replace('-', '')

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        token1 = row['token1']
        clicks = row['clicks']
        payout = row['payout']
        revenue = float(row['revenue']) if pd.notna(row['revenue']) else 0.0
        
        prefix = extract_prefix(token1)
        suffix = token1.split('_', 1)[1] if '_' in token1 else ''
        
        campaign_id = prefix_to_campaign.get(prefix)
        total_revenue += revenue

        if campaign_id:
            # Generate unique click_id to prevent collision between multiple entries
            # of the same campaign on the same day. Include the row index.
            click_id = f"sale_{prefix}_{date_compact}_{suffix};mir_{idx}_{revenue}"
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
    print(f"   - Matched Rows (inserted to additional_monetization): {len(matched_rows)} ({len(matched_rows)/len(df)*100:.1f}%)")
    print(f"   - Orphaned Rows (inserted to orphans): {len(orphan_rows)} ({len(orphan_rows)/len(df)*100:.1f}%)")
    print(f"   - Total Revenue: ${total_revenue:.2f}")
    print("-" * 60)

    # 6. Database Operations
    if is_dry_run:
        print("⚠️  DRY RUN: No database changes were made.")
        print("💡 To perform the actual import, run:")
        print(f"   python3 app/backend/scratch/import_sale_mir.py --date {target_date}")
    else:
        print("💾 Saving records to database...")
        # Insert Matched Rows
        if matched_rows:
            inserted_count = 0
            values = []
            for r in matched_rows:
                cid = r['click_id'].replace("'", "''")
                camp = r['campaign_id'].replace("'", "''")
                t1 = r['token1'].replace("'", "''")
                d = r['date']
                rev = r['revenue']
                src = r['source']
                values.append(f"('{cid}', '{camp}', '{t1}', '{d}', {rev}, '{src}')")
            
            # Execute batch insert OR replace
            sql = f"""
                INSERT OR REPLACE INTO additional_monetization (click_id, campaign_id, token1, date, revenue, source)
                VALUES {', '.join(values)}
            """
            cursor.execute(sql)
            print(f"   ✅ Successfully upserted {len(matched_rows)} records into 'additional_monetization'.")

        # Insert Orphan Rows
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
