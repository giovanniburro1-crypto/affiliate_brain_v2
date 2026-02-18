# Анализ кнопки "Apply" на карточке компании в TOP-5

## Общая информация

Кнопка "Apply" (Применить) появляется на каждой карточке кампании в разделе TOP-5 анализа системы Affiliate Brain. Она позволяет пользователю применить выбранный вердикт к кампании.

## Фронтенд реализация (frontend/bot-top5.html)

### Расположение и внешний вид
```html
<button type="button" onclick="onApply('${escapeHtml(c.campaign_id)}', ${c.confidence})" 
        class="btn-success px-3 py-1.5 rounded text-sm">Apply</button>
```
- Кнопка зеленого цвета (класс `btn-success`)
- Расположена в нижней части карточки кампании
- Соседние элементы: выбор вердикта, выбор дней речека, кнопка "Call AI Council"

### Функционал JavaScript

**Основная функция `onApply()`:**
```javascript
function onApply(campaignId, confidence) {
    const verdictEl = document.querySelector(`input[name="verdict-${campaignId}"]:checked`);
    const verdict = verdictEl ? verdictEl.value : 'HOLD';
    const recheckEl = document.getElementById(`recheckDays-${campaignId}`);
    const recheckAfterDays = recheckEl ? parseInt(recheckEl.value, 10) : 0;

    // Находим карточку кампании для удаления
    const campaignCard = document.querySelector(`[data-campaign-id="${campaignId}"]`);
    
    fetch('/api/bot-agent/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            campaign_id: campaignId, 
            verdict, 
            recheck_after_days: recheckAfterDays, 
            confidence 
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            // Анимация удаления карточки
            if (campaignCard) {
                campaignCard.style.opacity = '0.7';
                campaignCard.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                campaignCard.style.transform = 'scale(0.95)';
                
                setTimeout(() => {
                    campaignCard.style.opacity = '0';
                    campaignCard.style.transform = 'scale(0.9)';
                    
                    setTimeout(() => {
                        campaignCard.remove();
                        // Обновляем порядковый номер оставшихся карточек если нужно
                        const remainingCards = document.querySelectorAll('#top5Cards > .card');
                        if (remainingCards.length === 0) {
                            document.getElementById('top5Cards').innerHTML = 
                                '<p class="text-zinc-500 py-8 text-center">Кампания перемещена в очередь речека. Нажмите <strong>Play</strong> для загрузки новых кампаний.</p>';
                        }
                    }, 200);
                }, 300);
            }
            // Показываем уведомление
            alert(data.message || 'Кампания перемещена в очередь речека.');
        } else {
            alert(data.error || 'Ошибка');
        }
    })
    .catch(() => {
        alert('Ошибка сети');
        // Восстанавливаем карточку если была скрыта
        if (campaignCard && campaignCard.style.opacity !== '1') {
            campaignCard.style.opacity = '1';
            campaignCard.style.transform = 'scale(1)';
        }
    });
}
```

### Пользовательский интерфейс
1. **Выбор вердикта:** 3 радио-кнопки:
   - SCALE (зеленый)
   - HOLD (желтый) 
   - OPTIMIZE (синий)

2. **Выбор дней речека:** выпадающий список:
   - "Речек: некогда" (значение 0)
   - 1 день
   - 2 дня
   - 3 дня (по умолчанию)
   - 5 дней
   - 7 дней

3. **Кнопка Apply:** применяет выбранные настройки

## Бэкенд реализация (backend/routers/bot_agent.py)

### Endpoint
```python
@router.post("/apply")
async def apply(body: ApplyBody, db: Session = Depends(get_db)):
    """Применить вердикт пользователя: всегда пишем в AIMemory и при выборе речека — в очередь. Уверенность бота не ограничивает действие."""
```

### Модель данных ApplyBody
```python
class ApplyBody(BaseModel):
    campaign_id: str
    verdict: str
    hide_days: int = 0  # legacy, map to recheck_after_days
    recheck_after_days: int = 0  # 0 = некогда, 1/2/3/5/7 = add to queue
    confidence: float = 0
    bot_proposal: Optional[str] = None
    user_comment: Optional[str] = None
    context_snapshot: Optional[Dict[str, Any]] = None
```

### Логика работы

