# 任务9：数据仓库模块 - 开发提示词

## 角色设定
你是一名精通 Python Tornado + SQLite + Bootstrap 的全栈开发工程师，正在开发 IOIQ 智能数据系统的数据仓库模块。

## 任务目标
以列表形式展示通过瞭望采集到的数据，支持分页、筛选、删除，并预留AI深度采集入口。

## 技术栈
- 后端：Python 3.11 + Tornado 6.4
- 数据库：SQLite（复用 watch_results 表）
- 前端：Bootstrap 5.3 + 原生 JavaScript
- 项目路径：`d:\20260614XhSf23Class01\day3\DataFinderAgentOS`

## 功能需求

### 1. 数据展示
- 每页显示 **20条** 记录
- 列表字段：
  | 字段 | 说明 |
  |------|------|
  | ID | 记录ID |
  | 标题 | 采集标题（点击可查看详情） |
  | 摘要 | 内容摘要（最多2行） |
  | 关键词 | 采集时使用的关键词 |
  | 数据来源 | 来源名称 |
  | 深度状态 | 已深度采集/未深度采集（带状态标签） |
  | 采集时间 | 格式化显示 |
  | 操作 | 删除/深度采集 |

### 2. 筛选功能
支持多维度组合筛选：
- **关键词搜索**：文本输入，模糊匹配 title 和 snippet
- **数据来源**：下拉选择框，从 watch_sources 表动态加载
- **时间范围**：日期选择器（开始日期 ~ 结束日期）
- **深度状态**：下拉选择（全部/已采集/未采集）

筛选条件动态构建 SQL WHERE 子句：
```python
conditions = []
params = []
if keyword:
    conditions.append("(title LIKE ? OR snippet LIKE ?)")
    params.extend([f'%{keyword}%', f'%{keyword}%'])
if source_id:
    conditions.append("source_id = ?")
    params.append(source_id)
if date_from:
    conditions.append("collected_at >= ?")
    params.append(date_from)
if date_to:
    conditions.append("collected_at <= ?")
    params.append(date_to)
if deep_status is not None:
    conditions.append("deep_status = ?")
    params.append(deep_status)

where_clause = " AND ".join(conditions) if conditions else "1=1"
```

### 3. 删除功能
- **单条删除**：每行操作列的删除按钮，二次确认
- **批量删除**：顶部复选框全选 + 批量删除按钮
- 删除后刷新当前页

### 4. AI深度采集入口（预留）
- **单条深度采集**：每行操作列的"深度采集"按钮
- **批量深度采集**：顶部"批量深度采集"按钮（需勾选记录）
- 深度采集状态标识：
  - `deep_status = 0`：显示灰色标签"未深度采集"
  - `deep_status = 1`：显示绿色标签"已深度采集"
- 已深度采集的数据支持查看详细内容（跳转到深度采集详情页）

### 5. 需要实现的文件

#### 控制器：`app/controllers/data_warehouse.py`
实现以下 Handler：
- `DataWarehouseListHandler` — GET 列表页（支持筛选参数）
  - 接收参数：keyword, source_id, date_from, date_to, deep_status, page
  - 动态构建 WHERE 条件
  - 返回分页数据
- `DataWarehouseDeleteHandler` — POST 单条删除
- `DataWarehouseBatchDeleteHandler` — POST 批量删除
  - 接收参数：ids（逗号分隔的ID字符串）

#### 模板：`app/templates/admin/data_warehouse.html`
- 继承 `base.html`
- **筛选栏**（顶部）：
  - 关键词输入框
  - 来源下拉选择（动态加载）
  - 日期范围选择（开始~结束）
  - 深度状态下拉（全部/已采集/未采集）
  - 查询按钮 / 重置按钮
- **操作栏**：
  - 全选复选框
  - 批量删除按钮
  - 批量深度采集按钮（预留，后续任务实现）
- **数据表格**：
  - 表头带排序指示（可选）
  - 每行有复选框
  - 深度状态带颜色标签
  - 操作列：查看/深度采集/删除
- **分页组件**：
  - 显示总条数
  - 上一页/下一页
  - 页码跳转
  - 每页20条

### 6. 路由注册
```python
("/admin/data-warehouse", DataWarehouseListHandler),
("/admin/data-warehouse/delete", DataWarehouseDeleteHandler),
("/admin/data-warehouse/batch-delete", DataWarehouseBatchDeleteHandler),
```

### 7. 前端交互要求
1. 筛选条件改变后点击"查询"才触发搜索
2. 分页切换保留当前筛选条件
3. 删除操作有二次确认弹窗（Bootstrap Modal）
4. 批量操作需要至少选中一条记录
5. 空数据状态显示友好提示

### 8. 样式要求
- 深度状态标签：
  - 未采集：`badge bg-secondary` 或自定义灰色
  - 已采集：`badge bg-success` 或自定义绿色
- 表格行hover效果
- 标题列文字过长时省略显示，hover显示完整内容（tooltip）

## 验收标准
- [ ] 列表每页显示20条，支持分页
- [ ] 支持按关键词、来源、时间范围、深度状态筛选
- [ ] 支持单条删除和批量删除
- [ ] 深度状态以标签形式展示（已采集/未采集）
- [ ] 预留单条和批量深度采集入口
- [ ] 筛选和分页参数联动
- [ ] 空数据状态友好提示
