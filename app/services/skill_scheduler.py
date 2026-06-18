# 技能调度系统 - \\xxx 命令解析、路由、分发与日志记录

r"""
技能调度器 (Skill Scheduler)

功能：
1. 解析用户输入中的反斜杠命令 (\search, \query, \weather 等) 和 @ 命令
2. 维护技能注册表，支持动态注册/注销技能处理器
3. 根据命令名称路由到对应的处理器并执行
4. 记录每次调度过程的日志（skill_call_logs 表）

使用方式：
    from app.services.skill_scheduler import register_skill, parse_command, dispatch_skill

    # 注册技能
    register_skill("search", handle_search, "网络搜索", category="工具")

    # 解析命令
    skill_name, args, is_cmd = parse_command("\\search Python教程")

    # 调度执行
    result = dispatch_skill(skill_name, args, context={"caller_name": "admin"})
"""

import re
import time
import json
from typing import Callable, Dict, Optional, Any, Tuple

# ============================================================
# 技能注册表（内存）
# ============================================================
_skill_registry: Dict[str, dict] = {}


def register_skill(name: str, handler: Callable, description: str = "",
                   category: str = "通用", aliases: list = None):
    """
    注册一个技能到调度系统。

    参数:
        name: 技能名称（命令关键词，如 "search"、"天气"）
        handler: 技能处理函数，签名为 handler(args: str, context: dict) -> dict
        description: 技能描述
        category: 技能分类
        aliases: 技能别名列表（如 ["网络搜索", "web_search"]）
    """
    name_lower = name.lower()
    entry = {
        "name": name,
        "handler": handler,
        "description": description,
        "category": category,
        "aliases": aliases or [],
    }
    _skill_registry[name_lower] = entry
    # 同时用别名注册
    for alias in (aliases or []):
        _skill_registry[alias.lower()] = entry


def unregister_skill(name: str):
    """注销一个技能（同时清理别名）"""
    name_lower = name.lower()
    entry = _skill_registry.get(name_lower)
    if entry:
        # 清理主名称和所有别名
        del _skill_registry[name_lower]
        for alias in entry.get("aliases", []):
            if alias.lower() in _skill_registry:
                del _skill_registry[alias.lower()]


def get_registered_skills() -> list:
    """
    获取所有已注册的技能列表（去重）。
    返回: [{"name": str, "description": str, "category": str, "aliases": list}, ...]
    """
    seen = set()
    result = []
    for key, entry in _skill_registry.items():
        name = entry["name"]
        if name not in seen:
            seen.add(name)
            result.append({
                "name": name,
                "description": entry["description"],
                "category": entry["category"],
                "aliases": entry.get("aliases", []),
            })
    return result


def parse_command(message: str) -> Tuple[Optional[str], str, bool]:
    r"""
    解析用户输入中的 \xxx 或 @xxx 命令。

    格式: \search 关键词   或   @天气 北京
    支持中文、英文、数字技能名。

    返回:
        (skill_name, args, is_command)
        - 如果是命令: skill_name 为技能名（小写），args 为参数
        - 如果不是命令: (None, message, False)
    """
    if not message or not isinstance(message, str):
        return None, "", False

    # 匹配 @技能名 或 \技能名
    match = re.match(r'[@\\]([\u4e00-\u9fa5a-zA-Z0-9]+)\s*(.*)', message.strip())
    if match:
        skill_name = match.group(1).strip().lower()
        skill_args = match.group(2).strip()
        return skill_name, skill_args, True
    return None, message, False


