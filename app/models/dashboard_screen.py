# 数智大屏数据聚合仓储 — 跨模块全量统计查询

import time
from app.models.db import get_connection


class DashboardRepository:
    """数智大屏聚合数据查询"""

    @staticmethod
    def get_core_metrics():
        """核心指标：总用户/总会话/总消息/总Token/活跃会话"""
        with get_connection() as conn:
            total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            total_convs = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
            total_msgs = conn.execute("SELECT COUNT(*) AS c FROM chat_messages").fetchone()["c"]
            total_tokens = conn.execute(
                "SELECT COALESCE(SUM(tokens_used), 0) AS c FROM chat_messages"
            ).fetchone()["c"]
            active_convs = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE status='active'"
            ).fetchone()["c"]
            total_employees = conn.execute("SELECT COUNT(*) AS c FROM digital_employees").fetchone()["c"]
            total_skills = conn.execute("SELECT COUNT(*) AS c FROM ai_skills").fetchone()["c"]
            total_apis = conn.execute("SELECT COUNT(*) AS c FROM api_interfaces").fetchone()["c"]
            total_watch = conn.execute("SELECT COUNT(*) AS c FROM watch_sources").fetchone()["c"]
            flagged_msgs = conn.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE review_status='flagged'"
            ).fetchone()["c"]
        return {
            "users": total_users,
            "conversations": total_convs,
            "messages": total_msgs,
            "tokens": total_tokens,
            "active_convs": active_convs,
            "employees": total_employees,
            "skills": total_skills,
            "apis": total_apis,
            "watch_sources": total_watch,
            "flagged": flagged_msgs,
            "timestamp": int(time.time()),
        }

    @staticmethod
    def get_message_trend(days: int = 7):
        """最近N天消息趋势（按小时聚合）"""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT DATE(created_at) AS d, COUNT(*) AS cnt
                   FROM chat_messages
                   WHERE created_at >= datetime('now', '-' || ? || ' days')
                   GROUP BY d ORDER BY d""",
                (days,)
            ).fetchall()
        return [{"date": r["d"], "count": r["cnt"]} for r in rows]

    @staticmethod
    def get_role_distribution():
        """用户/AI 消息分布"""
        with get_connection() as conn:
            user_cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE role='user'"
            ).fetchone()["c"]
            ai_cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE role='assistant'"
            ).fetchone()["c"]
        return [
            {"name": "用户消息", "value": user_cnt},
            {"name": "AI消息", "value": ai_cnt},
        ]

    @staticmethod
    def get_model_usage():
        """模型调用分布"""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT COALESCE(c.model_name, '默认') AS model, COUNT(*) AS cnt
                   FROM chat_messages cm
                   JOIN conversations c ON cm.conversation_id = c.id
                   GROUP BY c.model_name
                   ORDER BY cnt DESC
                   LIMIT 10"""
            ).fetchall()
        return [{"name": r["model"], "count": r["cnt"]} for r in rows]

    @staticmethod
    def get_skill_calls():
        """技能调用分布"""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT name, call_count FROM ai_skills
                   WHERE call_count > 0
                   ORDER BY call_count DESC LIMIT 10"""
            ).fetchall()
        return [{"name": r["name"], "count": r["call_count"]} for r in rows]

    @staticmethod
    def get_hourly_activity():
        """最近24小时按小时活跃度"""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT strftime('%H', created_at) AS h, COUNT(*) AS cnt
                   FROM chat_messages
                   WHERE created_at >= datetime('now', '-24 hours')
                   GROUP BY h ORDER BY h"""
            ).fetchall()
        result = {str(i).zfill(2): 0 for i in range(24)}
        for r in rows:
            result[r["h"]] = r["cnt"]
        return [{"hour": k, "count": v} for k, v in result.items()]

    @staticmethod
    def get_risk_alerts():
        """风险预警列表"""
        alerts = []
        with get_connection() as conn:
            # 已标记消息
            flagged = conn.execute(
                """SELECT 'flag' AS type, cm.id, cm.content, u.username, cm.created_at
                   FROM chat_messages cm
                   JOIN conversations c ON cm.conversation_id = c.id
                   LEFT JOIN users u ON c.user_id = u.id
                   WHERE cm.review_status = 'flagged'
                   ORDER BY cm.id DESC LIMIT 5"""
            ).fetchall()
            for r in flagged:
                alerts.append({
                    "type": "content_risk",
                    "level": "warning",
                    "title": "敏感内容标记",
                    "detail": f"用户 {r['username']}: {r['content'][:50]}...",
                    "time": r["created_at"],
                })
            # 高Token消息
            high_tokens = conn.execute(
                """SELECT cm.id, cm.tokens_used, u.username, cm.created_at
                   FROM chat_messages cm
                   JOIN conversations c ON cm.conversation_id = c.id
                   LEFT JOIN users u ON c.user_id = u.id
                   WHERE cm.tokens_used > 500
                   ORDER BY cm.tokens_used DESC LIMIT 5"""
            ).fetchall()
            for r in high_tokens:
                alerts.append({
                    "type": "high_token",
                    "level": "info",
                    "title": "高Token消耗",
                    "detail": f"用户 {r['username']}: 单条 {r['tokens_used']} tokens",
                    "time": r["created_at"],
                })
        return alerts

    @staticmethod
    def get_live_messages(limit: int = 10):
        """实时最新消息"""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT cm.role, cm.content, u.username, cm.created_at
                   FROM chat_messages cm
                   JOIN conversations c ON cm.conversation_id = c.id
                   LEFT JOIN users u ON c.user_id = u.id
                   ORDER BY cm.id DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return [
            {
                "role": r["role"],
                "username": r["username"] or "-",
                "content": (r["content"] or "")[:80],
                "time": r["created_at"],
            }
            for r in rows
        ]

    @staticmethod
    def get_all_data():
        """一次性获取全部大屏数据"""
        return {
            "metrics": DashboardRepository.get_core_metrics(),
            "trend": DashboardRepository.get_message_trend(7),
            "distribution": DashboardRepository.get_role_distribution(),
            "model_usage": DashboardRepository.get_model_usage(),
            "skill_calls": DashboardRepository.get_skill_calls(),
            "hourly": DashboardRepository.get_hourly_activity(),
            "alerts": DashboardRepository.get_risk_alerts(),
            "live": DashboardRepository.get_live_messages(10),
        }
