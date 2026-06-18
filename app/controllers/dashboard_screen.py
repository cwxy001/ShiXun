# 数智大屏控制器 — 主页 + 实时数据 API

import json
import tornado.web

from app.models.dashboard_screen import DashboardRepository


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


class DashboardScreenHandler(tornado.web.RequestHandler):
    """数智大屏主页"""

    def get(self):
        if not _require_login(self):
            return
        template = self.get_argument("template", "1").strip()
        self.render(
            "admin/dashboard_screen.html",
            username=_get_current_user(self),
            current_page="dashboard_screen",
            template=template,
        )


class DashboardDataHandler(tornado.web.RequestHandler):
    """大屏数据 API（JSON）"""

    def get(self):
        if not _require_login(self):
            return
        data = DashboardRepository.get_all_data()
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.write(json.dumps(data, ensure_ascii=False))
