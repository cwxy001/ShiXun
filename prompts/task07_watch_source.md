# 任务7：瞭望管理模块 - 开发提示词

## 角色设定
你是一名精通 Python Tornado + SQLite + Bootstrap 的全栈开发工程师，正在开发 IOIQ 智能数据系统的瞭望管理模块。

## 任务目标
实现瞭望数据源管理功能，支持动态可视化管理采集规则，包括新增/修改/删除/查询采集源配置。

## 技术栈
- 后端：Python 3.11 + Tornado 6.4
- 数据库：SQLite（db.py 已提供 get_connection() 上下文管理器）
- 前端：Bootstrap 5.3 + 原生 JavaScript
- 项目路径：`d:\20260614XhSf23Class01\day3\DataFinderAgentOS`

## 功能需求

### 1. 数据库表设计
创建 `watch_sources` 表：
```sql
CREATE TABLE IF NOT EXISTS watch_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- 数据源名称（如"百度新闻"）
    url_template TEXT NOT NULL,            -- 采集URL模板
    method TEXT DEFAULT 'GET',             -- 请求方法 GET/POST
    headers TEXT,                          -- Request Header JSON配置
    proxy TEXT,                            -- 代理地址
    status INTEGER DEFAULT 1,              -- 状态 1=启用 0=禁用
    enable_pagination INTEGER DEFAULT 0,   -- 是否支持分页 1=是 0=否
    page_step INTEGER DEFAULT 10,          -- 分页步进值（默认10）
    description TEXT,                      -- 描述说明
    created_at TEXT,                       -- 创建时间
    updated_at TEXT                        -- 更新时间
);
```

### 2. URL模板占位符系统
- `{关键词}` — 替换为实际搜索词（如"西华师范大学"）
- `{pn}` — 分页步进占位符（pn=0第一页，pn=10第二页，pn=20第三页，以此类推）

**示例配置**：
```
基础URL: https://www.baidu.com/s?rt=1&bst=1&cl=2&tn=news&rsv_dl=ns_pc&word={关键词}&pn={pn}
实际请求: https://www.baidu.com/s?rt=1&bst=1&cl=2&tn=news&rsv_dl=ns_pc&word=西华师范大学&pn=0
```

### 3. 需要实现的文件

#### 模型层：`app/models/watch_source.py`
实现 `WatchSourceRepository` 类，包含：
- `create(name, url_template, method, headers, proxy, enable_pagination, page_step, description)` — 新增
- `get_by_id(id)` — 根据ID查询
- `get_all()` — 查询全部
- `paginate(page=1, per_page=20, keyword=None)` — 分页查询（支持关键词搜索name）
- `update(id, **kwargs)` — 更新
- `delete(id)` — 删除
- `get_active_sources()` — 获取所有启用的数据源

#### 控制器：`app/controllers/watch_source.py`
实现以下 Handler：
- `WatchSourceListHandler` — GET 分页列表（支持?keyword=搜索&page=页码）
- `WatchSourceAddHandler` — POST 新增数据源
- `WatchSourceEditHandler` — POST 编辑数据源
- `WatchSourceDeleteHandler` — POST 删除数据源
- `WatchSourceToggleHandler` — POST 切换启用/禁用状态

#### 模板：`app/templates/admin/watch_source_list.html`
- 继承 `base.html`
- 顶部搜索栏（关键词搜索 + 新增按钮）
- 数据表格展示：ID/名称/URL模板/方法/分页/状态/操作
- 分页组件
- 操作列：编辑/删除/启用禁用

#### 模板：`app/templates/admin/watch_source_edit.html`
- 继承 `base.html`
- 表单字段：
  - 名称（text，必填）
  - URL模板（textarea，必填，带占位符说明）
  - 请求方法（select：GET/POST）
  - Headers（textarea，JSON格式，带格式校验提示）
  - 代理地址（text，可选）
  - 是否分页（switch开关）
  - 分页步进（number，默认10，启用分页时显示）
  - 描述（textarea，可选）
- 占位符提示区域：说明 `{关键词}` 和 `{pn}` 用法
- 保存/取消按钮

### 4. 路由注册
在 `app.py` 中注册路由：
```python
("/admin/watch-sources", WatchSourceListHandler),
("/admin/watch-source/add", WatchSourceAddHandler),
("/admin/watch-source/edit", WatchSourceEditHandler),
("/admin/watch-source/delete", WatchSourceDeleteHandler),
("/admin/watch-source/toggle", WatchSourceToggleHandler),
```

### 5. 数据验证规则
- name: 必填，2-50字符
- url_template: 必填，必须包含 `{关键词}` 占位符
- headers: 可选，必须是合法JSON格式
- method: 只能是 GET 或 POST

### 6. 开发要求
1. 所有数据库操作使用 `get_connection()` 上下文管理器
2. 返回 JSON 统一格式：`{"success": true/false, "message": "...", "data": {...}}`
3. 前端表单提交使用 AJAX，避免页面刷新
4. 删除操作需要二次确认
5. 时间字段使用 `datetime.now().strftime('%Y-%m-%d %H:%M:%S')`

## 验收标准
- [ ] 可以成功新增、编辑、删除、查询数据源
- [ ] URL模板支持 `{关键词}` 和 `{pn}` 占位符
- [ ] Headers 支持 JSON 格式配置
- [ ] 分页步进可配置（默认10）
- [ ] 列表支持关键词搜索和分页
- [ ] 启用/禁用状态可切换
- [ ] 表单有完善的验证和错误提示

## 参考代码风格
参考项目中已有的 `app/controllers/admin_manage.py` 和 `app/models/user.py` 的代码风格。
