import io
import time
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db
from sqlalchemy.exc import IntegrityError
from backend.models import TrafficStats, AdditionalMonetization, Orphan

router = APIRouter()

TRAFFIC_COLS = {
    'Click ID': 'click_id', 'Campaign ID': 'campaign_id', 'Campaign': 'campaign',
    'Date Click': 'date', 'Token 1': 'token1', 'Token 2': 'token2',
    'Token 3': 'token3', 'Token 4': 'token4', 'Token 5': 'token5',
    'Token 6': 'token6', 'Token 7': 'token7', 'Token 8': 'token8',
    'Token 9': 'token9', 'Token 10': 'token10', 'Traffic Source': 'traffic_source',
    'Path': 'path', 'Rule': 'rule', 'Offer': 'offer', 'Lander ID': 'lander_id',
    'Device Type': 'device_type', 'OS': 'os', 'OS Version': 'os_version',
    'Browser Name': 'browser_name', 'Country': 'country', 'Language': 'language',
    'Cost': 'cost', 'Payout': 'revenue'
}

def is_bot(token2):
    return 'bot' in str(token2).lower() if token2 else False

def extract_prefix(token1):
    if not token1: return ''
    return str(token1).split('_')[0]

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    start = time.time()
    stats = {'total': 0, 'inserted': 0, 'bots': 0, 'matched': 0, 'orphans': 0, 'errors': []}
    try:
        content = await file.read()
        filename = file.filename.lower()
        if 'sale' in filename:
            df = _read_sales_file(content)
            _process_sales(df, db, stats)
        else:
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
            df = df.rename(columns={k: v for k, v in TRAFFIC_COLS.items() if k in df.columns})
            _process_traffic(df, db, stats)
        stats['time'] = round(time.time() - start, 2)
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _read_sales_file(content):
    try:
        df = pd.read_csv(io.BytesIO(content), sep=';', encoding='utf-8')
        if len(df.columns) > 1: return df
    except: pass
    try:
        df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
        if len(df.columns) == 1 and ';' in str(df.columns[0]):
            headers = df.columns[0].split(';')
            data = [str(row.iloc[0]).split(';') for _, row in df.iterrows()]
            return pd.DataFrame(data, columns=headers)
        return df
    except: pass
    raise ValueError("Cannot read sales file")

def _process_traffic(df, db, stats):
    stats['total'] = len(df)
    batch = []
    for _, row in df.iterrows():
        token2 = str(row.get('token2', '')) if pd.notna(row.get('token2')) else ''
        if is_bot(token2):
            stats['bots'] += 1
            continue
        date_val = row.get('date')
        if isinstance(date_val, str):
            try: date_val = datetime.strptime(date_val[:10], '%Y-%m-%d').date()
            except: date_val = datetime.now().date()
        elif hasattr(date_val, 'date'): date_val = date_val.date()
        else: date_val = datetime.now().date()
        revenue = float(row.get('revenue', 0) or 0)
        batch.append(TrafficStats(
            click_id=str(row.get('click_id', f'gen_{stats["inserted"]}'))[:255],
            campaign_id=str(row.get('campaign_id', '')) if pd.notna(row.get('campaign_id')) else None,
            campaign=str(row.get('campaign', 'Unknown'))[:255], date=date_val,
            token1=str(row.get('token1', '')) if pd.notna(row.get('token1')) else None,
            token2=token2 or None,
            token3=str(row.get('token3', '')) if pd.notna(row.get('token3')) else None,
            token4=str(row.get('token4', '')) if pd.notna(row.get('token4')) else None,
            token5=str(row.get('token5', '')) if pd.notna(row.get('token5')) else None,
            token6=str(row.get('token6', '')) if pd.notna(row.get('token6')) else None,
            token7=str(row.get('token7', '')) if pd.notna(row.get('token7')) else None,
            token8=str(row.get('token8', '')) if pd.notna(row.get('token8')) else None,
            token9=str(row.get('token9', '')) if pd.notna(row.get('token9')) else None,
            token10=str(row.get('token10', '')) if pd.notna(row.get('token10')) else None,
            traffic_source=str(row.get('traffic_source', 'Unknown'))[:255],
            os=str(row.get('os', ''))[:100] if pd.notna(row.get('os')) else None,
            device_type=str(row.get('device_type', ''))[:100] if pd.notna(row.get('device_type')) else None,
            cost=float(row.get('cost', 0) or 0), revenue=revenue,
            conversions=1 if revenue > 0 else 0
        ))
        stats['inserted'] += 1
        if len(batch) >= 5000:
            _save_traffic_batch(db, batch)
            batch = []
    if batch:
        _save_traffic_batch(db, batch)