1. **Обработка дней речека:**
   ```python
   recheck_days = getattr(body, "recheck_after_days", None)
   if recheck_days is None and getattr(body, "hide_days", None) is not None:
       recheck_days = body.hide_days
   recheck_days = recheck_days if recheck_days is not None else 0
   recheck_days = int(recheck_days)
   ```

2. **Получение данных кампании:**
   - Запрос к базе данных за последние 14 дней
   - Расчет метрик: spend, revenue, conversions, profit, ROI

3. **Валидация вердикта:**
   ```python
   verdict = (body.verdict or "HOLD").upper().strip()
   allowed = ("SCALE", "HOLD", "OPTIMIZE", "STOP")
   if "," in verdict:
       parts = [p.strip() for p in verdict.split(",") if p.strip() in allowed]
       verdict = ",".join(parts) if parts else "HOLD"
   elif verdict not in allowed:
       verdict = "HOLD"
   ```

4. **Запись в AIMemory:**
   - Всегда записывает решение пользователя
   - Сохраняет: campaign_id, decision_date, bot_verdict, user_choice
   - Также сохраняет user_comment и context_snapshot если есть

5. **Добавление в очередь речека:**
   - Если `recheck_after_days` в (1, 2, 3, 5, 7) - добавляет в очередь
   - Если уже существует запись - обновляет
   - Если не существует - создает новую

6. **Ответ:**
   ```python
   message = "Добавлено в очередь речека." if recheck_days in (1, 2, 3, 5, 7) else "Применено."
   return {"success": True, "message": message}
   ```

## Особенности работы

### Уверенность бота не ограничивает действие
В отличие от других систем, где действия могут быть ограничены уверенностью бота, здесь:
> "Уверенность бота не ограничивает действие."

Пользователь может применить любой вердикт независимо от confidence бота.

### Всегда записывается в AIMemory
Каждое действие пользователя сохраняется в историю решений для дальнейшего анализа и обучения.

### Обработка legacy параметров
Поддерживается обратная совместимость с параметром `hide_days` (автоматически маппится на `recheck_after_days`).

### Умное удаление на фронтенде
- Плавная анимация исчезновения карточки
- Автоматическое обновление списка
- Если все карточки удалены - показывается информационное сообщение
- Обработка ошибок сети с восстановлением карточки

## Связанные компоненты системы

### Таблица AIMemory
```sql
CREATE TABLE IF NOT EXISTS ai_memory (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(100),
    decision_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    bot_verdict VARCHAR(50),
    bot_score FLOAT,
    bot_confidence FLOAT,
    bot_reasoning TEXT,
    ai_verdict VARCHAR(50),
    ai_confidence FLOAT,
    user_choice VARCHAR(50),
    user_comment TEXT,
    context_snapshot TEXT,
    outcome VARCHAR(50),
    roi_after_7days FLOAT,
    roi_after_14days FLOAT
)
```

### Таблица RecheckQueue
```sql
CREATE TABLE IF NOT EXISTS recheck_queue (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(100) NOT NULL,
    campaign VARCHAR(255),
    verdict VARCHAR(50),
    recheck_after_days INTEGER DEFAULT 0,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Поток данных

1. **Пользователь:** Выбирает вердикт и дни речека → нажимает Apply
2. **Фронтенд:** Собирает данные → отправляет POST /api/bot-agent/apply
3. **Бэкенд:** 
   - Проверяет данные кампании
   - Записывает в AIMemory
   - При необходимости добавляет в RecheckQueue
   - Возвращает результат
4. **Фронтенд:** 
   - При успехе: анимация удаления + уведомление
   - При ошибке: alert с ошибкой

## Важные моменты

1. **Default значения:** Если вердикт не выбран - используется HOLD
2. **Валидация:** Поддерживаются только разрешенные вердикты (SCALE, HOLD, OPTIMIZE, STOP)
3. **Множественные вердикты:** Поддерживается формат "SCALE,OPTIMIZE" через запятую
4. **Контекст:** Можно передать context_snapshot для сохранения состояния системы на момент принятия решения
5. **Комментарии:** Пользователь может добавить user_comment к решению

## Использование в других интерфейсах

Кнопка Apply также используется в:
- `frontend/ai-company-analysis.html` - с текстом "Apply — записать в память"
- `frontend/index.html` - кнопка "Apply" на дашборде
- `frontend/re-checking.html` - для применения анализа

Но основная реализация для TOP-5 находится в `frontend/bot-top5.html`.