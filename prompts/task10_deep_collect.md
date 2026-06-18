# 任务10：深度采集模块 - 开发提示词

## 角色设定
你是一名精通 Python Tornado + OpenAI API + Crawl4AI + SSE 的全栈开发工程师，正在开发 IOIQ 智能数据系统的深度采集模块。

## 任务目标
通过模型引擎中的默认大模型服务，对数据仓库中已采集的数据进行深度解析，提取详细内容并存储，支持单条和批量采集模式，实时进度和日志记录。

## 技术栈
- 后端：Python 3.11 + Tornado 6.4 + requests + BeautifulSoup4
- AI：OpenAI 兼容 API（从 model_engines 表读取配置）
- 前端：Bootstrap 5.3 + SSE + JavaScript
- 数据库：SQLite
- 项目路径：`d:\20260614XhSf23Class01\day3\DataFinderAgentOS`

## 功能需求

### 1. 数据库表设计
创建 `deep_results` 表：
```sql
CREATE TABLE IF NOT EXISTS deep_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_result_id INTEGER NOT NULL,    -- 关联 watch_results 表
    source_url TEXT,                      -- 源URL
    model_engine_id INTEGER,             -- 使用的模型引擎ID
    model_name TEXT,                     -- 模型名称
    title TEXT,                          -- 标题
    full_content TEXT,                   -- 提取的完整正文（截断至50000字符）
    content_summary TEXT,                -- AI生成的摘要
    keywords TEXT,                       -- AI提取的关键词（JSON数组）
    category TEXT,                       -- AI分类标签
    sentiment TEXT,                      -- 情感分析结果
    status TEXT DEFAULT 'pending',       -- pending/success/fail
    error_message TEXT,                  -- 错误信息
    log_text TEXT,                       -- 执行日志
    tokens_used INTEGER DEFAULT 0,       -- Token消耗
    duration_ms INTEGER DEFAULT 0,       -- 耗时（毫秒）
    created_at TEXT                      -- 创建时间
);
```

### 2. 核心功能

#### 2.1 双模式采集
- **单条采集**：从数据仓库列表点击"深度采集"按钮，对单条记录执行
- **批量采集**：勾选多条记录，点击"批量深度采集"按钮

#### 2.2 采集流程
```
接收 watch_result_id 列表
  → 获取默认模型引擎配置（model_engines 表中 is_default=1）
  → 对每个记录：
    1. 获取 watch_result 的 URL 和 snippet
    2. 有有效 URL → requests 抓取页面 → BeautifulSoup 提取正文
       → 移除 script/style/nav/footer 等噪声标签
       → 优先 article/main/div 标签提取
       → 截断至 50000 字符
    3. 无有效 URL → 使用 snippet 做基础分析
    4. 调用 AI 模型分析内容
       → Prompt 要求返回 JSON: {summary, keywords, category, sentiment}
       → 解析 JSON 失败则回退到正则提取
    5. 无 AI 配置 → 规则摘要（前 200 字符）
    6. 保存结果到 deep_results 表
    7. 更新 watch_results.deep_status = 1
  → SSE 实时推送进度
```

#### 2.3 AI Prompt 模板
```python
DEEP_ANALYZE_PROMPT = """
请对以下内容进行深度分析，返回 JSON 格式：

内容：
{content}

要求返回以下字段：
{
    "summary": "内容摘要，200字以内",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "category": "内容分类",
    "sentiment": "positive/negative/neutral"
}

注意：
1. 必须返回合法 JSON，不要包含其他文字
2. summary 要简洁准确
3. keywords 最多5个
4. sentiment 只能是 positive/negative/neutral 之一
"""
```

#### 2.4 容错机制
- **JSON 解析失败**：尝试正则提取 `{}` 包裹的内容
- **正则提取失败**：回退到规则摘要（前 200 字符）
- **URL 请求失败**：使用已有 snippet 分析
- **AI 调用失败**：记录错误，状态标记为 fail

### 3. 实时进度与日志（SSE）