def _save_traffic_batch(db, batch):
    """
    Быстрая вставка через raw SQL с ON CONFLICT DO NOTHING.
    Это в 10-100 раз быстрее чем построчная вставка при дубликатах.
    """
    if not batch:
        return
    
    # Убираем дубликаты внутри партии
    seen = set()
    unique_batch = []
    for obj in batch:
        cid = getattr(obj, "click_id", None)
        if cid and cid not in seen:
            seen.add(cid)
            unique_batch.append(obj)
        elif not cid:
            unique_batch.append(obj)
    
    if not unique_batch:
        return
    
    # Формируем VALUES для bulk INSERT
    values_parts = []
    for obj in unique_batch:
        # Экранируем кавычки в строках
        def escape(s):
            if s is None:
                return 'NULL'
            s_str = str(s).replace("'", "''")
            return f"'{s_str}'"
        
        click_id = escape(getattr(obj, 'click_id', None))
        campaign_id = escape(getattr(obj, 'campaign_id', None))
        campaign = escape(getattr(obj, 'campaign', None))
        date_val = f"'{obj.date}'" if hasattr(obj, 'date') and obj.date else 'NULL'
        token1 = escape(getattr(obj, 'token1', None))
        token2 = escape(getattr(obj, 'token2', None))
        token3 = escape(getattr(obj, 'token3', None))
        token4 = escape(getattr(obj, 'token4', None))
        token5 = escape(getattr(obj, 'token5', None))
        token6 = escape(getattr(obj, 'token6', None))
        token7 = escape(getattr(obj, 'token7', None))
        token8 = escape(getattr(obj, 'token8', None))
        token9 = escape(getattr(obj, 'token9', None))
        token10 = escape(getattr(obj, 'token10', None))
        traffic_source = escape(getattr(obj, 'traffic_source', None))
        os_val = escape(getattr(obj, 'os', None))
        device_type_val = escape(getattr(obj, 'device_type', None))
        cost = getattr(obj, 'cost', 0) or 0
        revenue = getattr(obj, 'revenue', 0) or 0
        conversions = getattr(obj, 'conversions', 0) or 0
        
        values_parts.append(
            f"({click_id}, {campaign_id}, {campaign}, {date_val}, {token1}, {token2}, "
            f"{token3}, {token4}, {token5}, {token6}, {token7}, {token8}, {token9}, {token10}, "
            f"{traffic_source}, {os_val}, {device_type_val}, {cost}, {revenue}, {conversions})"
        )
    
    # Bulk INSERT с ON CONFLICT DO NOTHING
    sql = f"""
        INSERT INTO traffic_stats 
        (click_id, campaign_id, campaign, date, token1, token2, token3, token4, token5, 
         token6, token7, token8, token9, token10, traffic_source, os, device_type, cost, revenue, conversions)
        VALUES {', '.join(values_parts)}
        ON CONFLICT (click_id) DO NOTHING
    """
    
    try:
        db.execute(text(sql))
        db.commit()
    except Exception as e:
        # Если SQL слишком большой или другая ошибка - fallback на старый метод
        db.rollback()
        try:
            db.bulk_save_objects(unique_batch)
            db.commit()
        except IntegrityError:
            db.rollback()
            # Игнорируем дубликаты
            pass

def _process_sales(df, db, stats):
    """
    Оптимизированная обработка sales файлов:
    1. Собираем все prefixes за один раз
    2. Делаем ОДИН batch запрос для матчинга всех prefixes
    3. Используем полученный маппинг для быстрой классификации
    """
    stats['total'] = len(df)
    cols = list(df.columns)
    col_map = {}
    for col in cols:
        if 'sub id 1' in str(col).lower(): col_map[col] = 'token1'
    if len(cols) >= 5:
        col_map[cols[0]] = 'date'
        col_map[cols[-1]] = 'revenue'
    df = df.rename(columns=col_map)
    if 'token1' not in df.columns:
        raise ValueError(f"Missing Sub ID 1 column")
    
    # ШАГ 1: Собираем все уникальные prefixes из файла
    prefixes_set = set()
    rows_data = []
    
    for _, row in df.iterrows():
        token1 = str(row.get('token1', ''))
        if not token1 or token1 in ['', 'nan', 'None']: 
            continue
        
        revenue = float(str(row.get('revenue', 0)).replace(',', '.') or 0)
        date_val = row.get('date', datetime.now().date())
        if isinstance(date_val, str):
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y']:
                try:
                    date_val = datetime.strptime(date_val[:10], fmt).date()
                    break
                except: pass
            else: date_val = datetime.now().date()
        elif hasattr(date_val, 'date'): 
            date_val = date_val.date()
        
        prefix = extract_prefix(token1)
        if prefix:
            prefixes_set.add(prefix)
            rows_data.append({
                'token1': token1,
                'prefix': prefix,
                'revenue': revenue,
                'date': date_val
            })
    
    if not prefixes_set:
        return
    
    # ШАГ 2: ОДИН batch запрос для матчинга всех prefixes сразу
    prefixes_list = list(prefixes_set)
    prefix_to_campaign = {}
    
    # Разбиваем на батчи по 100 prefixes (чтобы не превысить лимит параметров)
    batch_size = 100
    for i in range(0, len(prefixes_list), batch_size):
        batch_prefixes = prefixes_list[i:i+batch_size]
        placeholders = ','.join([f"'{p}'" for p in batch_prefixes])
        
        matches = db.execute(text(f"""
            SELECT DISTINCT split_part(token1, '_', 1) as prefix, campaign_id
            FROM traffic_stats
            WHERE split_part(token1, '_', 1) IN ({placeholders})
        """)).fetchall()
        
        for prefix, campaign_id in matches:
            if campaign_id:
                prefix_to_campaign[prefix] = campaign_id
    
    # ШАГ 3: Классифицируем все строки используя маппинг
    matched_batch = []
    orphan_batch = []
    
    for row_data in rows_data:
        campaign_id = prefix_to_campaign.get(row_data['prefix'])
        
        if campaign_id:
            matched_batch.append(AdditionalMonetization(
                campaign_id=campaign_id,
                token1=row_data['token1'],
                date=row_data['date'],
                revenue=row_data['revenue'],
                source='sales'
            ))
            stats['matched'] += 1
        else:
            orphan_batch.append(Orphan(
                token1=row_data['token1'],
                date=row_data['date'],
                revenue=row_data['revenue'],
                source='sales'
            ))
            stats['orphans'] += 1
        
        stats['inserted'] += 1
    
    # ШАГ 4: Bulk insert всех matched и orphans
    if matched_batch:
        db.bulk_save_objects(matched_batch)
    if orphan_batch:
        db.bulk_save_objects(orphan_batch)
    
    db.commit()
