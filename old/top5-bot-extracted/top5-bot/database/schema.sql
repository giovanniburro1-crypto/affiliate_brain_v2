-- TOP-5 Analysis Bot Database Schema
-- Version: 1.0.0

-- =====================================================
-- ТАБЛИЦА: campaign_data
-- Основные данные кампаний (26 столбцов)
-- =====================================================

CREATE TABLE IF NOT EXISTS campaign_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- Основные поля
    date DATE NOT NULL,
    click INT NOT NULL DEFAULT 0,
    campaign_id VARCHAR(255) NOT NULL,
    
    -- Воронка и правила
    path VARCHAR(255),
    rule VARCHAR(255),
    offer_id VARCHAR(255),
    lander_id VARCHAR(255),
    
    -- Источник и сегментация
    traffic_source VARCHAR(255),
    device_type VARCHAR(50),
    country VARCHAR(10),
    os VARCHAR(50),
    os_version VARCHAR(100),
    browser_name VARCHAR(100),
    language VARCHAR(10),
    
    -- Финансовые метрики
    payout DECIMAL(10, 2) DEFAULT 0.00,
    conversion INT NOT NULL DEFAULT 0,
    cost DECIMAL(10, 2) DEFAULT 0.00,
    
    -- Токены (параметры кампании)
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
    
    -- Служебные поля
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Индексы для производительности
    INDEX idx_campaign_date (campaign_id, date),
    INDEX idx_date (date),
    INDEX idx_device (device_type),
    INDEX idx_country (country),
    INDEX idx_os (os),
    INDEX idx_traffic_source (traffic_source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ТАБЛИЦА: shown_campaigns
-- История показа кампаний в TOP-5
-- =====================================================

CREATE TABLE IF NOT EXISTS shown_campaigns (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    campaign_id VARCHAR(255) NOT NULL,
    shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    score DECIMAL(10, 2),
    volatility_score DECIMAL(10, 2),
    
    INDEX idx_campaign_shown (campaign_id, shown_at),
    INDEX idx_shown_at (shown_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ТАБЛИЦА: hidden_campaigns
-- Кампании, скрытые пользователем
-- =====================================================

CREATE TABLE IF NOT EXISTS hidden_campaigns (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    campaign_id VARCHAR(255) NOT NULL UNIQUE,
    hidden_until TIMESTAMP NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_hidden_until (hidden_until),
    INDEX idx_campaign (campaign_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ТАБЛИЦА: user_actions
-- Действия пользователя (SCALE/HOLD/OPTIMIZE)
-- =====================================================

CREATE TABLE IF NOT EXISTS user_actions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    campaign_id VARCHAR(255) NOT NULL,
    action_type ENUM('SCALE', 'HOLD', 'OPTIMIZE') NOT NULL,
    hide_duration INT DEFAULT 0, -- в днях
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Метрики кампании на момент действия
    roi DECIMAL(10, 2),
    impact DECIMAL(10, 2),
    volatility DECIMAL(10, 2),
    score DECIMAL(10, 2),
    
    INDEX idx_campaign_action (campaign_id, action_type),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ТАБЛИЦА: learning_weights
-- Веса для системы обучения
-- =====================================================

CREATE TABLE IF NOT EXISTS learning_weights (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pattern_type VARCHAR(100) NOT NULL UNIQUE,
    volatility_weight DECIMAL(5, 2) DEFAULT 3.0,
    growth_weight DECIMAL(5, 2) DEFAULT 2.5,
    token_anomaly_weight DECIMAL(5, 2) DEFAULT 2.0,
    roi_weight DECIMAL(5, 2) DEFAULT 1.0,
    volume_weight DECIMAL(5, 2) DEFAULT 0.5,
    score_multiplier DECIMAL(5, 2) DEFAULT 1.0,
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Начальные значения
INSERT INTO learning_weights (pattern_type) VALUES
    ('default'),
    ('high_volatility'),
    ('token_anomaly'),
    ('segment_opportunity'),
    ('stable_performer')
ON DUPLICATE KEY UPDATE pattern_type = pattern_type;

-- =====================================================
-- ТАБЛИЦА: campaign_patterns
-- Паттерны кампаний для обучения
-- =====================================================

CREATE TABLE IF NOT EXISTS campaign_patterns (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    campaign_id VARCHAR(255) NOT NULL,
    pattern_type VARCHAR(100) NOT NULL,
    pattern_data JSON,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_campaign (campaign_id),
    INDEX idx_pattern_type (pattern_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ТАБЛИЦА: ai_council_results
-- Результаты AI Council анализа
-- =====================================================

CREATE TABLE IF NOT EXISTS ai_council_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    campaign_id VARCHAR(255) NOT NULL,
    recommendation ENUM('SCALE', 'HOLD', 'OPTIMIZE') NOT NULL,
    reasoning TEXT,
    specific_actions JSON,
    confidence_score DECIMAL(5, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_campaign (campaign_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- ПРЕДСТАВЛЕНИЕ: campaign_metrics
-- Агрегированные метрики кампаний
-- =====================================================

CREATE OR REPLACE VIEW campaign_metrics AS
SELECT 
    campaign_id,
    DATE(date) as metric_date,
    SUM(click) as total_clicks,
    SUM(cost) as total_cost,
    SUM(conversion * payout) as total_revenue,
    SUM(conversion) as total_conversions,
    CASE 
        WHEN SUM(cost) > 0 THEN ((SUM(conversion * payout) - SUM(cost)) / SUM(cost)) * 100
        ELSE 0
    END as roi,
    CASE 
        WHEN SUM(click) > 0 THEN (SUM(conversion) / SUM(click)) * 100
        ELSE 0
    END as cr,
    SUM(conversion * payout) - SUM(cost) as impact
FROM campaign_data
GROUP BY campaign_id, DATE(date);

-- =====================================================
-- ФУНКЦИЯ: calculate_volatility
-- Расчёт волатильности для кампании
-- =====================================================

DELIMITER $$

CREATE FUNCTION calculate_volatility(
    p_campaign_id VARCHAR(255),
    p_days INT
) RETURNS DECIMAL(10, 2)
DETERMINISTIC
BEGIN
    DECLARE v_volatility DECIMAL(10, 2);
    DECLARE v_cv_roi DECIMAL(10, 2);
    DECLARE v_cv_cr DECIMAL(10, 2);
    DECLARE v_rr_impact DECIMAL(10, 2);
    
    -- CV для ROI
    SELECT 
        CASE 
            WHEN AVG(roi) > 0 THEN (STDDEV(roi) / AVG(roi)) * 100
            ELSE 0
        END INTO v_cv_roi
    FROM campaign_metrics
    WHERE campaign_id = p_campaign_id
        AND metric_date >= DATE_SUB(CURDATE(), INTERVAL p_days DAY);
    
    -- CV для CR
    SELECT 
        CASE 
            WHEN AVG(cr) > 0 THEN (STDDEV(cr) / AVG(cr)) * 100
            ELSE 0
        END INTO v_cv_cr
    FROM campaign_metrics
    WHERE campaign_id = p_campaign_id
        AND metric_date >= DATE_SUB(CURDATE(), INTERVAL p_days DAY);
    
    -- Range Ratio для Impact
    SELECT 
        CASE 
            WHEN AVG(impact) != 0 THEN (MAX(impact) - MIN(impact)) / AVG(impact)
            ELSE 0
        END INTO v_rr_impact
    FROM campaign_metrics
    WHERE campaign_id = p_campaign_id
        AND metric_date >= DATE_SUB(CURDATE(), INTERVAL p_days DAY);
    
    -- Итоговая волатильность
    SET v_volatility = (COALESCE(v_cv_roi, 0) * 0.4) + 
                       (COALESCE(v_cv_cr, 0) * 0.3) + 
                       (COALESCE(v_rr_impact, 0) * 0.3);
    
    RETURN v_volatility;
END$$

DELIMITER ;

-- =====================================================
-- ПРОЦЕДУРА: get_top5_campaigns
-- Основная процедура отбора TOP-5 кампаний
-- =====================================================

DELIMITER $$

CREATE PROCEDURE get_top5_campaigns(
    IN p_period_days INT,
    IN p_min_clicks INT
)
BEGIN
    -- Временная таблица с метриками
    CREATE TEMPORARY TABLE IF NOT EXISTS temp_campaign_scores (
        campaign_id VARCHAR(255),
        total_clicks INT,
        total_cost DECIMAL(10, 2),
        total_revenue DECIMAL(10, 2),
        roi DECIMAL(10, 2),
        impact DECIMAL(10, 2),
        volatility_score DECIMAL(10, 2),
        growth_3d DECIMAL(10, 2),
        final_score DECIMAL(10, 2),
        PRIMARY KEY (campaign_id)
    );
    
    -- Заполняем базовые метрики
    INSERT INTO temp_campaign_scores (campaign_id, total_clicks, total_cost, total_revenue, roi, impact)
    SELECT 
        campaign_id,
        SUM(click) as total_clicks,
        SUM(cost) as total_cost,
        SUM(conversion * payout) as total_revenue,
        CASE 
            WHEN SUM(cost) > 0 THEN ((SUM(conversion * payout) - SUM(cost)) / SUM(cost)) * 100
            ELSE 0
        END as roi,
        SUM(conversion * payout) - SUM(cost) as impact
    FROM campaign_data
    WHERE date >= DATE_SUB(CURDATE(), INTERVAL p_period_days DAY)
    GROUP BY campaign_id
    HAVING total_clicks >= p_min_clicks;
    
    -- Добавляем волатильность
    UPDATE temp_campaign_scores
    SET volatility_score = calculate_volatility(campaign_id, 14);
    
    -- Добавляем рост за 3 дня
    UPDATE temp_campaign_scores tcs
    JOIN (
        SELECT 
            campaign_id,
            ((recent.avg_roi - previous.avg_roi) / previous.avg_roi) * 100 as growth
        FROM (
            SELECT campaign_id, AVG(roi) as avg_roi
            FROM campaign_metrics
            WHERE metric_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
            GROUP BY campaign_id
        ) recent
        JOIN (
            SELECT campaign_id, AVG(roi) as avg_roi
            FROM campaign_metrics
            WHERE metric_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 10 DAY) 
                                  AND DATE_SUB(CURDATE(), INTERVAL 4 DAY)
            GROUP BY campaign_id
        ) previous ON recent.campaign_id = previous.campaign_id
    ) growth ON tcs.campaign_id = growth.campaign_id
    SET tcs.growth_3d = growth.growth;
    
    -- Вычисляем финальный score
    UPDATE temp_campaign_scores
    SET final_score = (
        (COALESCE(volatility_score, 0) * 3.0) +
        (COALESCE(growth_3d, 0) * 2.5) +
        (COALESCE(roi, 0) * 1.0) +
        (LOG10(total_clicks) * 0.5)
    );
    
    -- Выбираем TOP-5
    SELECT 
        tcs.*,
        cd.device_type,
        cd.os,
        cd.traffic_source
    FROM temp_campaign_scores tcs
    LEFT JOIN campaign_data cd ON tcs.campaign_id = cd.campaign_id
    WHERE tcs.campaign_id NOT IN (
        SELECT campaign_id 
        FROM shown_campaigns 
        WHERE shown_at > DATE_SUB(NOW(), INTERVAL 48 HOUR)
    )
    AND tcs.campaign_id NOT IN (
        SELECT campaign_id 
        FROM hidden_campaigns 
        WHERE hidden_until > NOW()
    )
    AND volatility_score BETWEEN 5 AND 30  -- Только средняя и высокая волатильность
    ORDER BY final_score DESC
    LIMIT 5;
    
    DROP TEMPORARY TABLE IF EXISTS temp_campaign_scores;
END$$

DELIMITER ;

-- =====================================================
-- ТРИГGER: record_shown_campaign
-- Автоматическая запись показа кампании
-- =====================================================

-- (Тригgers не создаются здесь, так как их вызов будет из приложения)

-- =====================================================
-- ИНДЕКСЫ для производительности
-- =====================================================

-- Композитные индексы для частых запросов
CREATE INDEX idx_campaign_date_device ON campaign_data(campaign_id, date, device_type);
CREATE INDEX idx_date_campaign ON campaign_data(date, campaign_id);

-- Индексы для токенов (часто используются в Level 3 анализе)
CREATE INDEX idx_token_1 ON campaign_data(token_1(50));
CREATE INDEX idx_token_2 ON campaign_data(token_2(50));
CREATE INDEX idx_token_3 ON campaign_data(token_3(50));

-- =====================================================
-- ГОТОВО!
-- =====================================================

SELECT 'Database schema created successfully!' as status;
