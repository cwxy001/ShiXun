# 瞭望数据源仓储类

import json
from app.models.db import get_connection


class WatchSourceRepository:
    """瞭望数据源 CRUD 操作"""

    @staticmethod
    def create(name: str, url_template: str, method: str = "GET",
               headers: str = "{}", proxy: str = "",
               enable_pagination: int = 0) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO watch_sources (name, url_template, method, headers, proxy, enable_pagination)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, url_template, method, headers, proxy, enable_pagination)
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_by_id(source_id: int):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM watch_sources WHERE id=?", (source_id,)).fetchone()

    @staticmethod
    def get_all():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watch_sources WHERE status=1 ORDER BY id"
            ).fetchall()

    @staticmethod
    def paginate(page: int = 1, page_size: int = 20, keyword: str = ""):
        offset = (page - 1) * page_size
        with get_connection() as conn:
            if keyword:
                where = "WHERE (name LIKE ? OR url_template LIKE ?)"
                params = (f"%{keyword}%", f"%{keyword}%")
                total = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM watch_sources {where}", params
                ).fetchone()["cnt"]
                rows = conn.execute(
                    f"SELECT * FROM watch_sources {where} ORDER BY id LIMIT ? OFFSET ?",
                    (*params, page_size, offset)
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) AS cnt FROM watch_sources").fetchone()["cnt"]
                rows = conn.execute(
                    "SELECT * FROM watch_sources ORDER BY id LIMIT ? OFFSET ?",
                    (page_size, offset)
                ).fetchall()
        return {"list": rows, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def update(source_id: int, **kwargs):
        allowed = ["name", "url_template", "method", "headers", "proxy", "enable_pagination"]
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
        values = list(updates.values()) + [source_id]
        with get_connection() as conn:
            conn.execute(
                f"UPDATE watch_sources SET {set_clause}, updated_at=datetime('now') WHERE id=?",
                values
            )
            conn.commit()

    @staticmethod
    def delete(source_id: int):
        with get_connection() as conn:
            conn.execute("DELETE FROM watch_sources WHERE id=?", (source_id,))
            conn.commit()
