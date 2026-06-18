# 任务8：瞭望采集模块 - 开发提示词

## 角色设定
你是一名精通 Python Tornado + BeautifulSoup + SSE + 前端特效的全栈开发工程师，正在开发 IOIQ 智能数据系统的瞭望采集模块。

## 任务目标
开发一个类似搜索引擎的独立风格采集界面，以炫酷、科技感、沉浸式体验为主，支持多源并发采集、实时进度展示和结果保存。

## 技术栈
- 后端：Python 3.11 + Tornado 6.4 + BeautifulSoup4 + requests
- 前端：独立风格（不与ZUI同步）+ CSS3动画 + JavaScript SSE
- 数据库：SQLite
- 项目路径：`d:\20260614XhSf23Class01\day3\DataFinderAgentOS`

## 功能需求

### 1. 数据库表设计
创建 `watch_results` 表：
```sql
CREATE TABLE IF NOT EXISTS watch_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,              -- 数据源ID
    source_name TEXT,               -- 数据源名称
    keyword TEXT NOT NULL,          -- 采集关键词
    title TEXT,                     -- 标题
    url TEXT,                       -- 链接
    snippet TEXT,                   -- 摘要
    raw_html TEXT,                  -- 原始HTML片段
    page_num INTEGER DEFAULT 1,     -- 页码
    deep_status INTEGER DEFAULT 0,  -- 深度采集状态 0=未采集 1=已采集
    collected_at TEXT               -- 采集时间
);
```

### 2. 页面风格要求
**独立科技感风格，不与ZUI同步**：
- 深色背景（#0a0e27 或类似深蓝黑色）
- 霓虹蓝/青色发光效果
- 动态网格背景或粒子效果
- 毛玻璃效果面板
- 平滑过渡动画

### 3. 页面布局结构

```
┌─────────────────────────────────────────────┐
│  动态科技背景（网格/粒子动画）                │
│                                             │
│          ┌─────────────────────┐            │
│          │   🔍 输入关键词      │            │
│          │   [开始采集] 按钮   │            │
│          └─────────────────────┘            │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  采集源动态开关面板（卡片式）        │   │
│  │  [百度新闻 ☑] [搜狗新闻 ☐] [...]   │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  参考配置区域                        │   │
│  │  采集数量: [10]  页数: [1]          │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 结果卡片1 │ │ 结果卡片2 │ │ 结果卡片3 │   │
│  │ ☑ 选中   │ │ ☐ 未选   │ │ ☑ 选中   │   │
│  └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 结果卡片4 │ │ 结果卡片5 │ │ 结果卡片6 │   │
│  └──────────┘ └──────────┘ └──────────┘   │
│                                             │
│  [全选] [取消全选]  [保存选中到数据库]      │
│                                             │
│  实时进度：██████░░░░ 60% (6/10)           │
│  日志：正在采集百度新闻第2页...             │
└─────────────────────────────────────────────┘
```

### 4. 核心功能实现

#### 4.1 主输入框
- 页面中央大输入框，带发光边框效果
- 支持回车键触发采集
- 输入框聚焦时有脉冲动画

#### 4.2 采集源动态开关面板
- 从 `watch_sources` 表读取启用的数据源
- 卡片式展示，每个卡片有开关按钮
- 卡片显示：数据源名称 + URL模板预览 + 开关状态
- 至少选择一个采集源才能开始采集

#### 4.3 参考配置区域
- **采集数量**：每页采集条数（默认10，范围5-50）
- **采集页数**：要采集的页数（默认1，范围1-5）
- 参数与URL中的 `{pn}` 联动：页数=1时 pn=0，页数=2时 pn=0,10，以此类推

#### 4.4 采集结果橱窗展示
- **1行3列** 卡片网格布局
- 每个卡片显示：
  - 标题（带链接，可点击跳转）
  - 摘要（最多3行，超出省略）
  - 来源标签
  - 复选框（左上角）
