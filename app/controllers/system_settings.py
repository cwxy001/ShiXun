# 系统设置控制器

import os
import json
import tornado.web

from app.models.system_settings import (
    SystemSettingsRepository,
    OperationLogRepository,
)


def _require_login(handler):
    if not handler.get_secure_cookie("admin_user"):
        handler.redirect("/admin/login")
        return False
    return True


def _get_current_user(handler):
    cookie = handler.get_secure_cookie("admin_user")
    return cookie.decode() if cookie else ""


def _int_arg(handler, key, default=0):
    try:
        return int(handler.get_argument(key, str(default)))
    except (ValueError, TypeError):
        return default


# ─── 系统设置主页面 ───

class SystemSettingsHandler(tornado.web.RequestHandler):
    def get(self):
        if not _require_login(self):
            return
        settings = SystemSettingsRepository.get_all()
        self.render(
            "admin/system_settings.html",
            username=_get_current_user(self),
            current_page="system",
            settings=settings,
            msg=self.get_query_argument("msg", ""),
        )


class SystemSettingsSaveHandler(tornado.web.RequestHandler):
    def post(self):
        if not _require_login(self):
            return
        data = {}
        for key in self.request.body_arguments:
            val = self.get_body_argument(key, "")
            data[key] = val
        SystemSettingsRepository.save_changes(data)
        op = _get_current_user(self)
        OperationLogRepository.log(
            operator=op,
            action="update_settings",
            detail="更新系统设置",
            ip=self.request.remote_ip,
        )
        self.redirect("/admin/system?msg=saved")


# ─── 备份 ───

class SystemBackupHandler(tornado.web.RequestHandler):
    def post(self):
        if not _require_login(self):
            return
        try:
            path = SystemSettingsRepository.backup_database()
            OperationLogRepository.log(
                operator=_get_current_user(self),
                action="backup",
                detail=f"数据库备份: {path}",
                ip=self.request.remote_ip,
            )
            self.redirect("/admin/system?msg=backup_ok")
        except Exception as e:
            self.redirect(f"/admin/system?msg=backup_fail:{str(e)}")


class SystemRestoreHandler(tornado.web.RequestHandler):
    def post(self):
        if not _require_login(self):
            return
        filename = self.get_body_argument("file", "").strip()
        if not filename:
            self.redirect("/admin/system?msg=restore_no_file")
            return
        ok = SystemSettingsRepository.restore_backup(filename)
        if ok:
            OperationLogRepository.log(
                operator=_get_current_user(self),
                action="restore",
                detail=f"从备份恢复: {filename}",
                ip=self.request.remote_ip,
            )
            self.redirect("/admin/system?msg=restore_ok")
        else:
            self.redirect(f"/admin/system?msg=restore_fail:{filename}")


# ─── 运行状态 ───

class SystemStatusHandler(tornado.web.RequestHandler):
    def get(self):
        if not _require_login(self):
            return
        status = SystemSettingsRepository.get_system_status()
        backups = SystemSettingsRepository.list_backups()
        settings = SystemSettingsRepository.get_all()
        self.render(
            "admin/system_status.html",
            username=_get_current_user(self),
            current_page="system",
            status=status,
            backups=backups,
            settings=settings,
        )


class SystemStatusJsonHandler(tornado.web.RequestHandler):
    def get(self):
        if not _require_login(self):
            return
        status = SystemSettingsRepository.get_system_status()
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(json.dumps(status, ensure_ascii=False))


# ─── 操作日志 ───

class OperationLogHandler(tornado.web.RequestHandler):
    def get(self):
        if not _require_login(self):
            return
        page = max(_int_arg(self, "page", 1), 1)
        operator = self.get_argument("operator", "").strip()
        action = self.get_argument("action", "").strip()
        date_from = self.get_argument("date_from", "").strip()
        date_to = self.get_argument("date_to", "").strip()
        result = OperationLogRepository.paginate(
            page=page, page_size=20,
            operator=operator, action=action,
            date_from=date_from, date_to=date_to,
        )
        total_pages = (result["total"] + 19) // 20
        actions = OperationLogRepository.get_actions()
        self.render(
            "admin/operation_logs.html",
            username=_get_current_user(self),
            current_page="system",
            **result,
            total_pages=total_pages,
            operator=operator, action=action,
            date_from=date_from, date_to=date_to,
            actions=actions,
        )


class OperationLogClearHandler(tornado.web.RequestHandler):
    def post(self):
        if not _require_login(self):
            return
        OperationLogRepository.clear()
        OperationLogRepository.log(
            operator=_get_current_user(self),
            action="clear_logs",
            detail="清空操作日志",
            ip=self.request.remote_ip,
        )
        self.redirect("/admin/operation-logs")


class OperationLogExportHandler(tornado.web.RequestHandler):
    def get(self):
        if not _require_login(self):
            return
        result = OperationLogRepository.paginate(page=1, page_size=50000)
        data = []
        for r in result["list"]:
            data.append({
                "id": r["id"],
                "operator": r["operator"],
                "action": r["action"],
                "detail": r["detail"],
                "ip": r["ip"],
                "created_at": r["created_at"],
            })
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Content-Disposition", "attachment; filename=operation_logs.json")
        self.write(json.dumps(data, ensure_ascii=False, indent=2))
