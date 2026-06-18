# 任务12：接口管理模块 - 开发提示词

## 角色设定
你是一名精通 Python Tornado + SQLite + Bootstrap 的全栈开发工程师，正在开发 IOIQ 智能数据系统的接口管理模块。

## 任务目标
实现对系统内外API接口的统一管理和监控，支持完整的生命周期管理：CRUD、在线调试、调用统计、文档生成、调用日志。

## 技术栈
- 后端：Python 3.11 + Tornado 6.4 + requests
- 数据库：SQLite
- 前端：Bootstrap 5.3 + 原生 JavaScript
- 项目路径：`d:\20260614XhSf23Class01\day3\DataFinderAgentOS`

## 功能需求

### 1. 数据库表设计

#### api_interfaces 表（接口配置）
```sql
CREATE TABLE IF NOT EXISTS api_interfaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                -- 接口名称
    path TEXT NOT NULL,                -- 请求路径（如 /api/v1/users）
    method TEXT NOT NULL,              -- 请求方法：GET/POST/PUT/DELETE/PATCH
    description TEXT,                  -- 接口描述
    params TEXT,                       -- 参数定义（JSON格式）
    headers TEXT,                      -- 请求头定义（JSON格式）
    auth_type TEXT DEFAULT 'none',     -- 认证方式：none/api_key/bearer/basic/oauth2
    auth_config TEXT,                  -- 认证配置（JSON格式）
    status INTEGER DEFAULT 1,          -- 状态 1=启用 0=禁用（软删除）
    created_at TEXT,
    updated_at TEXT
);
```

#### api_call_logs 表（调用日志）
```sql
CREATE TABLE IF NOT EXISTS api_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interface_id INTEGER,              -- 关联接口ID
    interface_name TEXT,               -- 接口名称（冗余存储）
    method TEXT,                       -- 实际请求方法
    path TEXT,                         -- 实际请求路径
    request_params TEXT,               -- 请求参数（JSON）
    request_headers TEXT,              -- 请求头（JSON）
    response_status INTEGER,           -- HTTP状态码
    response_body TEXT,                -- 响应内容（截断）
    response_time_ms INTEGER,          -- 响应时间（毫秒）
    success INTEGER DEFAULT 1,         -- 是否成功 1=是 0=否
    error_message TEXT,                -- 错误信息
    called_at TEXT                     -- 调用时间
);
```

### 2. 核心功能

#### 2.1 接口CRUD管理
- **新增接口**：配置名称、路径、方法、参数、请求头、认证方式
- **编辑接口**：修改所有配置字段
- **删除接口**：软删除（status=0），保留历史数据
- **查询接口**：分页列表，支持关键词搜索

#### 2.2 认证方式支持
| 认证方式 | 说明 | 配置示例 |
|---------|------|---------|
| none | 无认证 | - |
| api_key | API密钥 | `{ "key": "X-API-Key", "value": "secret123" }` |
| bearer | Bearer Token | `{ "token": "eyJhbG..." }` |
| basic | Basic认证 | `{ "username": "admin", "password": "123" }` |
| oauth2 | OAuth2 | `{ "token_url": "...", "client_id": "..." }` |

#### 2.3 在线调试功能
- 左右分栏布局：左侧请求配置，右侧响应结果
- 请求配置：
  - 基础信息（从接口配置加载，可修改）
  - 参数表格（key-value，支持动态增删）
  - 请求头表格（key-value，支持动态增删）
  - 请求体编辑器（JSON格式，POST/PUT时显示）
- 发送请求后：
  - 显示响应状态码（颜色标识：2xx绿色/4xx黄色/5xx红色）
  - 显示响应时间
  - 显示响应头（格式化JSON）
  - 显示响应体（语法高亮JSON）
- 使用 SSE 流式返回调试过程（可选）

#### 2.4 调用统计分析
- **总览统计**：
  - 总调用次数
  - 成功次数 / 失败次数
  - 成功率（百分比）
  - 平均响应时间
  - 最快/最慢响应时间
- **趋势图表**（近30天）：
  - 调用次数趋势
  - 平均响应时间趋势
  - 成功率趋势
- **接口排名**：
  - 调用次数最多的Top10接口
  - 平均响应时间最长的Top10接口

#### 2.5 接口文档生成
- 自动生成接口文档页面
- 按接口分组展示
- 每个接口显示：
  - 名称和描述
  - 请求方法 + 路径（带颜色标识方法）
  - 参数表格（名称/类型/必填/描述）
  - 请求头表格
  - 认证方式说明
  - 响应示例（如果有）
- **导出功能**：一键导出 Markdown 格式文档

#### 2.6 调用日志记录
- 每次调试自动记录到 `api_call_logs` 表
- 日志列表页：
  - 筛选：按接口、状态（成功/失败）、时间范围
  - 表格：接口名/方法/路径/状态码/响应时间/时间
  - 详情：查看完整请求和响应
- 支持清空日志

### 3. 需要实现的文件

#### 模型：`app/models/api_interface.py`
实现两个Repository类：

**ApiInterfaceRepository**：
- `create(name, path, method, description, params, headers, auth_type, auth_config)`
- `get_by_id(id)`
- `paginate(page=1, per_page=20, keyword=None)`
- `update(id, **kwargs)`
- `delete(id)` — 软删除，设置 status=0
- `get_stats()` — 获取调用统计

**ApiCallLogRepository**：
- `create(interface_id, interface_name, method, path, request_params, request_headers, response_status, response_body, response_time_ms, success, error_message)`
- `paginate(page=1, per_page=20, interface_id=None, success=None)`
- `get_stats_by_interface(interface_id)` — 单接口统计
- `clear_logs()` — 清空日志

