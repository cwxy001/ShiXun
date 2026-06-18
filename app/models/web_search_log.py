# 网络搜索日志仓储

from app.models.db import get_connection


class WebSearchLogRepository:
    """搜索日志 CRUD + 统计"""

    @staticmethod
    def log(query: str, result_count: int, source: str, source_urls: str = "",
            user: str = "", duration_ms: int = 0):
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO web_search_logs
                   (query, result_count, source, source_urls, user, duration_ms)
                   VALUES (?,?,?,?,?,?)""",
                (query, result_count, source, source_urls, user, duration_ms)
            )
            conn.commit()

    @staticmethod
    def paginate(page: int = 1, page_size: int = 20,
                 keyword: str = "", user: str = "",
                 date_from: str = "", date_to: str = ""):
        offset = (page - 1) * page_size
        conditions = []
        params = []
        if keyword:
            conditions.append("query LIKE ?")
            params.append(f"%{keyword}%")
        if user:
            conditions.append("user LIKE ?")
            params.append(f"%{user}%")
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to + " 23:59:59")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM web_search_logs {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM web_search_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, page_size, offset)
            ).fetchall()
        return {"list": rows, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_stats():
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM web_search_logs").fetchone()["cnt"]
            total_results = conn.execute(
                "SELECT COALESCE(SUM(result_count), 0) AS c FROM web_search_logs"
            ).fetchone()["c"]
            live_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM web_search_logs WHERE source='live'"
            ).fetchone()["cnt"]
            avg_ms = conn.execute(
                "SELECT COALESCE(AVG(duration_ms), 0) AS c FROM web_search_logs"
            ).fetchone()["c"]
            today = conn.execute(
                "SELECT COUNT(*) AS cnt FROM web_search_logs WHERE date(created_at)=date('now')"
            ).fetchone()["cnt"]
        return {
            "total": total,
            "total_results": total_results,
            "live_count": live_count,
            "avg_duration_ms": round(avg_ms, 1),
            "today": today,
        }

    @staticmethod
    def clear():
        with get_connection() as conn:
            conn.execute("DELETE FROM web_search_logs")
            conn.commit()
