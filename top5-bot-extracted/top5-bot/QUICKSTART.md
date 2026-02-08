# БЫСТРЫЙ СТАРТ - TOP-5 ANALYSIS BOT

## ЗА 5 МИНУТ ДО ЗАПУСКА

### Шаг 1: Установите зависимости

```bash
# Node.js 18+ и npm
node --version  # должно быть >= 18.0.0

# Python 3.9+
python3 --version  # должно быть >= 3.9

# MySQL 8.0+
mysql --version  # должно быть >= 8.0
```

### Шаг 2: Распакуйте архив

```bash
unzip top5-bot.zip
cd top5-bot
```

### Шаг 3: Настройте базу данных

```bash
# Войдите в MySQL
mysql -u root -p

# Создайте базу данных
CREATE DATABASE top5_analysis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# Выйдите и импортируйте схему
mysql -u root -p top5_analysis < database/schema.sql
```

### Шаг 4: Загрузите тестовые данные (опционально)

```bash
# Если у вас есть CSV с данными кампаний:
mysql -u root -p top5_analysis

LOAD DATA LOCAL INFILE '/path/to/your/campaign_data.csv'
INTO TABLE campaign_data
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
```

### Шаг 5: Настройте окружение

```bash
# Скопируйте пример конфига
cp .env.example .env

# Отредактируйте .env
nano .env
```

Измените:
```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=ВАШ_ПАРОЛЬ
DB_NAME=top5_analysis
PORT=3000
```

### Шаг 6: Установите зависимости

```bash
# Backend
cd backend
npm install

# Python scripts
cd ../scripts
pip install -r requirements.txt --break-system-packages

cd ..
```

### Шаг 7: Запустите сервер

```bash
cd backend
npm start
```

Вы должны увидеть:
```
🚀 TOP-5 Analysis Bot Server running on port 3000
📊 API endpoint: http://localhost:3000/api/top5
```

### Шаг 8: Откройте интерфейс

Откройте в браузере:
```
http://localhost:3000/api/top5
```

Для полноценного UI запустите frontend:
```bash
# В новом терминале
cd frontend
npm install
npm start
```

---

## БЫСТРЫЙ ТЕСТ API

```bash
# Получить TOP-5
curl http://localhost:3000/api/top5

# Получить TOP-5 за 7 дней
curl http://localhost:3000/api/top5?period=7

# Применить действие
curl -X POST http://localhost:3000/api/apply-action \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "YourCampaignID",
    "action": "SCALE",
    "hide_duration": 3
  }'
```

---

## TROUBLESHOOTING

### Ошибка подключения к БД
```
Error: ER_ACCESS_DENIED_ERROR
```
**Решение:** Проверьте credentials в .env

### Python скрипт не найден
```
Error: python3 not found
```
**Решение:**
```bash
# macOS/Linux
which python3
# Если не найдено, установите Python 3.9+

# Проверьте mlxtend
python3 -c "import mlxtend; print('OK')"
```

### Порт 3000 занят
```
Error: EADDRINUSE: address already in use
```
**Решение:** Измените PORT в .env на другой (например, 3001)

### Нет данных в TOP-5
```json
{
  "data": []
}
```
**Решение:**
1. Проверьте, что в таблице campaign_data есть данные
2. Убедитесь, что данные за последние 30 дней
3. Проверьте, что есть кампании с минимум 60 кликами
4. Сбросьте shown_campaigns: `TRUNCATE TABLE shown_campaigns;`

---

## СТРУКТУРА ПРОЕКТА

```
top5-bot/
├── README.md              # Главная документация
├── .env.example           # Пример конфигурации
├── backend/
│   ├── server.js          # Express сервер
│   └── package.json
├── frontend/
│   └── src/
│       └── components/
│           ├── Top5Display.jsx
│           └── Top5Display.css
├── database/
│   └── schema.sql         # SQL схема
├── scripts/
│   ├── analyze_tokens.py  # FP-Growth анализ
│   └── requirements.txt
└── docs/
    └── ARCHITECTURE.md    # Детальная архитектура
```

---

## СЛЕДУЮЩИЕ ШАГИ

1. **Загрузите реальные данные** в campaign_data
2. **Настройте AI Council** (добавьте OPENAI_API_KEY в .env)
3. **Кастомизируйте веса** в таблице learning_weights
4. **Добавьте мониторинг** (Grafana, Prometheus)
5. **Настройте автоматический backup** БД

---

## ПОЛЕЗНЫЕ КОМАНДЫ

```bash
# Посмотреть последние действия пользователей
mysql -u root -p -e "SELECT * FROM top5_analysis.user_actions ORDER BY timestamp DESC LIMIT 10"

# Посмотреть скрытые кампании
mysql -u root -p -e "SELECT * FROM top5_analysis.hidden_campaigns WHERE hidden_until > NOW()"

# Сбросить показы (для тестирования)
mysql -u root -p -e "TRUNCATE TABLE top5_analysis.shown_campaigns"

# Проверить веса обучения
mysql -u root -p -e "SELECT * FROM top5_analysis.learning_weights"
```

---

**Готово! 🎉**

Теперь у вас запущен TOP-5 Analysis Bot. 

Для детальной информации см. README.md и docs/ARCHITECTURE.md