#### 控制器：`app/controllers/api_manage.py`
实现以下 Handler：
- `ApiListHandler` — GET 接口列表页
- `ApiAddHandler` — POST 新增接口
- `ApiEditHandler` — POST 编辑接口
- `ApiDeleteHandler` — POST 删除接口（软删除）
- `ApiDebugHandler` — POST 在线调试执行
  - 接收：method, path, params, headers, body
  - 执行实际HTTP请求
  - 记录调用日志
  - 返回响应结果
- `ApiDebugPageHandler` — GET 调试页面
- `ApiStatsHandler` — GET 统计页面
- `ApiLogsHandler` — GET 调用日志列表
- `ApiClearLogsHandler` — POST 清空日志
- `ApiDocHandler` — GET 接口文档页面
- `ApiDocExportHandler` — GET 导出Markdown文档

#### 模板：`app/templates/admin/api_list.html`
- 继承 `base.html`
- 顶部统计卡片（总接口数/今日调用/成功率）
- 搜索栏 + 新增按钮
- 数据表格：名称/路径/方法/认证/状态/操作
- 方法标签带颜色：GET(蓝)/POST(绿)/PUT(黄)/DELETE(红)/PATCH(紫)
- 操作：调试/编辑/删除

#### 模板：`app/templates/admin/api_edit.html`
- 继承 `base.html`
- 表单字段：
  - 接口名称（text）
  - 请求路径（text，带/前缀校验）
  - 请求方法（select：GET/POST/PUT/DELETE/PATCH）
  - 接口描述（textarea）
  - 参数定义（动态表格，key-value-type-required-description）
  - 请求头定义（动态表格，key-value）
  - 认证方式（select）
  - 认证配置（根据认证方式动态显示不同表单）

#### 模板：`app/templates/admin/api_debug.html`
- 继承 `base.html`
- **左右分栏布局**：
  - 左侧（40%）：请求配置
    - 基础信息（方法/路径，从接口加载但可修改）
    - 参数表格（动态增删行）
    - 请求头表格（动态增删行）
    - 请求体编辑器（textarea，JSON格式）
    - [发送请求] 按钮
  - 右侧（60%）：响应结果
    - 状态码 + 响应时间
    - 响应头（格式化展示）
    - 响应体（语法高亮，可折叠）

#### 模板：`app/templates/admin/api_stats.html`
- 继承 `base.html`
- 统计卡片区域（总调用/成功/失败/平均响应时间）
- 趋势图表（使用 ECharts 或 Chart.js）
- 接口排名表格

#### 模板：`app/templates/admin/api_logs.html`
- 继承 `base.html`
- 筛选栏：接口选择/状态/时间范围
- 日志表格：接口/方法/路径/状态码/响应时间/时间
- 操作：查看详情
- 清空日志按钮（二次确认）

#### 模板：`app/templates/admin/api_doc.html`
- 继承 `base.html`
- 按接口分组展示文档卡片
- 每个卡片：方法标签/路径/描述/参数表/请求头/认证/响应示例
- [导出Markdown] 按钮

### 4. 路由注册
```python
("/admin/api-interfaces", ApiListHandler),
("/admin/api-interface/add", ApiAddHandler),
("/admin/api-interface/edit", ApiEditHandler),
("/admin/api-interface/delete", ApiDeleteHandler),
("/admin/api-interface/debug", ApiDebugPageHandler),
("/admin/api-interface/debug/sse", ApiDebugHandler),  # 如用SSE
("/admin/api-stats", ApiStatsHandler),
("/admin/api-logs", ApiLogsHandler),
("/admin/api-clear-logs", ApiClearLogsHandler),
("/admin/api-doc", ApiDocHandler),
("/admin/api-doc/export", ApiDocExportHandler),
```

### 5. 在线调试实现
```python
def execute_api_request(method, path, params, headers, body, auth_type, auth_config):
    """执行API请求"""
    import requests
    
    # 构建认证头
    auth_headers = build_auth_headers(auth_type, auth_config)
    headers.update(auth_headers)
    
    # 执行请求
    start_time = time.time()
    try:
        response = requests.request(
            method=method,
            url=path,
            params=params,
            headers=headers,
            json=body if body else None,
            timeout=30
        )
        success = True
        error_msg = None
    except Exception as e:
        success = False
        error_msg = str(e)
        response = None
    
    duration = int((time.time() - start_time) * 1000)
    
    return {
        'status_code': response.status_code if response else None,
        'headers': dict(response.headers) if response else {},
        'body': response.text if response else '',
        'duration_ms': duration,
        'success': success,
        'error': error_msg
    }
```

### 6. Markdown文档导出格式
```markdown
# API接口文档

## 用户管理

### 获取用户列表
- **方法**: GET
- **路径**: `/api/v1/users`
- **认证**: Bearer Token

#### 参数
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| page | int | 否 | 页码，默认1 |
| size | int | 否 | 每页数量，默认20 |

#### 请求头
| 名称 | 值 |
|------|-----|
| Authorization | Bearer {token} |

#### 响应示例
```json
{
  "code": 200,
  "data": [...]
}
```
```

## 验收标准
- [ ] 接口的增删改查（软删除）
- [ ] 5种认证方式支持
- [ ] 在线调试功能（左右分栏）
- [ ] 调试结果语法高亮
- [ ] 调用统计（总览/趋势/排名）
- [ ] 接口文档自动生成
- [ ] Markdown文档导出
- [ ] 调用日志记录和查询
- [ ] 响应时间统计
- [ ] 参数和请求头动态表格