def dispatch_skill(skill_name: str, args: str, context: dict = None) -> dict:
    """
    调度执行一个技能。

    查找顺序：
    1. 内存注册表（通过 register_skill 注册的）
    2. 数据库 ai_skills 表（已启用、名称或触发关键词匹配）

    参数:
        skill_name: 技能名称
        args: 命令参数
        context: 上下文信息（caller_type, caller_id, caller_name 等）

    返回:
        {
            "success": bool,
            "data": ... 或 None,
            "error": str,
            "skill_name": str,
            "skill_source": "registry" | "database" | "unknown",
            "duration_ms": int,
        }
    """
    context = context or {}
    skill_name_lower = skill_name.lower()
    t0 = time.time()

    # 1. 查找内存注册表
    skill_entry = _skill_registry.get(skill_name_lower)
    skill_source = "unknown"

    if skill_entry:
        skill_source = "registry"
        handler = skill_entry.get("handler")
    else:
        # 2. 查找数据库
        db_skill = _lookup_db_skill(skill_name_lower)
        if db_skill:
            skill_source = "database"
            skill_entry = {"name": db_skill.get("name"), "handler": None,
                           "db_skill": db_skill}
            handler = None
        else:
            duration_ms = int((time.time() - t0) * 1000)
            return {
                "success": False,
                "data": None,
                "error": f"技能 '{skill_name}' 未注册或未启用",
                "skill_name": skill_name,
                "skill_source": "unknown",
                "duration_ms": duration_ms,
            }

    # 3. 执行处理器
    try:
        data = handler(args, context) if handler else {"_from_db": True, "skill": skill_entry.get("db_skill")}
        duration_ms = int((time.time() - t0) * 1000)
        _log_dispatch(skill_name, skill_source, context, duration_ms, success=True)
        return {
            "success": True,
            "data": data,
            "skill_name": skill_name,
            "skill_source": skill_source,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        _log_dispatch(skill_name, skill_source, context, duration_ms,
                      success=False, error=str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
            "skill_name": skill_name,
            "skill_source": skill_source,
            "duration_ms": duration_ms,
        }


# ============================================================
# 内部辅助函数
# ============================================================

def _lookup_db_skill(skill_name: str) -> Optional[dict]:
    """从数据库 ai_skills 表查找启用中的匹配技能"""
    try:
        from app.models.ai_skill import AiSkillRepository
        skills = AiSkillRepository.get_all(enabled_only=True)
        for sk in skills:
            sk_dict = dict(sk) if hasattr(sk, 'keys') else sk
            # 按名称匹配
            if skill_name == sk_dict.get("name", "").lower():
                return sk_dict
            # 按触发关键词匹配
            keywords = sk_dict.get("trigger_keywords", "[]")
            try:
                kw_list = json.loads(keywords) if isinstance(keywords, str) else keywords
                if skill_name in [str(k).lower().strip() for k in kw_list]:
                    return sk_dict
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass
    return None


def _log_dispatch(skill_name: str, source: str, context: dict,
                  duration_ms: int, success: bool, error: str = ""):
    """记录调度日志到 skill_call_logs 表"""
    try:
        from app.models.ai_skill import SkillCallLogRepository
        SkillCallLogRepository.create(
            skill_id=0,
            skill_name=f"{skill_name} [{source}]",
            caller_type=context.get("caller_type", "user"),
            caller_id=context.get("caller_id", 0),
            caller_name=context.get("caller_name", ""),
            duration_ms=duration_ms,
            success=1 if success else 0,
            error_message=error,
        )
    except Exception:
        pass  # 日志记录失败不影响主流程


# ============================================================
# 内置技能注册（由 web_chat.py 启动时调用）
# ============================================================

def register_builtin_skills():
    """
    注册所有内置技能。由 web_chat 模块在加载时调用。

    内置技能列表：
    - search / 搜索：网络搜索
    - weather / 天气：天气查询
    - music / 音乐：音乐搜索
    - report / 报表 / 问数报表：数据库问数报表
    - help / 帮助：技能帮助
    """
    import time as _time

    # ---- 网络搜索 ----
    try:
        from app.services.web_search import search_web, format_for_ai_prompt

        def _handle_search(args: str, ctx: dict) -> dict:
            from app.models.web_search_log import WebSearchLogRepository
            t0 = _time.time()
            query = args.strip()
            if not query:
                return {"results": [], "source": "empty", "result_count": 0,
                        "prompt_fragment": "用户未提供搜索关键词。"}
            result = search_web(query, max_results=5)
            source = result.get("source", "fallback")
            items = result.get("results", [])
            urls = json.dumps([it.get("url", "") for it in items])
            dur = int((_time.time() - t0) * 1000)
            WebSearchLogRepository.log(
                query=query, result_count=len(items),
                source=source, source_urls=urls, duration_ms=dur,
            )
            return {
                "results": items,
                "source": source,
                "result_count": len(items),
                "prompt_fragment": format_for_ai_prompt(query, result),
                "cached": result.get("cached", False),
            }

        register_skill("search", _handle_search, "网络搜索，获取互联网最新信息",
                       category="搜索", aliases=["搜索", "网络搜索"])
    except ImportError:
        pass

    # ---- 天气查询 ----
    try:
        from app.services.weather_service import get_weather

        def _handle_weather(args: str, ctx: dict) -> dict:
            city = args.strip() or "北京"
            return get_weather(city)

        register_skill("weather", _handle_weather, "天气查询，获取指定城市的实时天气和预报",
                       category="生活", aliases=["天气"])
    except ImportError:
        pass

    # ---- 音乐搜索 ----
    try:
        from app.services.music_service import search_music

        def _handle_music(args: str, ctx: dict) -> dict:
            query = args.strip() or "热门"
            return search_music(query)

        register_skill("music", _handle_music, "音乐搜索，发现歌曲和歌手信息",
                       category="娱乐", aliases=["音乐"])
    except ImportError:
        pass

    # ---- 问数报表 ----
    try:
        from app.services.report_service import generate_sql_report, export_report_csv, export_report_json

        def _handle_report(args: str, ctx: dict) -> dict:
            query = args.strip()
            if not query:
                return {"error": "请提供报表需求描述", "type": "empty", "title": "报表"}
            result = generate_sql_report(query)
            if export_report_csv:
                result["csv"] = export_report_csv(result)
            if export_report_json:
                result["json"] = export_report_json(result)
            return result

        register_skill("report", _handle_report, "数据库问数报表，自动生成 SQL 并汇总数据",
                       category="数据", aliases=["报表", "问数报表"])
    except ImportError:
        pass

    # ---- 帮助 ----
    def _handle_help(args: str, ctx: dict) -> dict:
        skills = get_registered_skills()
        lines = []
        for s in skills:
            aliases_str = f"（别名: {', '.join(s['aliases'])}）" if s.get("aliases") else ""
            lines.append(f"- `\\{s['name']}` 或 `@{s['name']}`：{s['description']} {aliases_str}")
        return {"help_text": "\n".join(lines), "skills": skills}

    register_skill("help", _handle_help, "查看所有可用技能列表",
                   category="系统", aliases=["帮助", "?", "？"])
