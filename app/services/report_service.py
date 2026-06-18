# 问数报表服务 — NL→SQL 查询 + 数据聚合 + Markdown 表格 + 图表数据

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from app.models.db import get_connection


def generate_sql_report(user_query: str) -> dict:
    """
    根据自然语言描述生成数据报表。
    支持：时间范围（今天/昨天/上月/近7天/近30天）、指标聚合、用户/会话/消息统计。
    返回: {"type": "table"|"chart", "title": ..., "data": {...}, "sql": ..., "raw_rows": [...]}
    """
    q = user_query.strip().lower()
    now = datetime.now()

    # 时间范围识别
    time_range = None
    range_label = ""
    if "今天" in q:
        time_range = now.strftime("%Y-%m-%d")
        range_label = "今日"
    elif "昨天" in q:
        time_range = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        range_label = "昨日"
    elif "上月" in q or "上个月" in q:
        y, m = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        time_range = f"{y}-{m:02d}"
        range_label = f"{y}年{m}月"
    elif "近7天" in q or "最近7天" in q or "过去一周" in q:
        time_range = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        range_label = "近7天"
    elif "近30天" in q or "最近30天" in q or "过去一月" in q:
        time_range = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
        range_label = "近30天"

    # 主题识别
    report_type = _detect_report_type(q)
    title, sql, chart_type = _build_query(q, report_type, time_range, range_label, now)

    try:
        with get_connection() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
    except Exception as e:
        return {"error": f"SQL 查询失败：{str(e)}", "sql": sql, "title": title}

    # 格式化结果
    formatted = _format_result(rows, report_type, title, range_label, chart_type, sql)
    return formatted


def _detect_report_type(q: str) -> str:
    if any(w in q for w in ["用户", "注册"]):
        return "users"
    if any(w in q for w in ["对话", "聊天", "会话", "消息", "活跃"]):
        return "conversations"
    if any(w in q for w in ["token", "Token", "消耗"]):
        return "tokens"
    if any(w in q for w in ["技能", "skill"]):
        return "skills"
    if any(w in q for w in ["员工", "数字员工"]):
        return "employees"
    if any(w in q for w in ["模型", "引擎"]):
        return "models"
    if any(w in q for w in ["概览", "汇总", "总览", "综合", "全部"]):
        return "overview"
    return "general"


