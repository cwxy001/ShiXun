# 系统设置 + 操作日志 + 备份 + 运行状态

import os
import json
import shutil
import datetime
import sqlite3

from app.models.db import get_connection, get_path

_defaults = {
    "site_name": "IOIQ System",
    "site_logo": "",
    "site_copyright": "IOIQ System",
    "default_lang": "zh-CN",
    "session_timeout": "120",
    "upload_max_size": "10",
    "captcha_enabled": "1",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_from": "",
    "mail_notify": "0",
    "sms_notify": "0",
    "webhook_url": "",
    "maintenance_mode": "0",
    "version": "2.1.0",
}


class SystemSettingsRepository:

    @staticmethod
    def get_all():
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM system_settings ORDER BY category, id"
            ).fetchall()
        result = dict(_defaults)
        for r in rows:
            if r["key"] is not None:
                result[r["key"]] = r["value"] or _defaults.get(r["key"], "")
        return result

    @staticmethod
    def get(key: str, default: str = ""):
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key=?", (key,)
            ).fetchone()
        return (row["value"] if row["value"] is not None else "") if row else _defaults.get(key, default)

    @staticmethod
    def save_changes(settings: dict):
        with get_connection() as conn:
            for k, v in settings.items():
                if k.startswith("_"):
                    continue
                sv = str(v)
                conn.execute(
                    """INSERT INTO system_settings (key, value, updated_at)
                       VALUES (?, ?, datetime('now'))
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')""",
                    (k, sv)
                )
            conn.commit()

    @staticmethod
    def backup_database():
        db_path = get_path()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"db_backup_{stamp}.db")
        shutil.copy2(db_path, backup_path)
        return backup_path

    @staticmethod
    def list_backups():
        db_path = get_path()
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        if not os.path.isdir(backup_dir):
            return []
        files = []
        for f in os.listdir(backup_dir):
            fp = os.path.join(backup_dir, f)
            if os.path.isfile(fp):
                st = os.stat(fp)
                files.append({
                    "name": f,
                    "size": st.st_size,
                    "mtime": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        files.sort(key=lambda x: x["mtime"], reverse=True)
        return files

    @staticmethod
    def restore_backup(filename: str):
        db_path = get_path()
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        src = os.path.join(backup_dir, filename)
        if not os.path.isfile(src):
            return False
        shutil.copy2(src, db_path)
        return True

    @staticmethod
    def get_system_status():
        try:
            with get_connection() as conn:
                conn.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
        db_path = get_path()
        db_size = os.path.getsize(db_path) if os.path.isfile(db_path) else 0
        return {
            "db_connected": db_ok,
            "db_path": db_path,
            "db_size": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "python_version": os.sys.version,
            "start_time": getattr(os, "start_time", "N/A"),
        }


class OperationLogRepository:

    @staticmethod
    def log(operator: str, action: str, detail: str = "", ip: str = ""):
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO operation_logs (operator, action, detail, ip)
                   VALUES (?,?,?,?)""",
                (operator, action, detail, ip)
            )
            conn.commit()

    @staticmethod
    def paginate(page: int = 1, page_size: int = 20,
                 operator: str = "", action: str = "",
                 date_from: str = "", date_to: str = ""):
        offset = (page - 1) * page_size
        conditions = []
        params = []
        if operator:
            conditions.append("operator LIKE ?")
            params.append(f"%{operator}%")
        if action:
            conditions.append("action = ?")
            params.append(action)
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to + " 23:59:59")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM operation_logs {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM operation_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, page_size, offset)
            ).fetchall()
        return {"list": rows, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get_actions():
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT action FROM operation_logs ORDER BY action"
            ).fetchall()
        return [r["action"] for r in rows]

    @staticmethod
    def clear():
        with get_connection() as conn:
            conn.execute("DELETE FROM operation_logs")
            conn.commit()
