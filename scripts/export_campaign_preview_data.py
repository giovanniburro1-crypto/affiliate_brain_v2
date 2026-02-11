"""
Скрипт для экспорта данных кампании в JSON.
Используется для встраивания в standalone HTML визуал.
Запуск: python scripts/export_campaign_preview_data.py [campaign_id]
Если campaign_id не указан — берётся первая кампания с spend > 100.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def main():
    from backend.database import SessionLocal
    from backend.services.top5_service import Top5Service
    from backend.brain import KnowledgeBase
    from backend.services.campaign_analysis_service import get_parameter_conclusions
    from backend.routers.metrics import get_campaign_breakdown_data, get_campaign_daily_days
    
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else None
    db = SessionLocal()
    
    try:
        brain = KnowledgeBase()
        service = Top5Service(db, brain)
        today = date.today()
        date_from = today - timedelta(days=14)
        date_to = today
        
        from sqlalchemy import text
        if campaign_id:
            analysis = service.get_campaign_analysis(campaign_id, 14, date_from.isoformat(), date_to.isoformat())
        else:
            rows = db.execute(
                text("""
                    SELECT campaign_id FROM traffic_stats
                    WHERE date >= :d AND date <= :d_to
                    GROUP BY campaign_id
                    HAVING SUM(cost) >= 100
                    ORDER BY SUM(revenue) - SUM(cost) DESC
                    LIMIT 1
                """),
                {"d": date_from, "d_to": date_to}
            ).fetchone()
            if not rows:
                print(json.dumps({"error": "No campaigns found"}, ensure_ascii=False))
                return
            campaign_id = rows[0]
            analysis = service.get_campaign_analysis(campaign_id, 14, date_from.isoformat(), date_to.isoformat())
        
        if not analysis:
            print(json.dumps({"error": "Campaign not found"}, ensure_ascii=False))
            return
        
        breakdown = get_campaign_breakdown_data(db, campaign_id, date_from, date_to)
        daily_days = get_campaign_daily_days(db, campaign_id, date_from, date_to, None)
        volatility = analysis.get("volatility", 0) or 0
        parameter_conclusions = get_parameter_conclusions(
            breakdown=breakdown,
            campaign_summary=breakdown.get("summary", {}),
            volatility=volatility,
            brain=brain,
        )
        
        result = {
            "success": True,
            "campaign_id": campaign_id,
            "analysis": analysis,
            "parameter_conclusions": parameter_conclusions,
            "breakdown": breakdown,
            "days": daily_days,
        }
        
        out_path = project_root / "frontend" / "campaign-preview-data.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Exported to {out_path}")
        
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
    finally:
        db.close()

if __name__ == "__main__":
    main()
