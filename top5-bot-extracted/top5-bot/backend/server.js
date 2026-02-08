// TOP-5 Analysis Bot - Backend Server
// Version: 1.0.0

const express = require('express');
const cors = require('cors');
const mysql = require('mysql2/promise');
const { execSync } = require('child_process');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Database Connection Pool
const pool = mysql.createPool({
    host: process.env.DB_HOST || 'localhost',
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASSWORD || '',
    database: process.env.DB_NAME || 'top5_analysis',
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0
});

// =====================================================
// API ENDPOINTS
// =====================================================

/**
 * GET /api/top5
 * Получить TOP-5 кампаний
 */
app.get('/api/top5', async (req, res) => {
    try {
        const period = parseInt(req.query.period) || 30;
        const minClicks = parseInt(req.query.minClicks) || 60;
        
        const [campaigns] = await pool.execute(
            'CALL get_top5_campaigns(?, ?)',
            [period, minClicks]
        );
        
        // Обогащаем данные детальной информацией
        const enrichedCampaigns = await Promise.all(
            campaigns[0].map(async (campaign) => {
                // Получаем лучшие и худшие сегменты
                const segments = await getSegmentBreakdown(campaign.campaign_id, period);
                
                // Получаем динамику за последние 3 дня
                const trend = await getTrend(campaign.campaign_id, 3);
                
                // Записываем показ
                await pool.execute(
                    'INSERT INTO shown_campaigns (campaign_id, score, volatility_score) VALUES (?, ?, ?)',
                    [campaign.campaign_id, campaign.final_score, campaign.volatility_score]
                );
                
                return {
                    ...campaign,
                    best_segments: segments.best,
                    worst_segments: segments.worst,
                    trend_data: trend,
                    score_percentage: Math.round((campaign.final_score / 100) * 100)
                };
            })
        );
        
        res.json({
            success: true,
            data: enrichedCampaigns,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('Error fetching TOP-5:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/apply-action
 * Применить действие пользователя (SCALE/HOLD/OPTIMIZE)
 */
app.post('/api/apply-action', async (req, res) => {
    try {
        const { campaign_id, action, hide_duration } = req.body;
        
        if (!campaign_id || !action) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields'
            });
        }
        
        // Получаем текущие метрики кампании
        const [metrics] = await pool.execute(`
            SELECT 
                SUM(click) as clicks,
                SUM(cost) as cost,
                SUM(conversion * payout) as revenue,
                ((SUM(conversion * payout) - SUM(cost)) / SUM(cost)) * 100 as roi
            FROM campaign_data
            WHERE campaign_id = ?
                AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        `, [campaign_id]);
        
        const campaignMetrics = metrics[0];
        const impact = campaignMetrics.revenue - campaignMetrics.cost;
        const volatility = await getVolatility(campaign_id);
        
        // Записываем действие пользователя
        await pool.execute(`
            INSERT INTO user_actions 
            (campaign_id, action_type, hide_duration, roi, impact, volatility)
            VALUES (?, ?, ?, ?, ?, ?)
        `, [
            campaign_id,
            action,
            hide_duration || 0,
            campaignMetrics.roi,
            impact,
            volatility
        ]);
        
        // Если выбрано скрыть
        if (hide_duration > 0) {
            await pool.execute(`
                INSERT INTO hidden_campaigns (campaign_id, hidden_until)
                VALUES (?, DATE_ADD(NOW(), INTERVAL ? DAY))
                ON DUPLICATE KEY UPDATE hidden_until = DATE_ADD(NOW(), INTERVAL ? DAY)
            `, [campaign_id, hide_duration, hide_duration]);
        }
        
        // Обновляем веса модели обучения
        await updateLearningWeights(campaign_id, action, volatility);
        
        res.json({
            success: true,
            message: 'Action applied successfully'
        });
        
    } catch (error) {
        console.error('Error applying action:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/ai-council/:campaignId
 * Вызов AI Council для детального анализа
 */
app.post('/api/ai-council/:campaignId', async (req, res) => {
    try {
        const { campaignId } = req.params;
        
        // Получаем полные данные кампании
        const [campaignData] = await pool.execute(`
            SELECT * FROM campaign_data
            WHERE campaign_id = ?
                AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ORDER BY date DESC
        `, [campaignId]);
        
        // Вызываем Python скрипт для AI анализа
        const analysis = await callAICouncil(campaignData);
        
        // Сохраняем результат
        await pool.execute(`
            INSERT INTO ai_council_results 
            (campaign_id, recommendation, reasoning, specific_actions, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        `, [
            campaignId,
            analysis.recommendation,
            analysis.reasoning,
            JSON.stringify(analysis.specific_actions),
            analysis.confidence_score
        ]);
        
        res.json({
            success: true,
            data: analysis
        });
        
    } catch (error) {
        console.error('Error calling AI Council:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /api/campaign/:id/details
 * Получить детальную информацию по кампании
 */
app.get('/api/campaign/:id/details', async (req, res) => {
    try {
        const { id } = req.params;
        const period = parseInt(req.query.period) || 30;
        
        const [campaign] = await pool.execute(`
            SELECT 
                campaign_id,
                SUM(click) as total_clicks,
                SUM(cost) as total_cost,
                SUM(conversion * payout) as total_revenue,
                SUM(conversion) as total_conversions,
                ((SUM(conversion * payout) - SUM(cost)) / SUM(cost)) * 100 as roi,
                (SUM(conversion) / SUM(click)) * 100 as cr
            FROM campaign_data
            WHERE campaign_id = ?
                AND date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
            GROUP BY campaign_id
        `, [id, period]);
        
        if (campaign.length === 0) {
            return res.status(404).json({
                success: false,
                error: 'Campaign not found'
            });
        }
        
        // Получаем детальную разбивку
        const segments = await getSegmentBreakdown(id, period);
        const tokenAnalysis = await analyzeTokens(id, period);
        const volatility = await getVolatility(id);
        
        res.json({
            success: true,
            data: {
                ...campaign[0],
                volatility_score: volatility,
                segments,
                token_analysis: tokenAnalysis
            }
        });
        
    } catch (error) {
        console.error('Error fetching campaign details:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// =====================================================
// HELPER FUNCTIONS
// =====================================================

/**
 * Получить сегментацию кампании
 */
async function getSegmentBreakdown(campaignId, days) {
    const [segments] = await pool.execute(`
        SELECT 
            'OS' as segment_type,
            os as segment_value,
            SUM(click) as clicks,
            SUM(conversion) as conversions,
            SUM(conversion * payout) - SUM(cost) as impact,
            SUM(conversion * payout) as revenue,
            SUM(cost) as cost
        FROM campaign_data
        WHERE campaign_id = ?
            AND date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
            AND os IS NOT NULL
        GROUP BY os
        
        UNION ALL
        
        SELECT 
            'Device' as segment_type,
            device_type as segment_value,
            SUM(click) as clicks,
            SUM(conversion) as conversions,
            SUM(conversion * payout) - SUM(cost) as impact,
            SUM(conversion * payout) as revenue,
            SUM(cost) as cost
        FROM campaign_data
        WHERE campaign_id = ?
            AND date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
            AND device_type IS NOT NULL
        GROUP BY device_type
        
        UNION ALL
        
        SELECT 
            'Token2' as segment_type,
            token_2 as segment_value,
            SUM(click) as clicks,
            SUM(conversion) as conversions,
            SUM(conversion * payout) - SUM(cost) as impact,
            SUM(conversion * payout) as revenue,
            SUM(cost) as cost
        FROM campaign_data
        WHERE campaign_id = ?
            AND date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
            AND token_2 IS NOT NULL
        GROUP BY token_2
        
        ORDER BY impact DESC
    `, [campaignId, days, campaignId, days, campaignId, days]);
    
    // Разделяем на лучшие и худшие
    const sorted = segments.sort((a, b) => b.impact - a.impact);
    
    return {
        best: sorted.slice(0, 5),
        worst: sorted.slice(-3)
    };
}

/**
 * Получить тренд за N дней
 */
async function getTrend(campaignId, days) {
    const [trend] = await pool.execute(`
        SELECT 
            date,
            ((SUM(conversion * payout) - SUM(cost)) / SUM(cost)) * 100 as daily_roi
        FROM campaign_data
        WHERE campaign_id = ?
            AND date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
        GROUP BY date
        ORDER BY date DESC
    `, [campaignId, days]);
    
    return trend.map(t => Math.round(t.daily_roi));
}

/**
 * Получить волатильность кампании
 */
async function getVolatility(campaignId) {
    const [result] = await pool.execute(
        'SELECT calculate_volatility(?, ?) as volatility',
        [campaignId, 14]
    );
    
    return result[0].volatility;
}

/**
 * Анализ токенов (вызов Python скрипта)
 */
async function analyzeTokens(campaignId, days) {
    try {
        const output = execSync(
            `python3 ../scripts/analyze_tokens.py ${campaignId} ${days}`,
            { encoding: 'utf-8' }
        );
        
        return JSON.parse(output);
    } catch (error) {
        console.error('Token analysis error:', error);
        return { patterns: [] };
    }
}

/**
 * Обновление весов системы обучения
 */
async function updateLearningWeights(campaignId, action, volatility) {
    if (action === 'SCALE') {
        // Увеличиваем веса для похожих паттернов
        const multiplier = volatility > 15 ? 1.15 : 1.1;
        
        await pool.execute(`
            UPDATE learning_weights
            SET 
                volatility_weight = volatility_weight * ?,
                score_multiplier = score_multiplier * ?
            WHERE pattern_type = 'high_volatility'
        `, [multiplier, multiplier]);
        
    } else if (action === 'OPTIMIZE') {
        // Снижаем веса
        await pool.execute(`
            UPDATE learning_weights
            SET score_multiplier = score_multiplier * 0.9
            WHERE pattern_type IN (
                SELECT pattern_type FROM campaign_patterns
                WHERE campaign_id = ?
            )
        `, [campaignId]);
    }
}

/**
 * Вызов AI Council (симуляция LLM)
 */
async function callAICouncil(campaignData) {
    // В реальной реализации здесь будет вызов OpenAI/Anthropic API
    // Сейчас возвращаем mock данные
    
    const totalRevenue = campaignData.reduce((sum, row) => sum + (row.conversion * row.payout), 0);
    const totalCost = campaignData.reduce((sum, row) => sum + row.cost, 0);
    const roi = ((totalRevenue - totalCost) / totalCost) * 100;
    
    let recommendation = 'HOLD';
    let reasoning = 'Insufficient data for strong recommendation';
    
    if (roi > 150) {
        recommendation = 'SCALE';
        reasoning = 'High ROI with potential for scaling. Consider increasing budget by 50%.';
    } else if (roi < 50) {
        recommendation = 'OPTIMIZE';
        reasoning = 'Low ROI. Focus on improving conversion rate and reducing costs.';
    }
    
    return {
        recommendation,
        reasoning,
        specific_actions: [
            'Increase budget for top-performing segments',
            'Pause underperforming creatives',
            'Test new landing pages'
        ],
        confidence_score: 75.5
    };
}

// =====================================================
// SERVER START
// =====================================================

app.listen(PORT, () => {
    console.log(`🚀 TOP-5 Analysis Bot Server running on port ${PORT}`);
    console.log(`📊 API endpoint: http://localhost:${PORT}/api/top5`);
});

module.exports = app;
