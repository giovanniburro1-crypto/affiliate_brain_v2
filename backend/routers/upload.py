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
    'Path': 'path', 'Rule': 'rule', 'Offer': 'offer', 'Offer ID': 'offer', 'Lander ID': 'lander_id',
    'Device Type': 'device_type', 'OS': 'os', 'OS Version': 'os_version',
    'Browser Name': 'browser_name', 'Country': 'country', 'Language': 'language',
    'Cost': 'cost', 'Payout': 'revenue', 'Conversion': 'conversions', 'Conversions': 'conversions',
}

# Варианты названий колонок (регистр и пробелы не важны)
COL_OS_ALIASES = ('os',)
COL_DEVICE_ALIASES = ('device type', 'devicetype', 'device_type')
COL_TRAFFIC_SOURCE_ALIASES = ('traffic source', 'trafficsource', 'traffic_source')
COL_CONVERSION_ALIASES = ('conversion', 'conversions')
COL_OFFER_ALIASES = ('offer id', 'offer_id', 'offerid')

def is_bot(token2):
    return 'bot' in str(token2).lower() if token2 else False

# Золотое правило: ВСЕ автоматические решения (подстановка OS/Device, маршрут monetisation и т.д.)
# применяются ТОЛЬКО при уверенности в ответе выше 95%.
# Относится и к изменениям в коде: при сомнениях более 5% — ищем решение вместе или перепроверяем.
CONFIDENCE_THRESHOLD = 0.95

def infer_os_and_device(token2, campaign):
    """
    Пытается определить OS и Device по token2/campaign.
    Возвращает (os, device_type, confidence).
    Подставляем только если confidence >= CONFIDENCE_THRESHOLD (>95%).
    """
    t = (str(token2 or '') + ' ' + str(campaign or '')).lower()
    if not t.strip():
        return None, None, 0.0
    os_val, dev_val = None, None
    conf = 0.0
    # OS: чёткие маркеры
    if 'android' in t and 'ios' not in t and 'iphone' not in t:
        os_val, conf = 'Android', 0.96
    elif ('ios' in t or 'iphone' in t or 'ipad' in t) and 'android' not in t:
        os_val, conf = 'iOS', 0.96
    # Device: чёткие маркеры
    if 'mobile' in t and 'desktop' not in t:
        dev_val = 'Mobile'
        if conf < 0.96:
            conf = 0.96
    elif 'desktop' in t and 'mobile' not in t:
        dev_val = 'Desktop'
        if conf < 0.96:
            conf = 0.96
    # Если нашли только device без os — уверенность только по device
    if dev_val and not os_val:
        conf = 0.96
    return os_val, dev_val, conf

def extract_prefix(token1):
    if not token1: return ''
    return str(token1).split('_')[0]

# Monetisation определяем по значению колонки Traffic Source (и при необходимости campaign), не по названию файла.
MONETISATION_MARKER = 'monetisation'

def _is_monetisation_by_column(traffic_source_val, campaign_val):
    """
    Доп. монетизация: в колонке Traffic Source (или campaign) есть 'monetisation'.
    Уверенность 0.96 — только при явном маркере. Иначе не применяем маршрут.
    """
    ts = (str(traffic_source_val or '')).lower()
    camp = (str(campaign_val or '')).lower()
    if MONETISATION_MARKER in ts or MONETISATION_MARKER in camp:
        return True, 0.96
    return False, 0.0

