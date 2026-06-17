# 瞭望采集结果仓储类

from app.models.db import get_connection


class WatchResultRepository:

    @staticmethod
    def save_batch(results: list) -> int:
        """批量保存采集结果"""
        count = 0
        with get_connection() as conn:
            for r in results:
                conn.execute(
                    """INSERT INTO watch_results
                       (source_id, source_name, keyword, title, url, snippet, raw_html, page_num)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (r.get("source_id", 0), r.get("source_name", ""),
                     r.get("keyword", ""), r.get("title", ""),
                     r.get("url", ""), r.get("snippet", ""),
                     r.get("raw_html", ""), r.get("page_num", 0))
                )
                count += 1
            conn.commit()
        return count

    @staticmethod
    def paginate(page: int = 1, page_size: int = 20, keyword: str = ""):
        offset = (page - 1) * page_size
        with get_connection() as conn:
            if keyword:
                where = "WHERE keyword LIKE ? OR title LIKE ?"
                params = (f"%{keyword}%", f"%{keyword}%")
                total = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM watch_results {where}", params
                ).fetchone()["cnt"]
                rows = conn.execute(
                    f"SELECT * FROM watch_results {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                    (*params, page_size, offset)
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) AS cnt FROM watch_results").fetchone()["cnt"]
                rows = conn.execute(
                    "SELECT * FROM watch_results ORDER BY id DESC LIMIT ? OFFSET ?",
                    (page_size, offset)
                ).fetchall()
        return {"list": rows, "total": total, "page": page, "page_size": page_size}
