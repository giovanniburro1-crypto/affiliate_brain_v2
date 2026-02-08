# АРХИТЕКТУРА СИСТЕМЫ TOP-5 ANALYSIS BOT

## ОБЗОР

TOP-5 Analysis Bot — это полнофункциональная система анализа арбитражных кампаний, состоящая из трёх основных компонентов:

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                       │
│  - Отображение TOP-5 кампаний                             │
│  - Интерактивные элементы управления                       │
│  - Визуализация метрик и трендов                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/REST API
┌──────────────────────▼──────────────────────────────────────┐
│                   Backend (Node.js/Express)                 │
│  - REST API endpoints                                       │
│  - Бизнес-логика отбора кампаний                          │
│  - Система обучения (reinforcement learning)               │
│  - Интеграция с Python скриптами                          │
└──────┬────────────────────────────────────┬────────────────┘
       │                                    │
       │ SQL Queries                        │ Subprocess Calls
       │                                    │
┌──────▼────────────┐            ┌─────────▼──────────────────┐
│   MySQL Database  │            │  Python Scripts            │
│  - campaign_data  │            │  - analyze_tokens.py       │
│  - shown_campaigns│            │  - calc_volatility.py      │
│  - user_actions   │            │  - FP-Growth алгоритм      │
│  - learning_weights│           │  - Anomaly detection       │
└───────────────────┘            └────────────────────────────┘
```

## КОМПОНЕНТЫ

### 1. FRONTEND (React)

**Расположение:** `/frontend`

**Основные файлы:**
- `src/components/Top5Display.jsx` — главный компонент отображения
- `src/components/Top5Display.css` — стили
- `src/App.jsx` — корневой компонент приложения

**Функции:**
- Отображение TOP-5 кампаний в реальном времени
- Выбор действий (SCALE/HOLD/OPTIMIZE)
- Настройка периодов скрытия
- Вызов AI Council

**Технологии:**
- React 18+
- Fetch API для HTTP запросов
- CSS Grid/Flexbox для layout

---

### 2. BACKEND (Node.js/Express)

**Расположение:** `/backend`

**Основные файлы:**
- `server.js` — главный сервер
- `routes/` — API маршруты (если расширять)
- `services/` — бизнес-логика (если расширять)

**API Endpoints:**

#### GET /api/top5
Получить топ-5 кампаний

**Query Parameters:**
- `period` (int) — период в днях (default: 30)
- `minClicks` (int) — минимум кликов (default: 60)

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "campaign_id": "Traffichunt-1665",
      "total_clicks": 133,
      "total_cost": 23.00,
      "total_revenue": 60.00,
      "roi": 160.87,
      "impact": 37.00,
      "volatility_score": 12.5,
      "growth_3d": 15.3,
      "final_score": 92.3,
      "score_percentage": 93,
      "best_segments": [...],
      "worst_segments": [...],
      "trend_data": [105, 211, 73]
    }
  ],
  "timestamp": "2026-02-08T10:00:00Z"
}
```

#### POST /api/apply-action
Применить действие пользователя

**Request Body:**
```json
{
  "campaign_id": "Traffichunt-1665",
  "action": "SCALE",
  "hide_duration": 3
}
```

**Response:**
```json
{
  "success": true,
  "message": "Action applied successfully"
}
```

#### POST /api/ai-council/:campaignId
Вызов AI Council для детального анализа

**Response:**
```json
{
  "success": true,
  "data": {
    "recommendation": "SCALE",
    "reasoning": "High ROI with potential for scaling...",
    "specific_actions": [
      "Increase budget by 50%",
      "Focus on Android 13+ segment"
    ],
    "confidence_score": 85.5
  }
}
```

---

### 3. DATABASE (MySQL)

**Расположение:** `/database`

**Схема БД:**

#### Таблица: campaign_data
Основные данные кампаний (26 столбцов)

```sql
CREATE TABLE campaign_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    date DATE,
    click INT,
    campaign_id VARCHAR(255),
    path VARCHAR(255),
    rule VARCHAR(255),
    offer_id VARCHAR(255),
    lander_id VARCHAR(255),
    traffic_source VARCHAR(255),
    device_type VARCHAR(50),
    country VARCHAR(10),
    os VARCHAR(50),
    os_version VARCHAR(100),
    browser_name VARCHAR(100),
    language VARCHAR(10),
    payout DECIMAL(10,2),
    conversion INT,
    cost DECIMAL(10,2),
    token_1 VARCHAR(255),
    token_2 VARCHAR(255),
    token_3 VARCHAR(255),
    token_4 VARCHAR(255),
    token_5 VARCHAR(255),
    token_6 VARCHAR(255),
    token_7 VARCHAR(255),
    token_8 VARCHAR(255),
    token_9 VARCHAR(255),
    token_10 VARCHAR(255),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### Таблица: shown_campaigns
История показа в TOP-5

```sql
CREATE TABLE shown_campaigns (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    campaign_id VARCHAR(255),
    shown_at TIMESTAMP,
    score DECIMAL(10,2),
    volatility_score DECIMAL(10,2)
);
```

#### Таблица: user_actions
Действия пользователя для обучения

```sql
CREATE TABLE user_actions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    campaign_id VARCHAR(255),
    action_type ENUM('SCALE', 'HOLD', 'OPTIMIZE'),
    hide_duration INT,
    timestamp TIMESTAMP,
    roi DECIMAL(10,2),
    impact DECIMAL(10,2),
    volatility DECIMAL(10,2),
    score DECIMAL(10,2)
);
```

#### Процедура: get_top5_campaigns
Основная процедура отбора TOP-5

```sql
CALL get_top5_campaigns(30, 60);
```

---

### 4. PYTHON SCRIPTS

**Расположение:** `/scripts`

#### analyze_tokens.py
FP-Growth анализ токенов для поиска скрытых паттернов

**Использование:**
```bash
python3 analyze_tokens.py <campaign_id> [days]
```

**Выход (JSON):**
```json
{
  "patterns": [
    {
      "pattern": "T2_238885_21581 AND Device_Mobile",
      "clicks": 51,
      "conversions": 11,
      "roi": 200.5,
      "cr": 21.6,
      "lift": 3.2,
      "confidence": 0.85
    }
  ],
  "anomalies": [
    {
      "token": "Token3",
      "value": "1665_1_WD_La",
      "frequency": 3.5,
      "cr": 18.2,
      "cr_vs_avg": 4.5
    }
  ]
}
```

---

## АЛГОРИТМ РАБОТЫ

### 1. ОТБОР КАМПАНИЙ

```
1. Запрос к БД: получить все кампании за последние N дней
2. Фильтр: минимум 60 кликов
3. Расчёт базовых метрик (ROI, Impact, CR)
4. Расчёт волатильности (Standard Deviation + CV + Range Ratio)
5. Расчёт роста за 3 дня
6. Вычисление SCORE по формуле:
   SCORE = (Volatility × 3.0) + (Growth × 2.5) + (ROI × 1.0) + (LOG10(Clicks) × 0.5)
