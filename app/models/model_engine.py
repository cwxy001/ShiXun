# 模型引擎仓储类

from app.models.db import get_connection


class ModelEngineRepository:
    """模型引擎 CRUD 操作"""

    @staticmethod
    def create(name: str, provider: str, api_base: str, api_key: str,
               model_name: str, model_type: str = "text", temperature: float = 0.7,
               max_tokens: int = 2048, system_prompt: str = "",
               enable_stream: int = 1, enable_think: int = 0) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO model_engines (name, provider, api_base, api_key, model_name,
                   model_type, temperature, max_tokens, system_prompt, enable_stream, enable_think)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, provider, api_base, api_key, model_name,
                 model_type, temperature, max_tokens, system_prompt, enable_stream, enable_think)
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_by_id(model_id: int):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM model_engines WHERE id=?", (model_id,)).fetchone()

    @staticmethod
    def get_default():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM model_engines WHERE is_default=1 AND status=1 LIMIT 1"
            ).fetchone()

    @staticmethod
    def get_all():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM model_engines WHERE status=1 ORDER BY is_default DESC, id"
            ).fetchall()

    @staticmethod
    def paginate(page: int = 1, page_size: int = 6, keyword: str = ""):
        offset = (page - 1) * page_size
        with get_connection() as conn:
            if keyword:
                where = "WHERE (name LIKE ? OR model_name LIKE ? OR provider LIKE ?)"
                params = (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")
                total = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM model_engines {where}", params
                ).fetchone()["cnt"]
                rows = conn.execute(
                    f"SELECT * FROM model_engines {where} ORDER BY is_default DESC, id LIMIT ? OFFSET ?",
                    (*params, page_size, offset)
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) AS cnt FROM model_engines").fetchone()["cnt"]
                rows = conn.execute(
                    "SELECT * FROM model_engines ORDER BY is_default DESC, id LIMIT ? OFFSET ?",
                    (page_size, offset)
                ).fetchall()
        return {"list": rows, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def update(model_id: int, **kwargs):
        allowed = ["name", "provider", "api_base", "api_key", "model_name",
                   "model_type", "temperature", "max_tokens", "system_prompt",
                   "enable_stream", "enable_think"]
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = None  # 触发 DEFAULT
        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
        values = list(updates.values()) + [model_id]
        with get_connection() as conn:
            conn.execute(
                f"UPDATE model_engines SET {set_clause}, updated_at=datetime('now') WHERE id=?",
                values
            )
            conn.commit()

    @staticmethod
    def set_default(model_id: int):
        with get_connection() as conn:
            conn.execute("UPDATE model_engines SET is_default=0")
            conn.execute("UPDATE model_engines SET is_default=1 WHERE id=?", (model_id,))
            conn.commit()

    @staticmethod
    def delete(model_id: int):
        with get_connection() as conn:
            conn.execute("DELETE FROM model_engines WHERE id=?", (model_id,))
            conn.commit()

    @staticmethod
    def add_tokens(model_id: int, token_count: int):
        with get_connection() as conn:
            conn.execute(
                "UPDATE model_engines SET total_tokens = total_tokens + ? WHERE id=?",
                (token_count, model_id)
            )
            conn.commit()
