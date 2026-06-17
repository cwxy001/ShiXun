# 主入口程序：加载程序、路由注册、静态资源配置、数据库初始化、服务器启动

import os
import tornado.web
import tornado.ioloop
from tornado.httpserver import HTTPServer

# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 控制器导入
from app.controllers.admin_auth import AdminLoginHandler, AdminIndexHandler, AdminLogoutHandler
from app.controllers.admin_manage import (
    FuncListHandler, FuncAddHandler, FuncEditHandler, FuncDeleteHandler,
    RoleListHandler, RoleAddHandler, RoleEditHandler, RoleDeleteHandler,
    UserListHandler, UserAddHandler, UserEditHandler, UserDeleteHandler,
)
from app.controllers.model_engine import (
    ModelListHandler, ModelAddHandler, ModelEditHandler, ModelDeleteHandler,
    ModelSetDefaultHandler, ModelChatHandler, ModelChatSSEHandler,
)
from app.controllers.watch_source import (
    WatchSourceListHandler, WatchSourceAddHandler, WatchSourceEditHandler, WatchSourceDeleteHandler,
)
from app.controllers.watch_collect import (
    WatchCollectPageHandler, WatchCollectSourcesHandler,
    WatchCollectFetchHandler, WatchCollectSaveHandler,
)

# 数据库初始化 & 种子数据
from app.models.db import init_db, seed_admin, seed_roles_and_functions, seed_model_engines, seed_watch_sources


def create_app():
    """创建 Tornado Web 应用实例"""
    init_db()
    seed_admin()
    seed_roles_and_functions()
    seed_model_engines()
    seed_watch_sources()

    return tornado.web.Application(
        [
            # 前台路由（预留）
            ("/", IndexHandler),
            ("/index.html", IndexHandler),
            # 后台认证路由
            ("/admin/login", AdminLoginHandler),
            ("/admin/index", AdminIndexHandler),
            ("/admin/logout", AdminLogoutHandler),
            # 功能管理路由
            ("/admin/functions", FuncListHandler),
            ("/admin/function/add", FuncAddHandler),
            ("/admin/function/edit", FuncEditHandler),
            ("/admin/function/delete", FuncDeleteHandler),
            # 角色管理路由
            ("/admin/roles", RoleListHandler),
            ("/admin/role/add", RoleAddHandler),
            ("/admin/role/edit", RoleEditHandler),
            ("/admin/role/delete", RoleDeleteHandler),
            # 用户管理路由
            ("/admin/users", UserListHandler),
            ("/admin/user/add", UserAddHandler),
            ("/admin/user/edit", UserEditHandler),
            ("/admin/user/delete", UserDeleteHandler),
            # 模型引擎路由
            ("/admin/models", ModelListHandler),
            ("/admin/model/add", ModelAddHandler),
            ("/admin/model/edit", ModelEditHandler),
            ("/admin/model/delete", ModelDeleteHandler),
            ("/admin/model/set-default", ModelSetDefaultHandler),
            ("/admin/model/chat", ModelChatHandler),
            ("/admin/model/chat/sse", ModelChatSSEHandler),
            # 瞭望数据源路由
            ("/admin/watch-sources", WatchSourceListHandler),
            ("/admin/watch-source/add", WatchSourceAddHandler),
            ("/admin/watch-source/edit", WatchSourceEditHandler),
            ("/admin/watch-source/delete", WatchSourceDeleteHandler),
            # 瞭望采集路由
            ("/admin/watch-collect", WatchCollectPageHandler),
            ("/admin/watch-collect/sources", WatchCollectSourcesHandler),
            ("/admin/watch-collect/fetch", WatchCollectFetchHandler),
            ("/admin/watch-collect/save", WatchCollectSaveHandler),
        ],
        # 静态文件配置
        static_path=os.path.join(PROJECT_ROOT, "app", "static"),
        template_path=os.path.join(PROJECT_ROOT, "app", "templates"),
        # Cookie 安全密钥（用于 secure_cookie）
        cookie_secret="ioiq_system_2024_secure_key_change_in_production",
        # 开启调试模式
        debug=True,
    )


class IndexHandler(tornado.web.RequestHandler):
    """前台首页处理器（预留）"""

    def get(self):
        self.write("<h1>欢迎访问 IOIQ 智能瞭望与智能问数系统</h1>"
                   "<p><a href='/admin/login'>进入管理后台</a></p>")


if __name__ == "__main__":
    application = create_app()
    server = HTTPServer(application)
    server.listen(10086)
    print("Server Started: http://localhost:10086/", flush=True)
    print("Admin Login : http://localhost:10086/admin/login  (admin/123456)", flush=True)
    tornado.ioloop.IOLoop.current().start()
