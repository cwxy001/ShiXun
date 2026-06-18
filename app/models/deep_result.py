# 深度采集结果仓储类

from app.models.db import get_connection


class DeepResultRepository:

    @staticmethod
    def create(watch_result_id: int, source_url: str = "", model_engine_id: int = 0,
               model_name: str = "", title: str = "", full_content: str = "",
               content_summary: str = "", status: str = "pending",
               error_message: str = "", log_text: str = "",
               tokens_used: int = 0, duration_ms: int = 0) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO deep_results
                   (watch_result_id, source_url, model_engine_id, model_name, title,
                    full_content, content_summary, status, error_message, log_text,
                    tokens_used, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (watch_result_id, source_url, model_engine_id, model_name, title,
                 full_content, content_summary, status, error_message, log_text,
                 tokens_used, duration_ms)
            )
            # 同时更新 watch_results 的 deep_status
            is_done = status in ("success", "fail")
            conn.execute(
                "UPDATE watch_results SET deep_status=? WHERE id=?",
                (1 if is_done else 0, watch_result_id)
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def update(result_id: int, **kwargs):
        allowed = ["title", "full_content", "content_summary", "status",
                   "error_message", "log_text", "tokens_used", "duration_ms",
                   "model_engine_id", "model_name"]
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [result_id]
        with get_connection() as conn:
            conn.execute(f"UPDATE deep_results SET {set_clause} WHERE id=?", values)
            conn.commit()

    @staticmethod
    def get_by_id(result_id: int):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM deep_results WHERE id=?", (result_id,)
            ).fetchone()

    @staticmethod
    def get_by_watch_result_id(watch_result_id: int):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM deep_results WHERE watch_result_id=? ORDER BY id DESC LIMIT 1",
                (watch_result_id,)
            ).fetchone()

    @staticmethod
    def delete_by_watch_result_id(watch_result_id: int):
        with get_connection() as conn:
            conn.execute("DELETE FROM deep_results WHERE watch_result_id=?", (watch_result_id,))
            conn.execute("UPDATE watch_results SET deep_status=0 WHERE id=?", (watch_result_id,))
            conn.commit()

    @staticmethod
    def get_batch_deep_status(watch_result_ids: list) -> dict:
        """批量查询深度采集状态，返回 {watch_result_id: deep_row}"""
        if not watch_result_ids:
            return {}
        placeholders = ",".join("?" for _ in watch_result_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM deep_results WHERE watch_result_id IN ({placeholders})",
                watch_result_ids
            ).fetchall()
        return {row["watch_result_id"]: row for row in rows}
