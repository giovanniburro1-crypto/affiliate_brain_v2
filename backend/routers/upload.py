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
    'Affiliate Network': 'affiliate_network',
    'Device Type': 'device_type', 'OS': 'os', 'OS Version': 'os_version',
    'Browser Name': 'browser_name', 'Country': 'country', 'Language': 'language',
    'Cost': 'cost', 'Payout': 'revenue', 'Conversion': 'conversions', 'Conversions': 'conversions',
}

# Варианты названий колонок (регистр и пробелы не важны)
COL_OS_ALIASES = ('os',)
COL_DEVICE_ALIASES = ('device type', 'devicetype', 'device_type')

EXPECTED_TRAFFIC_COLS_SET = {
    "Click ID", "Date Click", "Campaign ID", "Campaign", "Path", "Rule", 
    "Offer ID", "Lander ID", "Traffic Source", "Affiliate Network", 
    "Device Type", "Country", "OS", "OS Version", "Browser Name", "Language", 
    "Payout", "Conversion", "Cost", "Token 1", "Token 2", "Token 3", 
    "Token 4", "Token 5", "Token 6", "Token 7", "Token 8", "Token 9", "Token 10"
}
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


def _sale_click_id(token1: str, date_val, col2: str, revenue: float) -> str:
    """
    Уникальный click_id для sale-строки: sale_PREFIX_YYYYMMDD_suffix;col2_revenue
    Пример: sale_1338_20260127_i_bb;add_0.4
    Включает PREFIX чтобы избежать коллизий между разными кампаниями
    """
    date_compact = date_val.strftime('%Y%m%d') if hasattr(date_val, 'strftime') else str(date_val).replace('-', '')[:8]
    token1_str = str(token1).strip()
    
    # Разделяем на prefix и suffix
    if '_' in token1_str:
        prefix = token1_str.split('_', 1)[0]
        suffix = token1_str.split('_', 1)[1]
    else:
        prefix = token1_str
        suffix = ''
    
    revenue_safe = str(revenue).replace(',', '.') if revenue is not None else '0'
    col2_safe = (str(col2 or '').strip().replace(';', '')).replace(' ', '')[:50]
    
    if col2_safe:
        cid = f"sale_{prefix}_{date_compact}_{suffix};{col2_safe}_{revenue_safe}"
    else:
        cid = f"sale_{prefix}_{date_compact}_{suffix}_{revenue_safe}"
    return cid[:255]

# Monetisation определяем по значению колонки Traffic Source (и при необходимости campaign), не по названию файла.
MONETISATION_MARKER = 'monetisation'
_monet_log_sampled = 0

def _is_monetisation_by_column(traffic_source_val, campaign_val):
    """
    Доп. монетизация: в колонке Traffic Source (или campaign) есть 'monetisation' или 'monetization'.
    Уверенность 0.96 — только при явном маркере. Иначе не применяем маршрут.
    """
    ts = (str(traffic_source_val or '')).lower()
    camp = (str(campaign_val or '')).lower()
    markers = ['monetisation', 'monetization']
    if any(m in ts for m in markers) or any(m in camp for m in markers):
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

