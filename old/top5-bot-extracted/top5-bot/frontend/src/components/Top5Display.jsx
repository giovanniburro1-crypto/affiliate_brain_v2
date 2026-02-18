import React, { useState, useEffect } from 'react';
import './Top5Display.css';

/**
 * TOP-5 Analysis Bot - Frontend Component
 * Отображение топ-5 кампаний с возможностью выбора действий
 */

const Top5Display = () => {
    const [campaigns, setCampaigns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [period, setPeriod] = useState(30);
    const [selectedActions, setSelectedActions] = useState({});
    const [hideDurations, setHideDurations] = useState({});

    // Загрузка данных при монтировании
    useEffect(() => {
        fetchTop5();
    }, [period]);

    // Получить TOP-5 кампаний
    const fetchTop5 = async () => {
        setLoading(true);
        try {
            const response = await fetch(
                `http://localhost:3000/api/top5?period=${period}`
            );
            const data = await response.json();
            
            if (data.success) {
                setCampaigns(data.data);
                
                // Инициализируем действия по умолчанию
                const defaultActions = {};
                const defaultDurations = {};
                
                data.data.forEach(campaign => {
                    defaultActions[campaign.campaign_id] = 'SCALE';
                    defaultDurations[campaign.campaign_id] = 3;
                });
                
                setSelectedActions(defaultActions);
                setHideDurations(defaultDurations);
            }
        } catch (error) {
            console.error('Error fetching TOP-5:', error);
        } finally {
            setLoading(false);
        }
    };

    // Применить действие
    const applyAction = async (campaignId) => {
        const action = selectedActions[campaignId];
        const hideDuration = hideDurations[campaignId];

        try {
            const response = await fetch('http://localhost:3000/api/apply-action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    campaign_id: campaignId,
                    action: action,
                    hide_duration: hideDuration
                })
            });

            const data = await response.json();
            
            if (data.success) {
                alert('Action applied successfully!');
                fetchTop5(); // Обновляем список
            }
        } catch (error) {
            console.error('Error applying action:', error);
            alert('Failed to apply action');
        }
    };

    // Вызов AI Council
    const callAICouncil = async (campaignId) => {
        try {
            const response = await fetch(
                `http://localhost:3000/api/ai-council/${campaignId}`,
                { method: 'POST' }
            );
            
            const data = await response.json();
            
            if (data.success) {
                alert(`AI Recommendation: ${data.data.recommendation}\n\n${data.data.reasoning}`);
            }
        } catch (error) {
            console.error('Error calling AI Council:', error);
        }
    };

    // Получить цвет для score
    const getScoreColor = (score) => {
        if (score >= 90) return '#059669'; // Тёмно-зелёный
        if (score >= 80) return '#16a34a'; // Светло-зелёный
        if (score >= 70) return '#eab308'; // Жёлтый
        return '#6b7280'; // Серый
    };

    // Форматирование волатильности
    const formatVolatility = (campaign) => {
        const vol = campaign.volatility_score || 0;
        const days = 3; // Можно динамически менять
        const growth = campaign.growth_3d || 0;
        
        return `volatility ${vol.toFixed(1)}% data for ${days} days ${growth > 0 ? '+' : ''}${growth.toFixed(1)}%`;
    };

    if (loading) {
        return <div className="loading">Loading TOP-5 campaigns...</div>;
    }

    return (
        <div className="top5-container">
            <header className="top5-header">
                <h1>🏆 TOP-5 SCALE OPPORTUNITIES</h1>
                <div className="header-controls">
                    <label>
                        Period:
                        <select value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
                            <option value={7}>Last 7 days</option>
                            <option value={14}>Last 14 days</option>
                            <option value={30}>Last 30 days</option>
                        </select>
                    </label>
                    <button className="refresh-btn" onClick={fetchTop5}>
                        🔄 Refresh
                    </button>
                </div>
                <p className="update-time">Updated: {new Date().toLocaleString()}</p>
            </header>

            <div className="campaigns-list">
                {campaigns.map((campaign, index) => (
                    <div key={campaign.campaign_id} className="campaign-card">
                        {/* Заголовок */}
                        <div className="campaign-header">
                            <div className="campaign-title">
                                <h3>
                                    #{index + 1} {campaign.campaign_id}
                                </h3>
                                <div className="campaign-metrics">
                                    ROI {campaign.roi?.toFixed(0)}% •
                                    Profit ${campaign.impact?.toFixed(0)} •
                                    Spend ${campaign.total_cost?.toFixed(0)} •
                                    Clicks {campaign.total_clicks} •
                                    Conv {campaign.total_conversions}
                                </div>
                            </div>
                            <div 
                                className="score-badge"
                                style={{ backgroundColor: getScoreColor(campaign.score_percentage) }}
                            >
                                {campaign.score_percentage}%
                            </div>
                        </div>

                        {/* Волатильность */}
                        <div className="volatility-section">
                            <span className="action-label scale">SCALE</span>
                            <span className="volatility-text">
                                {formatVolatility(campaign)}
                            </span>
                        </div>

                        {/* Тренд */}
                        {campaign.trend_data && campaign.trend_data.length > 0 && (
                            <div className="trend-info">
                                ↗ last {campaign.trend_data.length} days:{' '}
                                {campaign.trend_data.join('%, ')}%
                            </div>
                        )}

                        {/* Лучшие сегменты */}
                        <div className="segments-section">
                            {campaign.best_segments?.slice(0, 4).map((segment, idx) => (
                                <div key={idx} className="segment-row best">
                                    <span className="segment-label">
                                        best {segment.segment_type} {segment.segment_value}
                                    </span>
                                    <span className="segment-metrics">
                                        Clicks {segment.clicks} |
                                        Conv {segment.conversions} |
                                        Impact ${segment.impact?.toFixed(0)} |
                                        Rev ${segment.revenue?.toFixed(0)} |
                                        Cost ${segment.cost?.toFixed(0)}
                                    </span>
                                </div>
                            ))}
                        </div>

                        {/* Худшие сегменты */}
                        {campaign.worst_segments && campaign.worst_segments.length > 0 && (
                            <div className="segments-section">
                                {campaign.worst_segments.map((segment, idx) => (
                                    <div key={idx} className="segment-row worst">
                                        <span className="segment-label">
                                            worst {segment.segment_type} {segment.segment_value}
                                        </span>
                                        <span className="segment-metrics">
                                            Clicks {segment.clicks} |
                                            Conv {segment.conversions} |
                                            Impact ${segment.impact?.toFixed(0)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Кнопки действий */}
                        <div className="action-buttons">
                            <div className="radio-group">
                                <label>
                                    <input
                                        type="radio"
                                        name={`action_${campaign.campaign_id}`}
                                        value="SCALE"
                                        checked={selectedActions[campaign.campaign_id] === 'SCALE'}
                                        onChange={(e) => setSelectedActions({
                                            ...selectedActions,
                                            [campaign.campaign_id]: e.target.value
                                        })}
                                    />
                                    SCALE
                                </label>
                                <label>
                                    <input
                                        type="radio"
                                        name={`action_${campaign.campaign_id}`}
                                        value="HOLD"
                                        checked={selectedActions[campaign.campaign_id] === 'HOLD'}
                                        onChange={(e) => setSelectedActions({
                                            ...selectedActions,
                                            [campaign.campaign_id]: e.target.value
                                        })}
                                    />
                                    HOLD
                                </label>
                                <label>
                                    <input
                                        type="radio"
                                        name={`action_${campaign.campaign_id}`}
                                        value="OPTIMIZE"
                                        checked={selectedActions[campaign.campaign_id] === 'OPTIMIZE'}
                                        onChange={(e) => setSelectedActions({
                                            ...selectedActions,
                                            [campaign.campaign_id]: e.target.value
                                        })}
                                    />
                                    OPTIMIZE
                                </label>
                            </div>

                            <select
                                className="hide-duration"
                                value={hideDurations[campaign.campaign_id]}
                                onChange={(e) => setHideDurations({
                                    ...hideDurations,
                                    [campaign.campaign_id]: Number(e.target.value)
                                })}
                            >
                                <option value={3}>Hide for: 3 days</option>
                                <option value={7}>7 days</option>
                                <option value={14}>14 days</option>
                                <option value={30}>30 days</option>
                            </select>

                            <button
                                className="apply-btn"
                                onClick={() => applyAction(campaign.campaign_id)}
                            >
                                Apply
                            </button>

                            <button
                                className="council-btn"
                                onClick={() => callAICouncil(campaign.campaign_id)}
                            >
                                Call AI Council
                            </button>
                        </div>
                    </div>
                ))}
            </div>

            {campaigns.length === 0 && (
                <div className="no-campaigns">
                    No campaigns found matching TOP-5 criteria.
                    Try adjusting the period or check your data.
                </div>
            )}
        </div>
    );
};

export default Top5Display;
