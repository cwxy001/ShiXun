# 搜索适配器 — 将环境可用的 WebSearch 工具转为标准化接口

import json


def web_search_raw(query: str, num: int = 5) -> list:
    """
    适配层: 调用 WebSearch 工具获取搜索结果。
    返回: [{"title": ..., "url": ..., "snippet": ...}, ...]
    
    注意：此函数依赖 Trae IDE 提供的 WebSearch 能力。
    在运行时环境中，WebSearch 通过 IDE 内置机制工作。
    本适配器提供标准化接口，便于后续替换搜索引擎。
    """
    # 此函数作为占位接口。
    # 实际执行搜索的逻辑在 web_search.py 的 _perform_search 中，
    # 当 WebSearch 工具在运行时可用时自动调用。
    # 此处返回 None 表示"需要 fallback"。
    return []
