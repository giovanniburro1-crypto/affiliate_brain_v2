#!/usr/bin/env python3
"""
TOP-5 Analysis Bot - Token Pattern Analysis
Использует FP-Growth для поиска скрытых паттернов в токенах
"""

import sys
import json
import pandas as pd
import mysql.connector
from mlxtend.frequent_patterns import fpgrowth, association_rules
from mlxtend.preprocessing import TransactionEncoder
import numpy as np
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

# =====================================================
# DATABASE CONNECTION
# =====================================================

def get_db_connection():
    """Подключение к MySQL"""
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'top5_analysis')
    )

# =====================================================
# DATA LOADING
# =====================================================

def load_campaign_data(campaign_id, days=30):
    """Загрузить данные кампании из БД"""
    conn = get_db_connection()
    
    query = f"""
        SELECT *
        FROM campaign_data
        WHERE campaign_id = %s
            AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    """
    
    df = pd.read_sql(query, conn, params=(campaign_id, days))
    conn.close()
    
    return df

# =====================================================
# FP-GROWTH ANALYSIS
# =====================================================

def analyze_token_patterns(df):
    """
    Глубокий анализ токенов с использованием FP-Growth
    
    Returns:
        dict: Найденные паттерны с метриками
    """
    
    if len(df) < 10:
        return {
            'patterns': [],
            'message': 'Insufficient data for pattern mining'
        }
    
    # Шаг 1: Создание транзакций
    transactions = []
    
    for idx, row in df.iterrows():
        transaction = []
        
        # Добавляем токены
        for i in range(1, 11):
            token_col = f'token_{i}'
            if pd.notna(row.get(token_col)) and str(row[token_col]).strip():
                transaction.append(f'T{i}_{row[token_col]}')
        
        # Добавляем категориальные поля
        if pd.notna(row.get('device_type')):
            transaction.append(f'Device_{row["device_type"]}')
        
        if pd.notna(row.get('os')):
            transaction.append(f'OS_{row["os"]}')
        
        if pd.notna(row.get('country')):
            transaction.append(f'Country_{row["country"]}')
        
        # Метка конверсии
        if row.get('conversion', 0) > 0:
            transaction.append('CONVERTED')
        
        if transaction:
            transactions.append(transaction)
    
    if not transactions:
        return {
            'patterns': [],
            'message': 'No valid transactions found'
        }
    
    # Шаг 2: Кодирование транзакций
    te = TransactionEncoder()
    te_ary = te.fit(transactions).transform(transactions)
    df_encoded = pd.DataFrame(te_ary, columns=te.columns_)
    
    # Шаг 3: FP-Growth
    try:
        frequent_itemsets = fpgrowth(
            df_encoded,
            min_support=0.02,  # Минимум 2% транзакций
            use_colnames=True
        )
        
        if frequent_itemsets.empty:
            return {
                'patterns': [],
                'message': 'No frequent patterns found'
            }
        
        # Шаг 4: Ассоциативные правила
        rules = association_rules(
            frequent_itemsets,
            metric="confidence",
            min_threshold=0.6
        )
        
        # Шаг 5: Фильтруем правила с CONVERTED
        conversion_rules = rules[
            rules['consequents'].apply(lambda x: 'CONVERTED' in x)
        ].copy()
        
        if conversion_rules.empty:
            return {
                'patterns': [],
                'message': 'No conversion patterns found'
            }
        
        # Шаг 6: Расчёт score для паттернов
        conversion_rules['pattern_score'] = (
            conversion_rules['lift'] *
            conversion_rules['confidence'] *
            conversion_rules['support']
        )
        
        # Шаг 7: Топ паттерны
        top_patterns = conversion_rules.nlargest(10, 'pattern_score')
        
        # Шаг 8: Формирование результатов
        patterns = []
        
        for _, rule in top_patterns.iterrows():
            antecedents = list(rule['antecedents'])
            
            # Фильтруем данные по паттерну
            pattern_mask = df.apply(
                lambda row: all(check_condition(row, cond) for cond in antecedents),
                axis=1
            )
            pattern_data = df[pattern_mask]
            
            if len(pattern_data) > 0:
                # Вычисляем метрики
                total_clicks = len(pattern_data)
                total_conversions = pattern_data['conversion'].sum()
                total_revenue = (pattern_data['conversion'] * pattern_data['payout']).sum()
                total_cost = pattern_data['cost'].sum()
                
                roi = 0
                if total_cost > 0:
                    roi = ((total_revenue - total_cost) / total_cost) * 100
                
                cr = 0
                if total_clicks > 0:
                    cr = (total_conversions / total_clicks) * 100
                
                patterns.append({
                    'pattern': ' AND '.join(antecedents),
                    'conditions': antecedents,
                    'clicks': int(total_clicks),
                    'conversions': int(total_conversions),
                    'revenue': float(total_revenue),
                    'cost': float(total_cost),
                    'roi': round(float(roi), 2),
                    'cr': round(float(cr), 2),
                    'lift': round(float(rule['lift']), 2),
                    'confidence': round(float(rule['confidence']), 2),
                    'support': round(float(rule['support']), 4),
                    'score': round(float(rule['pattern_score']), 4)
                })
        
        return {
            'patterns': patterns,
            'total_patterns_found': len(patterns),
            'analysis_date': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'patterns': [],
            'error': str(e),
            'message': 'Error during pattern mining'
        }