- 卡片hover效果：上浮 + 发光边框
- 支持多选和全选

#### 4.5 实时进度与日志（SSE流式）
- 顶部进度条，显示总体进度百分比
- 实时日志区域，显示当前采集状态
- SSE 推送格式：
```json
{"type": "progress", "current": 6, "total": 10, "percent": 60}
{"type": "log", "message": "正在采集百度新闻第2页..."}
{"type": "result", "data": {"title": "...", "url": "...", "snippet": "..."}}
{"type": "complete", "message": "采集完成"}
```

### 5. 智能采集算法

#### 5.1 三级递进内容提取策略
```python
def _extract_items(html, source_type='generic'):
    """
    第一级：结构化提取（针对主流搜索引擎）
    第二级：泛化提取（遍历所有有效链接）
    第三级：标题补充（从h标签补充）
    """
    items = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # 第一级：结构化提取
    selectors = {
        'baidu': 'div.result, div.c-container',
        'google': 'div.g, div.tF2Cxc',
        'bing': 'li.b_algo',
        'sogou': 'div.vrwrap, div.rb'
    }
    
    # 第二级：泛化提取（兜底）
    if not items:
        for a in soup.find_all('a', href=True):
            # 提取有效链接和标题
            ...
    
    # 第三级：标题补充
    ...
    
    return items
```

#### 5.2 智能过滤算法
- **噪声过滤**：过滤导航、广告、分页等（维护黑名单词库）
- **相关性评分**：标题匹配权重0.7 + 摘要匹配权重0.3
- **相似度去重**：基于 trigram Jaccard 相似度（阈值0.8）

### 6. 需要实现的文件

#### 控制器：`app/controllers/watch_collect.py`
实现以下 Handler：
- `WatchCollectPageHandler` — GET 渲染采集页面
- `WatchCollectSourcesHandler` — GET 返回可用采集源JSON
- `WatchCollectFetchHandler` — GET SSE 流式采集执行
  - 接收参数：keyword, source_ids, page_count, per_page
  - 对每个采集源逐页采集
  - 实时SSE推送进度、日志、结果
- `WatchCollectSaveHandler` — POST 保存选中结果到数据库
  - 接收参数：results[]（包含title, url, snippet, source_id, source_name, keyword）

#### 模板：`app/templates/admin/watch_collect.html`
**独立风格，不继承 base.html**
- 完整HTML文档，包含自己的CSS和JS
- 科技感深色主题
- 响应式布局

#### 模型：`app/models/watch_result.py`
实现 `WatchResultRepository` 类：
- `create_batch(results)` — 批量保存采集结果
- `get_by_keyword(keyword, page=1, per_page=20)` — 按关键词查询
- `delete(id)` — 删除单条
- `delete_batch(ids)` — 批量删除

### 7. 路由注册
```python
("/admin/watch-collect", WatchCollectPageHandler),
("/admin/watch-collect/sources", WatchCollectSourcesHandler),
("/admin/watch-collect/fetch", WatchCollectFetchHandler),
("/admin/watch-collect/save", WatchCollectSaveHandler),
```

### 8. 开发要求
1. SSE 响应头必须设置：`Content-Type: text/event-stream`
2. 采集请求需要设置合理的 User-Agent 和超时时间
3. 异常处理：单个源采集失败不影响其他源
4. 结果去重：相同URL的结果只保留一个
5. 前端卡片需要有加载骨架屏效果

## 验收标准
- [ ] 页面风格科技感、沉浸式，与ZUI不同
- [ ] 主输入框在中央，支持回车触发
- [ ] 采集源开关面板动态加载
- [ ] 参考配置与URL参数联动
- [ ] 结果以1行3列橱窗展示
- [ ] 支持多选、全选、保存到数据库
- [ ] SSE实时进度和日志
- [ ] 三级递进提取策略
- [ ] 智能过滤和去重
- [ ] 多源并发采集