SSE 推送格式：
```json
{"type": "start", "total": 5, "message": "开始深度采集，共5条"}
{"type": "progress", "current": 1, "total": 5, "percent": 20, "message": "正在采集：标题xxx..."}
{"type": "log", "level": "info", "message": "正在抓取 URL: https://..."}
{"type": "log", "level": "success", "message": "AI分析完成，耗时 2.3s"}
{"type": "complete", "success_count": 4, "fail_count": 1, "total_time": 15.2}
```

### 4. 统计分析
采集完成后展示：
- 总数量
- 成功数量
- 失败数量
- 总耗时
- 平均耗时
- Token 总消耗

### 5. 状态联动
- 深度采集完成后，更新 `watch_results.deep_status = 1`
- 数据仓库列表中显示"已深度采集"标签
- 已深度采集的数据可查看详情

### 6. 需要实现的文件

#### 控制器：`app/controllers/deep_collect.py`
实现以下 Handler：
- `DeepCollectListHandler` — GET 深度采集结果列表页
  - 分页展示 deep_results 记录
  - 统计卡片（总数/成功/失败/Token消耗）
- `DeepCollectSSEHandler` — GET SSE 流式深度采集
  - 接收参数：watch_result_ids（逗号分隔）
  - 逐条执行深度采集
  - 实时 SSE 推送
- `DeepCollectDetailHandler` — GET 单条详情页
  - 参数：id（deep_result_id）
  - 展示完整采集内容、AI分析结果、日志

#### 模型：`app/models/deep_result.py`
实现 `DeepResultRepository` 类：
- `create(watch_result_id, source_url, model_engine_id, ...)` — 创建记录
- `update(id, **kwargs)` — 更新记录
- `get_by_id(id)` — 查询详情
- `paginate(page=1, per_page=20, status=None)` — 分页查询
- `get_stats()` — 获取统计数据

#### 模板：`app/templates/admin/deep_collect_list.html`
- 继承 `base.html`
- **统计卡片区域**（顶部）：
  - 总采集数
  - 成功数（绿色）
  - 失败数（红色）
  - Token 总消耗
- **筛选栏**：按状态筛选
- **数据表格**：
  - 标题/源URL/模型/状态/耗时/Token/时间
  - 状态标签：pending（灰色）/ success（绿色）/ fail（红色）
  - 操作：查看详情
- **分页组件**

#### 模板：`app/templates/admin/deep_detail.html`
- 继承 `base.html`
- **源信息区域**：
  - 原始标题、URL、关键词
- **AI分析结果**：
  - 摘要（高亮显示）
  - 关键词（标签展示）
  - 分类
  - 情感（带颜色标识）
- **完整正文**：
  - 可折叠的长文本区域
- **采集日志**：
  - 时间线形式展示执行日志
- **错误信息**（如果有）

### 7. 路由注册
```python
("/admin/deep-collect", DeepCollectListHandler),
("/admin/deep-collect/sse", DeepCollectSSEHandler),
(r"/admin/deep-collect/detail/(\d+)", DeepCollectDetailHandler),
```

### 8. 模型引擎集成
从 `model_engines` 表读取默认模型配置：
```python
def get_default_model():
    """获取默认模型引擎配置"""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM model_engines WHERE is_default = 1 AND status = 1 LIMIT 1"
        )
        return cursor.fetchone()
```

使用 OpenAI 兼容 API：
```python
import openai

client = openai.OpenAI(
    base_url=model_config['api_url'],
    api_key=model_config['api_key']
)

response = client.chat.completions.create(
    model=model_config['model_name'],
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7
)
```

## 验收标准
- [ ] 支持单条和批量深度采集
- [ ] 使用默认模型引擎进行AI分析
- [ ] 提取正文并截断至50000字符
- [ ] AI返回结构化JSON（摘要/关键词/分类/情感）
- [ ] 三级容错机制（JSON→正则→规则）
- [ ] SSE实时进度和日志推送
- [ ] 采集完成统计（成功/失败/耗时/Token）
- [ ] 更新数据仓库深度状态
- [ ] 详情页展示完整AI分析结果
- [ ] 采集日志完整记录
