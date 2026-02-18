"""
Learning Service — обучение системы на основе решений пользователя.
Обновляет веса блоков знаний в зависимости от правильности их рекомендаций.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from backend.brain.knowledge_base_v2_complete import KnowledgeBaseV2


class LearningService:
    def __init__(self, db: Session, brain: Optional[KnowledgeBaseV2] = None):
        self.db = db
        self.brain = brain or KnowledgeBaseV2()
    
    def record_user_decision(
        self,
        campaign_id: str,
        user_verdict: str,
        confidence: float,
        recheck_after_days: int = 0,
        period: int = 30,
        date_from_str: Optional[str] = None,
        date_to_str: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Записать решение пользователя и создать запись для последующей оценки.
        
        Args:
            campaign_id: ID кампании
            user_verdict: Решение пользователя (SCALE, HOLD, OPTIMIZE, STOP)
            confidence: Уверенность пользователя (0-100)
            recheck_after_days: Через сколько дней проверить результат
            period: Период анализа
            date_from_str: Начальная дата (опционально)
            date_to_str: Конечная дата (опционально)
        
        Returns:
            Словарь с результатом операции
        """
        # Получаем текущие голоса блоков для этой кампании
        try:
            # Получаем метрики кампании
            date_from, date_to = self._get_date_range(period, date_from_str, date_to_str)
            
            # Получаем данные кампании
            campaign_data = self._get_campaign_data(campaign_id, date_from, date_to)
            if not campaign_data:
                return {"success": False, "error": "Campaign not found"}
            
            # Получаем голоса блоков через brain
            block_votes = self.brain.analyze_campaign(
                campaign_id=campaign_id,
                roi=campaign_data["roi"],
                profit=campaign_data["profit"],
                spend=campaign_data["spend"],
                clicks=campaign_data["clicks"],
                conversions=campaign_data["conversions"],
                volatility=campaign_data["volatility"],
                daily_impact=campaign_data["daily_impact"]
            ).get("block_votes", [])
            
            # Записываем решение в базу
            self.db.execute(
                text("""
                    INSERT INTO user_decisions (
                        campaign_id, decision_date, user_verdict, user_confidence,
                        recheck_after_days, period_days, date_from, date_to,
                        campaign_roi, campaign_profit, campaign_spend,
                        campaign_clicks, campaign_conversions, campaign_volatility,
                        block_votes_json, needs_outcome_update, is_training_example
                    ) VALUES (
                        :cid, :now, :verdict, :confidence, :recheck, :period,
                        :date_from, :date_to, :roi, :profit, :spend, :clicks,
                        :conversions, :volatility, :block_votes, :needs_update, :training
                    )
                """),
                {
                    "cid": campaign_id,
                    "now": date.today(),
                    "verdict": user_verdict,
                    "confidence": confidence,
                    "recheck": recheck_after_days,
                    "period": period,
                    "date_from": date_from,
                    "date_to": date_to,
                    "roi": campaign_data["roi"],
                    "profit": campaign_data["profit"],
                    "spend": campaign_data["spend"],
                    "clicks": campaign_data["clicks"],
                    "conversions": campaign_data["conversions"],
                    "volatility": campaign_data["volatility"],
                    "block_votes": json.dumps(block_votes),
                    "needs_update": True,
                    "training": True
                }
            )
            self.db.commit()
            
            return {
                "success": True,
                "message": "Decision recorded",
                "recheck_date": date.today() + timedelta(days=recheck_after_days) if recheck_after_days > 0 else None
            }
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def update_outcomes(self) -> Dict[str, any]:
        """
        Обновить результаты для решений, которые нуждаются в оценке.
        Сравнивает ROI через 7 и 14 дней после решения.
        
        Returns:
            Статистика обновлений
        """
        try:
            # Находим решения, которые нужно обновить
            decisions = self.db.execute(
                text("""
                    SELECT id, campaign_id, decision_date, user_verdict, block_votes_json
                    FROM user_decisions
                    WHERE needs_outcome_update = TRUE
                      AND decision_date <= DATE('now', '-14 days')
                    LIMIT 100
                """)
            ).fetchall()
            
            updated_count = 0
            for decision in decisions:
                decision_id = decision[0]
                campaign_id = decision[1]
                decision_date = decision[2]
                user_verdict = decision[3]
                block_votes_json = decision[4]
                
                # Получаем ROI через 7 и 14 дней после решения
                roi_7d = self._get_roi_after_days(campaign_id, decision_date, 7)
                roi_14d = self._get_roi_after_days(campaign_id, decision_date, 14)
                
                # Определяем, было ли решение правильным
                # Правила оценки:
                # - SCALE: ROI через 7 дней > 15% или ROI через 14 дней > 20%
                # - STOP: ROI через 7 дней < -20% или ROI через 14 дней < -30%
                # - OPTIMIZE: ROI улучшился на 5+ процентных пунктов
                # - HOLD: ROI остался в пределах ±10%
                
                outcome_verdict = self._evaluate_decision(user_verdict, roi_7d, roi_14d)
                
                # Обновляем запись
                self.db.execute(
                    text("""
                        UPDATE user_decisions
                        SET outcome_verdict = :outcome,
                            outcome_roi_7d = :roi7,
                            outcome_roi_14d = :roi14,
                            needs_outcome_update = FALSE,
                            outcome_updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {
                        "outcome": outcome_verdict,
                        "roi7": roi_7d,
                        "roi14": roi_14d,
                        "id": decision_id
                    }
                )
                
                # Если есть голоса блоков, обновляем веса
                if block_votes_json:
                    block_votes = json.loads(block_votes_json)
                    self._update_block_weights(block_votes, outcome_verdict, user_verdict)
                
                updated_count += 1
            
            self.db.commit()
            
            return {
                "success": True,
                "updated_count": updated_count,
                "message": f"Updated {updated_count} decision outcomes"
            }
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def get_learning_stats(self) -> Dict[str, any]:
        """
        Получить статистику обучения системы.
        
        Returns:
            Статистика по циклам обучения и точности блоков
        """
        try:
            # Статистика по циклам обучения
            cycles = self.db.execute(
                text("""
                    SELECT 
                        COUNT(*) as total_cycles,
                        SUM(CASE WHEN is_completed THEN 1 ELSE 0 END) as completed_cycles,
                        AVG(correct_decisions * 100.0 / NULLIF(total_decisions, 0)) as avg_accuracy
                    FROM learning_cycles
                """)
            ).fetchone()
            
            # Статистика по решениям
            decisions = self.db.execute(
                text("""
                    SELECT 
                        COUNT(*) as total_decisions,
                        SUM(CASE WHEN outcome_verdict = 'CORRECT' THEN 1 ELSE 0 END) as correct_decisions,
                        SUM(CASE WHEN outcome_verdict = 'INCORRECT' THEN 1 ELSE 0 END) as incorrect_decisions,
                        SUM(CASE WHEN outcome_verdict IS NULL THEN 1 ELSE 0 END) as pending_decisions
                    FROM user_decisions
                    WHERE is_training_example = TRUE
                """)
            ).fetchone()
            
            # Веса блоков
            blocks = self.brain.get_all_blocks()
            block_stats = []
            for block in blocks:
                block_stats.append({
                    "name": block.name,
                    "weight": block.weight,
                    "description": block.description[:50] + "..." if len(block.description) > 50 else block.description
                })
            
            return {
                "success": True,
                "cycles": {
                    "total": cycles[0] or 0,
                    "completed": cycles[1] or 0,
                    "avg_accuracy": round(cycles[2] or 0, 1)
                },
                "decisions": {
                    "total": decisions[0] or 0,
                    "correct": decisions[1] or 0,
                    "incorrect": decisions[2] or 0,
                    "pending": decisions[3] or 0,
                    "accuracy": round((decisions[1] or 0) * 100.0 / max(1, (decisions[0] or 0) - (decisions[3] or 0)), 1)
                },
                "blocks": block_stats
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def start_learning_cycle(self) -> Dict[str, any]:
        """
        Начать новый цикл обучения.
        
        Returns:
            Результат операции
        """
        try:
            # Проверяем, есть ли активные циклы
            active = self.db.execute(
                text("SELECT COUNT(*) FROM learning_cycles WHERE is_completed = FALSE")
            ).scalar()
            
            if active > 0:
                return {"success": False, "error": "Active learning cycle already exists"}
            
            # Создаем новый цикл
            self.db.execute(
                text("""
                    INSERT INTO learning_cycles (
                        cycle_start, cycle_end, total_decisions, correct_decisions,
                        accuracy_percent, is_completed
                    ) VALUES (
                        CURRENT_DATE, NULL, 0, 0, 0.0, FALSE
                    )
                """)
            )
            self.db.commit()
            
            return {"success": True, "message": "New learning cycle started"}
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def complete_learning_cycle(self) -> Dict[str, any]:
        """
        Завершить текущий цикл обучения и обновить статистику.
        
        Returns:
            Результат операции
        """
        try:
            # Находим активный цикл
            cycle = self.db.execute(
                text("""
                    SELECT id, cycle_start FROM learning_cycles 
                    WHERE is_completed = FALSE 
                    ORDER BY cycle_start DESC 
                    LIMIT 1
                """)
            ).fetchone()
            
            if not cycle:
                return {"success": False, "error": "No active learning cycle found"}
            
            cycle_id = cycle[0]
            cycle_start = cycle[1]
            
            # Получаем статистику решений за этот период
            stats = self.db.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN outcome_verdict = 'CORRECT' THEN 1 ELSE 0 END) as correct
                    FROM user_decisions
                    WHERE decision_date >= :start_date
                      AND decision_date <= CURRENT_DATE
                      AND is_training_example = TRUE
                      AND outcome_verdict IS NOT NULL
                """),
                {"start_date": cycle_start}
            ).fetchone()
            
            total = stats[0] or 0
            correct = stats[1] or 0
            accuracy = (correct * 100.0 / total) if total > 0 else 0.0
            
            # Обновляем цикл
            self.db.execute(
                text("""
                    UPDATE learning_cycles
                    SET cycle_end = CURRENT_DATE,
                        total_decisions = :total,
                        correct_decisions = :correct,
                        accuracy_percent = :accuracy,
                        is_completed = TRUE
                    WHERE id = :id
                """),
                {
                    "id": cycle_id,
                    "total": total,
                    "correct": correct,
                    "accuracy": accuracy
                }
            )
            self.db.commit()
            
            return {
                "success": True,
                "message": f"Learning cycle completed: {correct}/{total} correct ({accuracy:.1f}%)"
            }
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _get_date_range(
        self,
        period: int,
        date_from_str: Optional[str],
        date_to_str: Optional[str],
    ) -> Tuple[date, date]:
        """Получить диапазон дат."""
        today = date.today()
        if date_from_str and date_to_str:
            try:
                d_from = date.fromisoformat(date_from_str.strip()[:10])
                d_to = date.fromisoformat(date_to_str.strip()[:10])
                if d_from <= d_to:
                    return (d_from, d_to)
            except (ValueError, TypeError):
                pass
        return (today - timedelta(days=period), today)
    
    def _get_campaign_data(self, campaign_id: str, date_from: date, date_to: date) -> Optional[Dict]:
        """Получить данные кампании."""
        row = self.db.execute(
            text("""
                SELECT 
                    SUM(cost), SUM(revenue), SUM(conversions), COUNT(*)
                FROM traffic_stats
                WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
                GROUP BY campaign_id
            """),
            {"cid": campaign_id, "d": date_from, "d_to": date_to}
        ).fetchone()
        
        if not row:
            return None
        
        spend = float(row[0] or 0)
        revenue = float(row[1] or 0)
        conversions = int(row[2] or 0)
        clicks = int(row[3] or 0)
        profit = revenue - spend
        roi = ((revenue - spend) / spend * 100) if spend > 0 else 0.0
        
        # Получаем дневные метрики для волатильности
        daily = self.db.execute(
            text("""
                SELECT date, SUM(cost), SUM(revenue)
                FROM traffic_stats
                WHERE campaign_id = :cid AND date >= :d AND date <= :d_to
                GROUP BY date
                ORDER BY date
            """),
            {"cid": campaign_id, "d": date_from, "d_to": date_to}
        ).fetchall()
        
        daily_impact = []
        for d in daily:
            cost = float(d[1] or 0)
            rev = float(d[2] or 0)
            daily_impact.append(rev - cost)
        
        # Рассчитываем волатильность
        volatility = 0.0
        if len(daily_impact) >= 3:
            mean = sum(daily_impact) / len(daily_impact)
            if mean != 0:
                variance = sum((x - mean) ** 2 for x in daily_impact) / len(daily_impact)
                std = (variance ** 0.5) if variance > 0 else 0
                volatility = (std / abs(mean)) * 100
        
        return {
            "roi": roi,
            "profit": profit,
            "spend": spend,
            "clicks": clicks,
            "conversions": conversions,
            "volatility": volatility,
            "daily_impact": daily_impact
        }
    
    def _get_roi_after_days(self, campaign_id: str, decision_date: date, days: int) -> Optional[float]:
        """Получить ROI через указанное количество дней после решения."""
        start_date = decision_date
        end_date = decision_date + timedelta(days=days)
        
        row = self.db.execute(
            text("""
                SELECT SUM(cost), SUM(revenue)
                FROM traffic_stats
                WHERE campaign_id = :cid AND date >= :start AND date <= :end
            """),
            {"cid": campaign_id, "start": start_date, "end": end_date}
        ).fetchone()
        
        if not row:
            return None
        
        spend = float(row[0] or 0)
        revenue = float(row[1] or 0)
        
        if spend == 0:
            return None
        
        return ((revenue - spend) / spend * 100)
    
    def _evaluate_decision(self, user_verdict: str, roi_7d: Optional[float], roi_14d: Optional[float]) -> str:
        """Оценить правильность решения пользователя."""
        if roi_7d is None or roi_14d is None:
            return "UNKNOWN"
        
        if user_verdict == "SCALE":
            # SCALE считается правильным, если ROI положительный и растущий
            if roi_7d > 15 or roi_14d > 20:
                return "CORRECT"
            elif roi_7d < -10 or roi_14d < -15:
                return "INCORRECT"
            else:
                return "NEUTRAL"
        
        elif user_verdict == "STOP":
            # STOP считается правильным, если ROI отрицательный и ухудшается
            if roi_7d < -20 or roi_14d < -30:
                return "CORRECT"
            elif roi_7d > 10 or roi_14d > 15:
                return "INCORRECT"
            else:
                return "NEUTRAL"
        
        elif user_verdict == "OPTIMIZE":
            # OPTIMIZE считается правильным, если ROI улучшился
            roi_change = roi_14d - roi_7d if roi_7d is not None and roi_14d is not None else 0
            if roi_change > 5:
                return "CORRECT"
            elif roi_change < -5:
                return "INCORRECT"
            else:
                return "NEUTRAL"
        
        elif user_verdict == "HOLD":
            # HOLD считается правильным, если ROI остался стабильным
            if -10 <= roi_7d <= 10 and -10 <= roi_14d <= 10:
                return "CORRECT"
            elif roi_7d > 20 or roi_14d > 25 or roi_7d < -20 or roi_14d < -25:
                return "INCORRECT"
            else:
                return "NEUTRAL"
        
        return "UNKNOWN"
    
    def _update_block_weights(self, block_votes: List[Dict], outcome_verdict: str, user_verdict: str) -> None:
        """Обновить веса блоков на основе результатов решения."""
        if outcome_verdict == "UNKNOWN":
            return
        
        # Определяем, были ли голоса блоков правильными
        for vote in block_votes:
            block_name = vote.get("block_name")
            block_verdict = vote.get("verdict")
            block_confidence = vote.get("confidence", 0)
            
            if not block_name or not block_verdict:
                continue
            
            # Определяем, был ли голос блока правильным
            # Блок считается правильным, если его вердикт совпадает с итоговой оценкой
            was_correct = False
            
            if outcome_verdict == "CORRECT":
                # Если решение пользователя было правильным, блоки, которые голосовали
                # за тот же вердикт, считаются правильными
                if block_verdict == user_verdict:
                    was_correct = True
            elif outcome_verdict == "INCORRECT":
                # Если решение пользователя было неправильным, блоки, которые голосовали
                # за противоположный вердикт, могут считаться правильными
                # (это сложная логика, упростим)
                if block_verdict != user_verdict:
                    # Проверяем, был ли альтернативный вердикт лучше
                    if user_verdict == "SCALE" and block_verdict == "STOP":
                        was_correct = True
                    elif user_verdict == "STOP" and block_verdict == "SCALE":
                        was_correct = True
                    elif user_verdict == "OPTIMIZE" and block_verdict == "HOLD":
                        was_correct = True
                    elif user_verdict == "HOLD" and block_verdict == "OPTIMIZE":
                        was_correct = True
            
            # Обновляем вес блока
            learning_rate = 0.1 * (block_confidence / 100.0)  # Учитываем уверенность блока
            self.brain.update_block_weight(block_name, was_correct, learning_rate)