def _build_query(q: str, report_type: str, time_range, range_label: str, now: datetime) -> tuple:
    """构建 SQL、标题和图表类型"""
    title_map = {
        "users": "用户数据报表",
        "conversations": "对话活跃报表",
        "tokens": "Token 消耗报表",
        "skills": "技能调用报表",
        "employees": "数字员工运营报表",
        "models": "模型引擎使用报表",
        "overview": "系统综合概览报表",
        "general": "数据查询报表",
    }

    if isinstance(time_range, list):
        date_cond = f"date(created_at) IN ({','.join('?' for _ in time_range)})"
        date_params = time_range
        date_col = "date(created_at)"
        group_by = "date(created_at)"
        order_by = "date(created_at)"
        title = f"{range_label} {title_map[report_type]}"
        chart_type = "line"
    elif time_range and "-" in time_range and len(time_range) <= 10:
        date_cond = "date(created_at) = ?"
        date_params = [time_range]
        date_col = "'" + time_range + "'"
        group_by = "1"
        order_by = "1"
        title = f"{range_label} {title_map[report_type]}"
        chart_type = "bar"
    elif time_range:
        date_cond = "strftime('%Y-%m', created_at) = ?"
        date_params = [time_range]
        date_col = "strftime('%Y-%m-%d', created_at)"
        group_by = "strftime('%Y-%m-%d', created_at)"
        order_by = "strftime('%Y-%m-%d', created_at)"
        title = f"{range_label} {title_map[report_type]}"
        chart_type = "line"
    else:
        date_cond = "1=1"
        date_params = []
        date_col = "date(created_at)"
        group_by = "date(created_at)"
        order_by = "date(created_at) DESC"
        title = title_map[report_type]
        chart_type = "bar"

    queries = {
        "users": (
            f"SELECT {date_col} AS dt, COUNT(*) AS cnt FROM users WHERE {date_cond} GROUP BY {group_by} ORDER BY {order_by}",
            title, "bar",
        ),
        "conversations": (
            f"SELECT {date_col} AS dt, COUNT(*) AS cnt FROM conversations WHERE {date_cond} GROUP BY {group_by} ORDER BY {order_by}",
            title, "line",
        ),
        "tokens": (
            f"SELECT {date_col} AS dt, COALESCE(SUM(tokens_used),0) AS cnt FROM chat_messages WHERE {date_cond} GROUP BY {group_by} ORDER BY {order_by}",
            title, "line",
        ),
        "skills": (
            f"SELECT name AS dt, total_calls AS cnt FROM ai_skills ORDER BY total_calls DESC LIMIT 10",
            title, "bar",
        ),
        "employees": (
            f"SELECT name AS dt, 1 AS cnt FROM digital_employees",
            title, "bar",
        ),
        "models": (
            f"SELECT name AS dt, call_count AS cnt FROM model_engines ORDER BY call_count DESC",
            title, "bar",
        ),
        "overview": (
            f"""SELECT '总用户' AS dt, COUNT(*) AS cnt FROM users
            UNION ALL SELECT '总会话', COUNT(*) FROM conversations
            UNION ALL SELECT '总消息', COUNT(*) FROM chat_messages
            UNION ALL SELECT '总Token', COALESCE(SUM(tokens_used),0) FROM chat_messages
            UNION ALL SELECT '技能数', COUNT(*) FROM ai_skills
            UNION ALL SELECT '数字员工数', COUNT(*) FROM digital_employees""",
            "系统综合概览报表", "bar",
        ),
        "general": (
            f"SELECT {date_col} AS dt, COUNT(*) AS cnt FROM chat_messages WHERE {date_cond} GROUP BY {group_by} ORDER BY {order_by}",
            "数据查询报表", "bar",
        ),
    }

    sql, t, ct = queries.get(report_type, queries["general"])
    if report_type == "overview":
        return t, sql, ct
    return title, sql, ct


def _format_result(rows, report_type: str, title: str, range_label: str, chart_type: str, sql: str) -> dict:
    """格式化查询结果"""
    if not rows:
        return {"type": "empty", "title": title, "message": "暂无数据", "sql": sql}

    # 转为 list of dict
    data = []
    for r in rows:
        d = dict(r) if hasattr(r, 'keys') else r
        data.append(d)

    # 构建 Markdown 表格
    columns = list(data[0].keys())
    md_lines = [f"## {title}\n"]
    md_lines.append("| " + " | ".join(columns) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in data:
        vals = [str(row.get(c, "")) for c in columns]
        md_lines.append("| " + " | ".join(vals) + " |")

    # 汇总统计
    summary = {}
    if data and "cnt" in data[0]:
        summary["total"] = sum(r.get("cnt", 0) for r in data)
        summary["avg"] = round(summary["total"] / len(data), 1)
        summary["max"] = max(r.get("cnt", 0) for r in data)

    # 图表数据（ECharts 格式）
    chart_data = {
        "labels": [r.get("dt", "") for r in data],
        "values": [r.get("cnt", 0) for r in data],
    }

    return {
        "type": "report",
        "title": title,
        "chart_type": chart_type,
        "columns": columns,
        "rows": data,
        "summary": summary,
        "chart_data": chart_data,
        "markdown_table": "\n".join(md_lines),
        "sql": sql,
        "row_count": len(data),
    }


def export_report_csv(data: dict) -> str:
    """导出 CSV"""
    if not data.get("rows"):
        return ""
    cols = data.get("columns", [])
    lines = [",".join(cols)]
    for row in data["rows"]:
        lines.append(",".join(str(row.get(c, "")) for c in cols))
    return "\n".join(lines)


def export_report_json(data: dict) -> str:
    """导出 JSON"""
    export = {
        "title": data.get("title", ""),
        "columns": data.get("columns", []),
        "rows": data.get("rows", []),
        "summary": data.get("summary", {}),
        "generated_at": datetime.now().isoformat(),
    }
    return json.dumps(export, ensure_ascii=False, indent=2)
