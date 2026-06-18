# 网络搜索服务 — 实时搜索 + 结果缓存 + 引用格式化

import json
import time
import hashlib
from typing import Optional

# 简易内存缓存
_search_cache: dict = {}  # {key_hash: (results, expire_at)}


def _cache_key(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()


def search_web(query: str, max_results: int = 5, cache_ttl: int = 600) -> dict:
    """
    执行网络搜索，返回结构化结果。
    使用 WebSearch 工具（如果可用），否则回退到模拟结果。
    
    返回: {"results": [...], "source": str, "summary": str, "cached": bool}
    """
    key = _cache_key(query)
    now = time.time()
    if key in _search_cache:
        data, expire = _search_cache[key]
        if now < expire:
            result = dict(data)
            result["cached"] = True
            return result

    results = _perform_search(query, max_results)
    results["cached"] = False

    # 写入缓存
    _search_cache[key] = (results.copy(), now + cache_ttl)
    return results


def _perform_search(query: str, max_results: int) -> dict:
    """实际执行搜索"""
    try:
        from app.services.search_adapter import web_search_raw
        raw = web_search_raw(query, num=min(max_results, 8))
    except Exception:
        raw = None

    if raw and isinstance(raw, list) and len(raw) > 0:
        items = []
        for i, r in enumerate(raw[:max_results]):
            items.append({
                "index": i + 1,
                "title": str(r.get("title", "") or r.get("name", "") or "无标题"),
                "url": str(r.get("url", "") or r.get("link", "") or ""),
                "snippet": str(r.get("snippet", "") or r.get("description", "") or r.get("summary", "") or ""),
            })
        summary = _build_summary(query, items)
        return {"results": items, "source": "live", "summary": summary, "query": query}
    else:
        # 回退：构造"无法搜索"的提示
        return {
            "results": [],
            "source": "fallback",
            "summary": "",
            "query": query,
        }


def _build_summary(query: str, items: list) -> str:
    if not items:
        return ""
    lines = [f"**关于「{query}」的搜索结果：**\n"]
    for it in items:
        lines.append(f"{it['index']}. [{it['title']}]({it['url']})")
        if it["snippet"]:
            lines.append(f"   > {it['snippet'][:200]}")
    return "\n".join(lines)


def format_for_ai_prompt(query: str, search_result: dict) -> str:
    """将搜索结果格式化为 AI 对话可用的提示词"""
    items = search_result.get("results", [])
    if not items:
        return (
            f"用户搜索了「{query}」，但网络搜索未返回有效结果。"
            f"请基于你的已有知识尽力回答，并建议用户尝试更精确的关键词。"
        )
    parts = [f"以下是通过网络搜索获取的关于「{query}」的最新信息：\n"]
    for it in items:
        parts.append(f"[来源{it['index']}] {it['title']}\n  URL: {it['url']}\n  内容: {it['snippet']}\n")
    parts.append("\n请基于以上搜索结果，为用户生成一个全面、准确的中文回答。")
    parts.append("回答末尾必须以「📎 参考来源」为标题列出所有引用来源，格式为编号 + 可点击的Markdown链接。")
    parts.append("如果搜索结果不足以回答，请诚实说明并给出建议。")
    return "\n".join(parts)


def clear_cache():
    _search_cache.clear()