# =====================================================
# HELPER FUNCTIONS
# =====================================================

def check_condition(row, condition):
    """Проверка условия для строки"""
    
    if condition.startswith('T'):
        # Токен: T1_value, T2_value, etc.
        parts = condition.split('_', 1)
        token_num = int(parts[0][1:])
        token_value = parts[1]
        return str(row.get(f'token_{token_num}', '')) == token_value
    
    elif condition.startswith('Device_'):
        return str(row.get('device_type', '')) == condition.split('_', 1)[1]
    
    elif condition.startswith('OS_'):
        return str(row.get('os', '')) == condition.split('_', 1)[1]
    
    elif condition.startswith('Country_'):
        return str(row.get('country', '')) == condition.split('_', 1)[1]
    
    return False

# =====================================================
# ANOMALY DETECTION
# =====================================================

def detect_anomalies(df):
    """Выявление аномальных токен-значений"""
    
    anomalies = []
    total_clicks = len(df)
    
    # Анализируем каждый токен
    for i in range(1, 11):
        token_col = f'token_{i}'
        
        if token_col not in df.columns:
            continue
        
        # Группируем по значениям токена
        token_groups = df.groupby(token_col).agg({
            'click': 'count',
            'conversion': 'sum',
            'cost': 'sum'
        }).reset_index()
        
        token_groups.columns = ['value', 'clicks', 'conversions', 'cost']
        
        # Вычисляем метрики
        token_groups['frequency'] = (token_groups['clicks'] / total_clicks) * 100
        token_groups['cr'] = np.where(
            token_groups['clicks'] > 0,
            (token_groups['conversions'] / token_groups['clicks']) * 100,
            0
        )
        
        # Общий CR для сравнения
        overall_cr = (df['conversion'].sum() / total_clicks) * 100 if total_clicks > 0 else 0
        
        # Ищем аномалии: редкие (< 5%) но с высоким CR (> 2× общего)
        for _, row in token_groups.iterrows():
            if row['frequency'] < 5 and row['cr'] > (overall_cr * 2) and row['conversions'] > 0:
                anomalies.append({
                    'token': f'Token{i}',
                    'value': str(row['value']),
                    'frequency': round(float(row['frequency']), 2),
                    'clicks': int(row['clicks']),
                    'conversions': int(row['conversions']),
                    'cr': round(float(row['cr']), 2),
                    'cr_vs_avg': round(float(row['cr'] / overall_cr), 2) if overall_cr > 0 else 0,
                    'type': 'rare_high_conversion'
                })
    
    return sorted(anomalies, key=lambda x: x['cr_vs_avg'], reverse=True)

# =====================================================
# MAIN EXECUTION
# =====================================================

def main():
    """Main entry point"""
    
    if len(sys.argv) < 2:
        print(json.dumps({
            'error': 'Usage: analyze_tokens.py <campaign_id> [days]'
        }))
        sys.exit(1)
    
    campaign_id = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    try:
        # Загружаем данные
        df = load_campaign_data(campaign_id, days)
        
        if df.empty:
            print(json.dumps({
                'patterns': [],
                'anomalies': [],
                'message': 'No data found for campaign'
            }))
            sys.exit(0)
        
        # Анализ паттернов
        patterns_result = analyze_token_patterns(df)
        
        # Поиск аномалий
        anomalies = detect_anomalies(df)
        
        # Объединяем результаты
        result = {
            **patterns_result,
            'anomalies': anomalies,
            'total_anomalies': len(anomalies)
        }
        
        # Выводим JSON
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({
            'error': str(e),
            'patterns': [],
            'anomalies': []
        }))
        sys.exit(1)

if __name__ == '__main__':
    main()