from typing import List

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    start = time.time()
    stats = {'total': 0, 'inserted': 0, 'bots': 0, 'matched': 0, 'orphans': 0, 'errors': []}
    try:
        for file in files:
            content = await file.read()
            filename = file.filename.lower()
            if 'sale' in filename:
                df = _read_sales_file(content, filename)
                _process_sales(df, db, stats)
            else:
                try:
                    engine = 'xlrd' if filename.endswith('.xls') else 'openpyxl'
                    df = pd.read_excel(io.BytesIO(content), engine=engine)
                except Exception:
                    # Fallback to CSV: try semicolon first (tracker exports), then comma
                    try:
                        df = pd.read_csv(io.BytesIO(content), sep=';')
                        if len(df.columns) <= 1:
                            # Semicolon didn't work, try comma
                            df = pd.read_csv(io.BytesIO(content), sep=',')
                    except Exception:
                        try:
                            df = pd.read_csv(io.BytesIO(content), sep=',')
                        except Exception as csv_err:
                            import traceback
                            with open("/tmp/upload_err.log", "w") as _err:
                                _err.write(traceback.format_exc())
                            raise ValueError(f"Failed to read file {filename} as both Excel and CSV. Error: {str(csv_err)}")
                
                # Строгая проверка шаблона (если это не sale-файл)
                uploaded_cols = set(df.columns)
                missing_cols = EXPECTED_TRAFFIC_COLS_SET - uploaded_cols
                extra_cols = uploaded_cols - EXPECTED_TRAFFIC_COLS_SET
                
                if missing_cols or extra_cols:
                    error_msg = "Файл не соответствует шаблону БД."
                    if extra_cols: error_msg += f" Лишние колонки: {extra_cols}."
                    if missing_cols: error_msg += f" Отсутствуют: {missing_cols}."
                    raise ValueError(error_msg)

                original_columns = list(df.columns)
                rename_map = _build_traffic_rename_map(df)
                df = df.rename(columns=rename_map)
                # Deduplicate columns: if mapping created duplicates, keep only the first one to prevent Series errors later
                df = df.loc[:, ~df.columns.duplicated()]
                _process_traffic(df, db, stats, original_columns=original_columns, rename_map=rename_map)
                db.commit()
                
        # После загрузки любых файлов - пытаемся сматчить всех старых Orphans
        _rematch_orphans(db, stats)
        
        stats['time'] = round(time.time() - start, 2)
        return {"success": True, "stats": stats}
    except ValueError as ve:
        import traceback
        with open("/tmp/upload_err.log", "w") as _err:
            _err.write(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        with open("/tmp/upload_err.log", "w") as _err:
            _err.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

def _process_monetisation_rows(db, stats, monetisation_rows):
    """
    Строки, где в колонке было 'monetisation' (уже отфильтрованы по уверенности >95%):
    матчим по prefix token1 → campaign_id; есть родитель → additional_monetization, нет → orphans.
    INSERT с ON CONFLICT (click_id) DO UPDATE — повторяющиеся перезаписываются.
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
        placeholders = ','.join([f"'{str(p).replace(chr(39), chr(39)+chr(39))}'" for p in batch_prefixes])
        matches = db.execute(text(f"""
            SELECT DISTINCT
                CASE WHEN instr(token1, '_') > 0 THEN substr(token1, 1, instr(token1, '_') - 1) ELSE token1 END as prefix,
                campaign_id
            FROM traffic_stats
            WHERE CASE WHEN instr(token1, '_') > 0 THEN substr(token1, 1, instr(token1, '_') - 1) ELSE token1 END IN ({placeholders})
        """)).fetchall()
        for prefix, campaign_id in matches:
            if campaign_id:
                prefix_to_campaign[prefix] = campaign_id
    matched = []
    orphan_batch = []
    for r in monetisation_rows:
        prefix = extract_prefix(r['token1'])
        campaign_id = prefix_to_campaign.get(prefix) if prefix else None
        if campaign_id:
            matched.append({**r, 'campaign_id': campaign_id})
            stats['matched'] += 1
        else:
            orphan_batch.append(Orphan(
                token1=r['token1'],
                date=r['date'],
                revenue=r['revenue'],
                source=r['source']
            ))
            stats['orphans'] += 1
    if orphan_batch:
        db.bulk_save_objects(orphan_batch)
    if matched:
        # Убираем дубли внутри батча по click_id (оставляем последнее вхождение)
        seen_cid = {}
        for r in matched:
            seen_cid[r['click_id']] = r
        matched_deduped = list(seen_cid.values())
        matched = matched_deduped
        _insert_monetisation_with_upsert(db, matched)
    db.commit()

def _rematch_orphans(db, stats):
    """
    Сканирует таблицу orphans и ищет родителей в traffic_stats.
    Вызывается в конце каждой загрузки.
    """
    orphans = db.execute(text("SELECT id, token1, date, revenue, source FROM orphans")).fetchall()
    if not orphans:
        return
        
    prefixes_set = set()
    orphan_map = []
    for r in orphans:
        p = extract_prefix(r[1]) # token1
        if p:
            prefixes_set.add(p)
            orphan_map.append({'id': r[0], 'token1': r[1], 'prefix': p, 'date': r[2], 'revenue': r[3], 'source': r[4]})
            
    if not prefixes_set:
        return
        
    prefixes_list = list(prefixes_set)
    prefix_to_campaign = {}
    batch_size = 100
    for i in range(0, len(prefixes_list), batch_size):
        batch_prefixes = prefixes_list[i:i+batch_size]
        placeholders = ','.join([f"'{str(p).replace(chr(39), chr(39)+chr(39))}'" for p in batch_prefixes])
        
        matches = db.execute(text(f"""
            SELECT DISTINCT
                CASE WHEN instr(token1, '_') > 0 THEN substr(token1, 1, instr(token1, '_') - 1) ELSE token1 END as prefix,
                campaign_id
            FROM traffic_stats
            WHERE CASE WHEN instr(token1, '_') > 0 THEN substr(token1, 1, instr(token1, '_') - 1) ELSE token1 END IN ({placeholders})
        """)).fetchall()
        
        for prefix, campaign_id in matches:
            if campaign_id:
                prefix_to_campaign[prefix] = campaign_id
                
    matched_ids = []
    matched_records = []
    for o in orphan_map:
        campaign_id = prefix_to_campaign.get(o['prefix'])
        if campaign_id:
            matched_ids.append(o['id'])
            
            # Парсим дату для _sale_click_id
            date_val = o['date']
            from datetime import datetime
            if isinstance(date_val, str):
                try: date_val = datetime.strptime(date_val[:10], '%Y-%m-%d').date()
                except: date_val = datetime.now().date()
            
            click_id = _sale_click_id(o['token1'], date_val, o['source'], o['revenue'])
            matched_records.append({
                'click_id': click_id,
                'campaign_id': campaign_id,
                'token1': o['token1'],
                'date': date_val,
                'revenue': o['revenue'],
                'source': o['source']
            })
            
    if matched_records:
        # Вставляем сматченные записи
        _insert_monetisation_with_upsert(db, matched_records)
        
        # Удаляем их из orphans
        placeholders_ids = ','.join([str(id) for id in matched_ids])
        db.execute(text(f"DELETE FROM orphans WHERE id IN ({placeholders_ids})"))
        db.commit()
        stats['rematched_orphans'] = len(matched_records)



def _insert_monetisation_with_upsert(db, rows):
    """Bulk INSERT ... ON CONFLICT (click_id) DO UPDATE SET ..."""
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        values = []
        for r in batch:
            cid = str(r['click_id']).replace("'", "''")
            camp = str(r['campaign_id']).replace("'", "''")
            t1 = str(r['token1']).replace("'", "''")
            d = r['date']
            rev = float(r['revenue'])
            src = str(r['source']).replace("'", "''")
            values.append(f"('{cid}', '{camp}', '{t1}', '{d}', {rev}, '{src}')")
        sql = f"""
            INSERT OR REPLACE INTO additional_monetization (click_id, campaign_id, token1, date, revenue, source)
            VALUES {', '.join(values)}
        """
        db.execute(text(sql))

def _read_sales_file(content, filename=''):
    fname = (filename or '').lower()
    if fname.endswith(('.xlsx', '.xls')):
        engine = 'xlrd' if fname.endswith('.xls') else 'openpyxl'
        try:
            return pd.read_excel(io.BytesIO(content), engine=engine)
        except Exception:
            pass
    try:
        return pd.read_excel(io.BytesIO(content), engine='openpyxl')
    except Exception:
        pass
    for sep in [';', ',', '	']:
        for enc in ['utf-8', 'cp1251', 'latin-1']:
            try:
                df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=enc)
                if len(df.columns) > 1:
                    return df
            except Exception:
                pass
            try:
                df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=enc, header=None)
                if len(df.columns) > 1:
                    return df
            except Exception:
                pass
    raise ValueError("Cannot read sales file as Excel or CSV")

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
            if token1_val:
                token1_val = token1_val.replace('{', '').replace('}', '').replace('"', '').replace("'", '')
            if token1_val and token1_val not in ('', 'nan', 'None'):
                click_id_val = str(row.get('click_id', '')).strip() if pd.notna(row.get('click_id')) else ''
                if not click_id_val:
                    click_id_val = f"mon_{token1_val}_{date_val}"
                monetisation_rows.append({
                    'click_id': click_id_val[:255],
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
            token1=(str(row.get('token1', '')).replace('{', '').replace('}', '').replace('"', '').replace("'", '') if pd.notna(row.get('token1')) else None),
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
            affiliate_network=str(row.get('affiliate_network', ''))[:255] if pd.notna(row.get('affiliate_network')) else None,
            path=str(row.get('path', ''))[:255] if pd.notna(row.get('path')) else None,
            rule=str(row.get('rule', ''))[:255] if pd.notna(row.get('rule')) else None,
            offer=str(row.get('offer', ''))[:255] if pd.notna(row.get('offer')) else None,
            lander_id=str(row.get('lander_id', ''))[:100] if pd.notna(row.get('lander_id')) else None,
            os=os_val,
            device_type=device_val,
            os_version=str(row.get('os_version', ''))[:50] if pd.notna(row.get('os_version')) else None,
            browser_name=str(row.get('browser_name', ''))[:100] if pd.notna(row.get('browser_name')) else None,
            country=str(row.get('country', ''))[:10] if pd.notna(row.get('country')) else None,
            language=str(row.get('language', ''))[:20] if pd.notna(row.get('language')) else None,
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
        affiliate_network = escape(getattr(obj, 'affiliate_network', None))
        os_val = escape(getattr(obj, 'os', None))
        device_type_val = escape(getattr(obj, 'device_type', None))
        path = escape(getattr(obj, 'path', None))
        rule = escape(getattr(obj, 'rule', None))
        offer = escape(getattr(obj, 'offer', None))
        lander_id = escape(getattr(obj, 'lander_id', None))
        os_version = escape(getattr(obj, 'os_version', None))
        browser_name = escape(getattr(obj, 'browser_name', None))
        country = escape(getattr(obj, 'country', None))
        language = escape(getattr(obj, 'language', None))
        cost = getattr(obj, 'cost', 0) or 0
        revenue = getattr(obj, 'revenue', 0) or 0
        conversions = getattr(obj, 'conversions', 0) or 0
        
        values_parts.append(
            f"({click_id}, {campaign_id}, {campaign}, {date_val}, {token1}, {token2}, "
            f"{token3}, {token4}, {token5}, {token6}, {token7}, {token8}, {token9}, {token10}, "
            f"{traffic_source}, {affiliate_network}, {os_val}, {device_type_val}, "
            f"{path}, {rule}, {offer}, {lander_id}, {os_version}, {browser_name}, {country}, {language}, "
            f"{cost}, {revenue}, {conversions})"
        )
    
    # Bulk INSERT с ON CONFLICT REPLACE
    sql = f"""
        INSERT OR REPLACE INTO traffic_stats 
        (click_id, campaign_id, campaign, date, token1, token2, token3, token4, token5, 
         token6, token7, token8, token9, token10, traffic_source, affiliate_network, os, device_type, 
         path, rule, offer, lander_id, os_version, browser_name, country, language, cost, revenue, conversions)
        VALUES {', '.join(values_parts)}
    """
    
    try:
        db.execute(text(sql))
    except Exception as e:
        # Если SQL слишком большой или другая ошибка - fallback на старый метод
        try:
            db.bulk_save_objects(unique_batch)
        except IntegrityError:
            # Игнорируем дубликаты
            pass

def _process_sales(df, db, stats):
    """
    Универсальная обработка файлов продаж (sale):
    - Матричный формат (Sale+) с несколькими категориями монетизации (add, BB, bb2, nbb, i_p, etc.)
    - Стандартный 5-колоночный (Date; Token1; Col2; Clicks; Revenue)
    - T1/T5 формат (T1; T5; Clicks; CPC; Revenue)
    - 4-колоночный (Token1; Clicks; Payout; Revenue)
    - Fallback
    """
    df = df.dropna(how='all').copy()
    stats['total'] = len(df)
    
    # 1. Загружаем все известные campaign_id
    rows = db.execute(text("SELECT DISTINCT campaign_id FROM traffic_stats WHERE campaign_id IS NOT NULL AND campaign_id != ''")).fetchall()
    known_campaigns = {str(r[0]) for r in rows if r[0]}
    
    # 2. Определяем формат и извлекаем нормализованные записи
    cols_str = [str(c).strip() for c in df.columns]
    cols_lower = [c.lower() for c in cols_str]
    default_date = datetime.now().date()
    
    date_col = None
    id_col = None
    for i, cl in enumerate(cols_lower):
        if cl in ('date', 'дата') and date_col is None:
            date_col = df.columns[i]
        elif cl in ('id', 'token', 'token1', 'subid', 'sub_id', 'sub id', 't1') and id_col is None:
            id_col = df.columns[i]
            
    if id_col is None and date_col is not None and len(df.columns) > 1:
        id_col = df.columns[1]
        
    records = []
    
    # Проверяем матричный формат (Sale+)
    is_matrix = False
    if id_col is not None:
        exclude_cols = {date_col, id_col}
        candidate_rev_cols = [c for c in df.columns if c not in exclude_cols and str(c).lower() not in (
            'clicks', 'cpc', 'payout', 'conversions', 'cost', 'spend', 'cr', 'epc', 'date_str', 'camp'
        )]
        if len(candidate_rev_cols) >= 2 or (len(candidate_rev_cols) == 1 and any(cl in ('add', 'bb', 'nbb', 'i_p', 'rev') for cl in [str(c).lower() for c in candidate_rev_cols])):
            is_matrix = True
            for _, row in df.iterrows():
                raw_d = row[date_col] if date_col else default_date
                row_date = default_date
                if hasattr(raw_d, 'date'):
                    row_date = raw_d.date()
                elif isinstance(raw_d, str):
                    for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y', '%Y/%m/%d', '%m/%d/%Y']:
                        try:
                            row_date = datetime.strptime(raw_d[:10], fmt).date()
                            break
                        except ValueError:
                            pass
                
                raw_tok = str(row[id_col]).strip() if pd.notna(row[id_col]) else ''
                raw_tok = raw_tok.replace('{', '').replace('}', '').replace('"', '').replace("'", '')
                if not raw_tok or raw_tok.lower() in ('nan', 'none', '', 'итого', 'date', 'sub id'):
                    continue
                    
                for r_col in candidate_rev_cols:
                    val = row[r_col]
                    if pd.isna(val):
                        continue
                    try:
                        val_float = float(str(val).replace(',', '.'))
                    except (ValueError, TypeError):
                        continue
                    if val_float == 0:
                        continue
                    records.append({
                        'date': row_date,
                        'raw_token': raw_tok,
                        'stream': str(r_col).strip(),
                        'col2': '',
                        'revenue': round(val_float, 4)
                    })

    if not is_matrix:
        # Проверяем классические форматы
        if len(cols_lower) >= 5 and cols_lower[0] in ('t1', 'token1', 'token 1') and 'date' not in cols_lower[0]:
            for _, row in df.iterrows():
                raw_tok = str(row.iloc[0]).strip().replace('{', '').replace('}', '').replace('"', '').replace("'", '')
                if not raw_tok or raw_tok.lower() in ('nan', 'none', '', 'итого', 'sub id', 't1'):
                    continue
                col2 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                try: rev = float(str(row.iloc[-1]).replace(',', '.'))
                except: continue
                if rev == 0: continue
                records.append({'date': default_date, 'raw_token': raw_tok, 'stream': '', 'col2': col2, 'revenue': rev})
        elif len(df.columns) >= 5:
            for _, row in df.iterrows():
                raw_d = row.iloc[0]
                row_date = default_date
                if hasattr(raw_d, 'date'): row_date = raw_d.date()
                elif isinstance(raw_d, str):
                    for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y']:
                        try:
                            row_date = datetime.strptime(raw_d[:10], fmt).date()
                            break
                        except: pass
                raw_tok = str(row.iloc[1]).strip().replace('{', '').replace('}', '').replace('"', '').replace("'", '')
                if not raw_tok or raw_tok.lower() in ('nan', 'none', '', 'итого', 'sub id', 'date'):
                    continue
                col2 = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
                try: rev = float(str(row.iloc[4]).replace(',', '.'))
                except: continue
                if rev == 0: continue
                records.append({'date': row_date, 'raw_token': raw_tok, 'stream': '', 'col2': col2, 'revenue': rev})
        else:
            for _, row in df.iterrows():
                raw_tok = str(row.iloc[0]).strip().replace('{', '').replace('}', '').replace('"', '').replace("'", '')
                if not raw_tok or raw_tok.lower() in ('nan', 'none', '', 'итого'): continue
                col2 = str(row.iloc[1]).strip() if len(df.columns) > 2 and pd.notna(row.iloc[1]) else ''
                try: rev = float(str(row.iloc[-1]).replace(',', '.'))
                except: continue
                if rev == 0: continue
                records.append({'date': default_date, 'raw_token': raw_tok, 'stream': '', 'col2': col2, 'revenue': rev})

    # 3. Матчинг и группировка
    orphan_batch = []
    seen_cid = {}
    
    for idx, r in enumerate(records, start=1):
        raw_tok = r['raw_token']
        stream = r['stream']
        parts = raw_tok.split('_')
        camp_id = None
        norm_token = raw_tok
        partner = ''
        geo = ''
        
        if len(parts) >= 3 and parts[-1] in known_campaigns:
            camp_id = parts[-1]
            partner = parts[0]
            geo = parts[1]
            norm_token = f"{camp_id}_{geo}_{stream}" if stream else f"{camp_id}_{geo}"
        elif parts[0] in known_campaigns:
            camp_id = parts[0]
            suffix = '_'.join(parts[1:])
            norm_token = f"{camp_id}_{suffix}_{stream}" if stream else f"{camp_id}_{suffix}"
        elif raw_tok in known_campaigns:
            camp_id = raw_tok
            norm_token = f"{camp_id}_{stream}" if stream else camp_id
        else:
            for p in parts:
                if p in known_campaigns:
                    camp_id = p
                    norm_token = f"{camp_id}_{stream}" if stream else f"{raw_tok}_{stream}"
                    break
        
        if not camp_id:
            norm_token = f"{raw_tok}_{stream}" if stream else raw_tok

        date_compact = r['date'].strftime('%Y%m%d') if hasattr(r['date'], 'strftime') else str(r['date']).replace('-', '')[:8]
        rev_safe = str(r['revenue']).replace(',', '.')
        
        if camp_id:
            meta_parts = [p for p in [partner, geo, stream, r['col2']] if p]
            meta_tag = '_'.join(meta_parts) if meta_parts else str(idx)
            cid = f"sale_{camp_id}_{date_compact}_{meta_tag}_{rev_safe}"[:255]
            if cid in seen_cid:
                cid = f"{cid}_{idx}"[:255]
            
            seen_cid[cid] = {
                'click_id': cid,
                'campaign_id': camp_id,
                'token1': norm_token,
                'date': r['date'],
                'revenue': r['revenue'],
                'source': 'sales'
            }
            stats['matched'] += 1
        else:
            orphan_batch.append(Orphan(
                token1=norm_token,
                date=r['date'],
                revenue=r['revenue'],
                source='sales'
            ))
            stats['orphans'] += 1
            
        stats['inserted'] += 1

    if seen_cid:
        _insert_monetisation_with_upsert(db, list(seen_cid.values()))
    if orphan_batch:
        db.bulk_save_objects(orphan_batch)
    db.commit()