7. Исключение показанных < 48ч назад
8. Исключение скрытых пользователем
9. Фильтр: Volatility между 5% и 30%
10. Сортировка по SCORE DESC
11. Выбор TOP-5
```

### 2. ОБОГАЩЕНИЕ ДАННЫХ

Для каждой кампании в TOP-5:

```
1. Сегментный анализ (Level 2):
   - Группировка по OS, Device, Token2
   - Вычисление Impact для каждого сегмента
   - Сортировка: best (топ-5) и worst (низ-3)

2. Тренд-анализ:
   - Получение ROI за последние 3 дня
   - Форматирование: [105%, 211%, 73%]

3. Токен-анализ (Level 3, опционально):
   - Вызов Python скрипта analyze_tokens.py
   - FP-Growth для поиска паттернов
   - Детекция аномалий

4. Запись показа в shown_campaigns
```

### 3. СИСТЕМА ОБУЧЕНИЯ

При применении действия пользователя:

```python
if action == 'SCALE':
    # Увеличиваем веса для похожих паттернов
    volatility_weight *= 1.1
    score_multiplier *= 1.1
    
    if campaign.has_token_anomalies:
        token_anomaly_weight *= 1.15

elif action == 'OPTIMIZE':
    # Снижаем веса
    score_multiplier *= 0.9

elif action == 'HOLD':
    # Повышаем min порог кликов
    min_clicks_threshold += 10
```

---

## DATA FLOW

```
┌──────────────────┐
│  User Action     │
│  (Click Apply)   │
└────────┬─────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  POST /api/apply-action                │
│                                        │
│  1. Получить метрики кампании          │
│  2. Записать action в user_actions     │
│  3. Если hide_duration > 0:            │
│     INSERT INTO hidden_campaigns       │
│  4. Обновить learning_weights          │
│  5. Return success                     │
└────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  GET /api/top5 (refresh)               │
│                                        │
│  1. CALL get_top5_campaigns()          │
│  2. Для каждой кампании:               │
│     - getSegmentBreakdown()            │
│     - getTrend()                       │
│     - analyzeTokens() [Python]         │
│  3. INSERT INTO shown_campaigns        │
│  4. Return enriched data               │
└────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Frontend (React)                      │
│                                        │
│  1. Render campaign cards              │
│  2. Show metrics, segments, trends     │
│  3. User selects new action            │
│  4. Cycle repeats...                   │
└────────────────────────────────────────┘
```

---

## МАСШТАБИРОВАНИЕ

### Горизонтальное масштабирование:

1. **Backend:** Запустить несколько инстансов за load balancer (nginx)
2. **Database:** Master-Slave репликация для чтения
3. **Python Scripts:** Очередь задач (Redis + Bull)

### Оптимизация производительности:

1. **Кэширование:** Redis для результатов TOP-5 (TTL 5 минут)
2. **Индексы БД:** Композитные индексы на (campaign_id, date)
3. **Асинхронность:** Токен-анализ через Worker threads

---

## БЕЗОПАСНОСТЬ

1. **SQL Injection:** Все запросы через prepared statements
2. **Rate Limiting:** Express-rate-limit на API endpoints
3. **CORS:** Ограничение допустимых origins
4. **Environment Variables:** Секреты в .env, не в коде
5. **Validation:** Валидация входных данных (express-validator)

---

## МОНИТОРИНГ

Рекомендуемые метрики:

1. **API Response Time:** Средний 95th percentile < 200ms
2. **Database Queries:** Время выполнения get_top5_campaigns < 500ms
3. **Python Script Success Rate:** > 95%
4. **User Actions:** Распределение SCALE/HOLD/OPTIMIZE
5. **Error Rate:** < 1%

---

## РАЗВЕРТЫВАНИЕ

### Production Checklist:

- [ ] Настроить .env с production credentials
- [ ] Запустить database/schema.sql
- [ ] Установить зависимости: `npm install` + `pip install -r requirements.txt`
- [ ] Настроить reverse proxy (nginx)
- [ ] Настроить SSL сертификаты
- [ ] Настроить backup БД (daily)
- [ ] Настроить мониторинг (Grafana + Prometheus)
- [ ] Настроить логирование (ELK stack или аналог)

---

Версия: 1.0.0  
Дата: 2026-02-08