def _build_traffic_rename_map(df):
    """
    Строит маппинг колонок файла в имена полей.
    Учитывает точные имена из TRAFFIC_COLS и варианты для OS / Device Type
    (разный регистр, пробелы, DeviceType и т.д.).
    """
    rename = {}
    used_canonical = set()  # уже сопоставленные канонические имена (os, device_type)

    for col in df.columns:
        col_str = str(col).strip()
        if col_str in TRAFFIC_COLS:
            rename[col] = TRAFFIC_COLS[col_str]
            if TRAFFIC_COLS[col_str] in ('os', 'device_type', 'traffic_source', 'conversions', 'offer'):
                used_canonical.add(TRAFFIC_COLS[col_str])
            continue
        cl = col_str.lower().replace(' ', '')
        if cl in COL_OFFER_ALIASES and 'offer' not in used_canonical:
            rename[col] = 'offer'
            used_canonical.add('offer')
        elif cl == 'os' and 'os' not in used_canonical:
            rename[col] = 'os'
            used_canonical.add('os')
        elif cl in COL_DEVICE_ALIASES and 'device_type' not in used_canonical:
            rename[col] = 'device_type'
            used_canonical.add('device_type')
        elif cl in COL_TRAFFIC_SOURCE_ALIASES and 'traffic_source' not in used_canonical:
            rename[col] = 'traffic_source'
            used_canonical.add('traffic_source')
        elif cl in COL_CONVERSION_ALIASES and 'conversions' not in used_canonical:
            rename[col] = 'conversions'
            used_canonical.add('conversions')
    return rename

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
            original_columns = list(df.columns)
            rename_map = _build_traffic_rename_map(df)
            df = df.rename(columns=rename_map)
            _process_traffic(df, db, stats, original_columns=original_columns, rename_map=rename_map)
        stats['time'] = round(time.time() - start, 2)
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _process_monetisation_rows(db, stats, monetisation_rows):
    """
    Строки, где в колонке было 'monetisation' (уже отфильтрованы по уверенности >95%):
    матчим по prefix token1 → campaign_id; есть родитель → additional_monetization, нет → orphans.
    """
    prefixes_set = set()
    for r in monetisation_rows:
        p = extract_prefix(r['token1'])
        if p:
            prefixes_set.add(p)
    if not prefixes_set:
        return
    prefix_to_campaign = {}
    prefixes_list = list(prefixes_set)
    batch_size = 100
    for i in range(0, len(prefixes_list), batch_size):
        batch_prefixes = prefixes_list[i:i + batch_size]
        placeholders = ','.join([f"'{p}'" for p in batch_prefixes])
        matches = db.execute(text(f"""
            SELECT DISTINCT split_part(token1, '_', 1) as prefix, campaign_id
            FROM traffic_stats
            WHERE split_part(token1, '_', 1) IN ({placeholders})
        """)).fetchall()
        for prefix, campaign_id in matches:
            if campaign_id:
                prefix_to_campaign[prefix] = campaign_id
    matched_batch = []
    orphan_batch = []
    for r in monetisation_rows:
        prefix = extract_prefix(r['token1'])
        campaign_id = prefix_to_campaign.get(prefix) if prefix else None
        if campaign_id:
            matched_batch.append(AdditionalMonetization(
                campaign_id=campaign_id,
                token1=r['token1'],
                date=r['date'],
                revenue=r['revenue'],
                source=r['source']
            ))
            stats['matched'] += 1
        else:
            orphan_batch.append(Orphan(
                token1=r['token1'],
                date=r['date'],
                revenue=r['revenue'],
                source=r['source']
            ))
            stats['orphans'] += 1
    if matched_batch:
        db.bulk_save_objects(matched_batch)
    if orphan_batch:
        db.bulk_save_objects(orphan_batch)
    db.commit()

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

def _process_traffic(df, db, stats, original_columns=None, rename_map=None):
    stats['total'] = len(df)
    stats['upload_columns'] = original_columns or list(df.columns)
    stats['had_os_column'] = 'os' in df.columns
    stats['had_device_column'] = 'device_type' in df.columns
    stats['rows_with_os'] = 0
    stats['rows_with_device'] = 0
    batch = []
    monetisation_rows = []  # строки, где в колонке (traffic_source/campaign) есть 'monetisation' — только при уверенности >95%
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
        # Conversion: из колонки Conversion/Conversions или по правилу «везде где payout — есть conversion»
        conv_raw = row.get('conversions')
        if conv_raw is not None and pd.notna(conv_raw):
            try:
                conversions = max(0, int(float(conv_raw)))
            except (ValueError, TypeError):
                conversions = 1 if revenue > 0 else 0
        else:
            conversions = 1 if revenue > 0 else 0
        if revenue > 0 and conversions < 1:
            conversions = 1  # в БД конверсия везде, где есть пейаут
        traffic_source_val = row.get('traffic_source')
        campaign_val = row.get('campaign')
        # Маршрут monetisation: только по значению колонки и только при уверенности >95%
        is_monet, mon_conf = _is_monetisation_by_column(traffic_source_val, campaign_val)
        if is_monet and mon_conf >= CONFIDENCE_THRESHOLD:
            token1_val = str(row.get('token1', '')).strip() if pd.notna(row.get('token1')) else ''
            if token1_val and token1_val not in ('', 'nan', 'None'):
                monetisation_rows.append({
                    'token1': token1_val,
                    'date': date_val,
                    'revenue': revenue,
                    'source': str(traffic_source_val or 'monetisation')[:100]
                })
                stats['inserted'] += 1
            continue
        os_val = str(row.get('os', '')).strip()[:100] if pd.notna(row.get('os')) and str(row.get('os', '')).strip() else None
        device_val = str(row.get('device_type', '')).strip()[:100] if pd.notna(row.get('device_type')) and str(row.get('device_type', '')).strip() else None
        if os_val is not None:
            stats['rows_with_os'] += 1
        if device_val is not None:
            stats['rows_with_device'] += 1
        if os_val is None or device_val is None:
            campaign_str = str(row.get('campaign', '')) if pd.notna(row.get('campaign')) else ''
            inferred_os, inferred_dev, confidence = infer_os_and_device(token2, campaign_str)
            if confidence >= CONFIDENCE_THRESHOLD:
                if os_val is None and inferred_os:
                    os_val = inferred_os
                if device_val is None and inferred_dev:
                    device_val = inferred_dev
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
            os=os_val,
            device_type=device_val,
            cost=float(row.get('cost', 0) or 0), revenue=revenue,
            conversions=conversions
        ))
        stats['inserted'] += 1
        if len(batch) >= 5000:
            _save_traffic_batch(db, batch)
            batch = []
    if batch:
        _save_traffic_batch(db, batch)
    # Доп. монетизация из колонки: в additional_monetization при найденном родителе, иначе в orphans
    if monetisation_rows:
        _process_monetisation_rows(db, stats, monetisation_rows)


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
