# 前台 AI 问数对话控制器 — SSE 流式 + 意图识别 + 历史管理

import json
import time
import tornado.web
from openai import OpenAI

from app.models.model_engine import ModelEngineRepository
from app.models.conversation import ConversationRepository, ChatMessageRepository
from app.models.db import get_connection

# 数字员工/技能相关导入
try:
    from app.models.digital_employee import DigitalEmployeeRepository
    from app.models.ai_skill import AiSkillRepository
    from app.controllers.digital_employee import build_employee_system_prompt, _resolve_skill_ids
except ImportError:
    DigitalEmployeeRepository = None
    AiSkillRepository = None
    build_employee_system_prompt = None
    _resolve_skill_ids = None

# 技能调度系统导入
from app.services.skill_scheduler import (
    parse_command, dispatch_skill, register_builtin_skills, get_registered_skills
)

# 技能服务导入（保留用于兼容旧代码）
try:
    from app.services.weather_service import get_weather
except ImportError:
    get_weather = None
try:
    from app.services.music_service import search_music
except ImportError:
    search_music = None
try:
    from app.services.report_service import generate_sql_report, export_report_csv, export_report_json
except ImportError:
    generate_sql_report = None
    export_report_csv = None
    export_report_json = None

# 注册内置技能（搜索、天气、音乐、报表、帮助）
register_builtin_skills()


def _require_web_login(handler):
    username = handler.get_secure_cookie("admin_user")
    if not username:
        handler.redirect("/login")
        return False, ""
    if isinstance(username, bytes):
        username = username.decode()
    return True, username


def _get_user_id(username: str) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        return row["id"] if row else 0


def _int_arg(handler, key, default=0):
    try:
        return int(handler.get_argument(key, str(default)))
    except (ValueError, TypeError):
        return default


class ChatPageHandler(tornado.web.RequestHandler):
    """AI 问数对话主页面"""

    def get(self):
        ok, username = _require_web_login(self)
        if not ok:
            return
        user_id = _get_user_id(username)
        # 获取可用模型列表
        models = ModelEngineRepository.get_all()
        models_list = [dict(m) for m in models]
        # 获取用户对话历史
        conversations = ConversationRepository.get_by_user(user_id)
        conversations_list = [dict(c) for c in conversations]
        # 获取最后活跃的对话ID
        last_msg_id = ChatMessageRepository.get_last_message_id(user_id)
        self.render(
            "web/chat.html",
            username=username,
            models=models_list,
            conversations=conversations_list,
            conv_id=last_msg_id or 0,
        )


class ChatSSEHandler(tornado.web.RequestHandler):
    """SSE 流式对话接口 — 含意图识别 & SQL 问数"""

    async def post(self):
        ok, username = _require_web_login(self)
        if not ok:
            return
        user_id = _get_user_id(username)

        # 支持 JSON body 和 form-encoded body
        content_type = self.request.headers.get("Content-Type", "")
        if "application/json" in content_type:
            body = json.loads(self.request.body or "{}")
            user_message = body.get("message", "").strip()
            conversation_id = body.get("conversation_id", 0)
            model_engine_id = body.get("model_engine_id", 0)
        else:
            user_message = self.get_body_argument("message", "").strip()
            conversation_id = _int_arg(self, "conversation_id", 0)
            model_engine_id = _int_arg(self, "model_engine_id", 0)

        if not user_message:
            self.set_status(400)
            self.finish()
            return

        # 获取模型
        model = None
        if model_engine_id:
            model = ModelEngineRepository.get_by_id(model_engine_id)
        if not model:
            model = ModelEngineRepository.get_default()
        if not model:
            model = ModelEngineRepository.get_all()
            if model:
                model = model[0]
            else:
                self.set_status(500)
                self.finish()
                return

        # 新建或获取会话
        if conversation_id:
            conv = ConversationRepository.get_by_id(conversation_id)
            if not conv or conv["user_id"] != user_id:
                conversation_id = 0
        if not conversation_id:
            conversation_id = ConversationRepository.create(
                user_id, user_message[:30],
                model["id"], model["model_name"]
            )
        else:
            ConversationRepository.update_model(conversation_id, model["id"], model["model_name"])

        # 获取历史消息（最近20条）
        history = ChatMessageRepository.get_last_n(conversation_id, 20)

        # 意图识别：检测是否为 SQL 问数请求
        intent = _detect_intent(user_message)

        # @xxx / \xxx 数字员工调用检测（使用技能调度器）
        skill_name, skill_args, is_skill = parse_command(user_message)
        resolved_name = skill_name
        cached_skill_prompt = ""
        search_result = None  # 网络搜索结果
        skill_service_data = None  # 天气/音乐/报表服务数据
        dispatch_result = None  # 调度器执行结果

        if is_skill:
            cached_skill_prompt, resolved_name = _get_skill_prompt(skill_name, skill_args)

            # 通过技能调度器统一调度执行
            dispatch_result = dispatch_skill(skill_name, skill_args, context={
                "caller_type": "web_user",
                "caller_id": user_id,
                "caller_name": username,
            })

            if dispatch_result["success"]:
                data = dispatch_result["data"]
                if data:
                    # 根据技能类型分类处理调度结果
                    if skill_name.lower() in ("search", "搜索"):
                        search_result = data
                    elif skill_name.lower() in ("天气", "weather"):
                        skill_service_data = data
                    elif skill_name.lower() in ("音乐", "music"):
                        skill_service_data = data
                    elif skill_name.lower() in ("报表", "report", "问数报表"):
                        skill_service_data = data
            else:
                # 调度失败，但继续尝试让 AI 回答（使用缓存的 prompt）
                pass

        # 非 @ 指令：检测是否有报表意图关键词
        is_report = False
        if not is_skill and generate_sql_report:
            rpt_keywords = ["生成报表", "数据报表", "统计报表", "问数报表", "报表导出", "数据报告"]
            for kw in rpt_keywords:
                if kw in user_message:
                    is_report = True
                    # 通过调度器执行报表
                    dispatch_result = dispatch_skill("report", user_message, context={
                        "caller_type": "web_user",
                        "caller_id": user_id,
                        "caller_name": username,
                    })
                    if dispatch_result["success"] and dispatch_result["data"]:
                        skill_service_data = dispatch_result["data"]
                    else:
                        skill_service_data = _execute_report(user_message)
                    is_skill = True
                    skill_name = "report"
                    resolved_name = "问数报表"
                    break

        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        try:
            # 如果是 @xxx 数字员工调用，先发送通知事件（含员工信息）
            if is_skill:
                emp_info = _lookup_employee(skill_name)
                extra = ""
                sdata = None
                if search_result:
                    rc = search_result.get("result_count", 0)
                    source = search_result.get("source", "live")
                    extra = f" | 已检索到 {rc} 条结果 ({source})"
                elif skill_service_data:
                    sdata = skill_service_data
                    if skill_name.lower() in ("天气", "weather"):
                        if sdata.get("temperature") is not None:
                            extra = f" | {sdata['city']} {sdata['temperature']}°C {sdata['weather']}"
                        else:
                            extra = f" | {sdata.get('error', '查询中')}"
                    elif skill_name.lower() in ("音乐", "music"):
                        rc = sdata.get("result_count", 0)
                        extra = f" | 找到 {rc} 首歌曲"
                    elif skill_name.lower() in ("报表", "report", "问数报表"):
                        row_count = sdata.get("row_count", 0) if sdata else 0
                        extra = f" | {sdata.get('title', '报表')} ({row_count}行)"
                skill_start = json.dumps({
                    "type": "skill_start",
                    "skill": resolved_name,
                    "display_name": emp_info.get("display_name", resolved_name),
                    "avatar": emp_info.get("avatar", ""),
                    "role": emp_info.get("role", ""),
                    "content": f"正在调用{'网络搜索' if search_result else '数字员工'} @{resolved_name} ...{extra}",
                    "search_info": search_result,
                    "service_data": sdata,
                    "service_type": skill_name.lower() if skill_service_data else None,
                }, ensure_ascii=False)
                self.write(f"data: {skill_start}\n\n")
                await self.flush()

            api_key = model["api_key"] or "YOUR_API_KEY"
            api_base = model["api_base"] or "https://api.openai.com/v1"
            model_name = model["model_name"] or "gpt-3.5-turbo"
            system_prompt = model["system_prompt"] or ""

            client = OpenAI(api_key=api_key, base_url=api_base)

            # 保存用户消息
            ChatMessageRepository.add(conversation_id, "user", user_message)
            ConversationRepository.touch(conversation_id)

            # 构建消息列表
            messages = []

            # 系统提示词：@xxx 数字员工 > 服务数据 > SQL > 自定义 > 默认
            if is_skill:
                # 搜索类技能：如有实时搜索结果
                if search_result and search_result.get("prompt_fragment"):
                    messages.append({
                        "role": "system",
                        "content": (
                            "你是一个网络搜索助手。用户正在进行网络信息检索。\n"
                            "你的任务是基于以下搜索结果，为用户提供准确、全面的回答。\n\n"
                            + search_result["prompt_fragment"]
                        )
                    })
                # 天气服务：注入实时天气数据
                elif skill_service_data and skill_name.lower() in ("天气", "weather"):
                    messages.append({
                        "role": "system",
                        "content": _build_weather_prompt(skill_service_data),
                    })
                # 音乐服务：注入搜索结果
                elif skill_service_data and skill_name.lower() in ("音乐", "music"):
                    messages.append({
                        "role": "system",
                        "content": _build_music_prompt(skill_service_data),
                    })
                # 报表服务：注入报表数据
                elif skill_service_data and skill_name.lower() in ("报表", "report", "问数报表"):
                    messages.append({
                        "role": "system",
                        "content": _build_report_prompt(skill_service_data),
                    })
                else:
                    messages.append({"role": "system", "content": cached_skill_prompt})
            elif intent == "sql":
                sql_schema = _get_db_schema()
                sql_prompt = (
                    "你是一个智能问数助手。用户已经请求查询数据库中的数据。\n"
                    "你的回答必须严格遵循以下规则：\n"
                    "1. 根据用户的问题，生成对应的 SQLite SQL 语句查询数据库\n"
                    "2. 严禁在回复中展示任何 SQL 语句内容，包括 SELECT、FROM、WHERE 等关键字\n"
                    "3. 用自然语言解释查询结果，让用户理解数据含义\n"
                    "4. 如果用户的问数意图不明确，请追问具体想查询什么数据\n"
                    "5. 如果查询无结果，友好地告知用户并建议调整条件\n\n"
                    "数据库表结构如下：\n"
                    f"{sql_schema}\n\n"
                    "你需要在内部生成 SQL 查询（不展示），然后将结果转化为用户友好的自然语言回答。"
                )
                messages.append({"role": "system", "content": sql_prompt})
            elif system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({
                    "role": "system",
                    "content": "你是 IOIQ 智能助手，擅长数据问答、信息检索和知识解答。回答简洁、专业、友好。"
                })

            # 添加历史消息
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})

            # 当前用户消息
            messages.append({"role": "user", "content": user_message})

            # 调用 OpenAI 流式
            stream = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=model["temperature"] if model["temperature"] else 0.7,
                max_tokens=model["max_tokens"] if model["max_tokens"] else 2048,
                stream=True,
            )

            full_content = ""
            total_tokens = 0
            t0 = time.time()

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full_content += delta.content
                    data = json.dumps({
                        "type": "content",
                        "content": delta.content,
                        "conversation_id": conversation_id,
                    }, ensure_ascii=False)
                    self.write(f"data: {data}\n\n")
                    await self.flush()

                if chunk.usage and chunk.usage.total_tokens:
                    total_tokens = chunk.usage.total_tokens

                # 如果是 SQL 意图，检查 AI 回复中是否包含 SQL（拦截展示）
                # 实际做法：AI 自己遵守规则不展示 SQL

            elapsed = int((time.time() - t0) * 1000)

            # 保存 AI 回复
            ChatMessageRepository.add(conversation_id, "assistant", full_content, total_tokens)

            # 更新模型 token 统计
            if total_tokens > 0:
                ModelEngineRepository.add_tokens(model["id"], total_tokens)

            # 如果是第一条用户消息，更新对话标题
            if len(history) == 0:
                title = user_message[:30] + ("..." if len(user_message) > 30 else "")
                ConversationRepository.update_title(conversation_id, title)

            # 发送结束事件
            done_info = {
                "type": "done",
                "tokens": total_tokens,
                "duration_ms": elapsed,
                "conversation_id": conversation_id,
            }
            if is_skill:
                done_info["skill"] = resolved_name
                emp = _lookup_employee(skill_name)
                done_info["display_name"] = emp.get("display_name", resolved_name)
                done_info["avatar"] = emp.get("avatar", "")
            # 附加服务数据给前端渲染
            if skill_service_data:
                if skill_name.lower() in ("天气", "weather"):
                    done_info["weather_data"] = skill_service_data
                elif skill_name.lower() in ("音乐", "music"):
                    done_info["music_data"] = skill_service_data
                elif skill_name.lower() in ("报表", "report", "问数报表"):
                    done_info["report_data"] = {
                        "title": skill_service_data.get("title"),
                        "chart_type": skill_service_data.get("chart_type"),
                        "chart_data": skill_service_data.get("chart_data"),
                        "summary": skill_service_data.get("summary"),
                        "csv": export_report_csv(skill_service_data) if export_report_csv else "",
                        "json": export_report_json(skill_service_data) if export_report_json else "",
                    }
            if search_result:
                done_info["search_data"] = {
                    "results": search_result.get("results", []),
                    "source": search_result.get("source"),
                }
            done_data = json.dumps(done_info, ensure_ascii=False)
            self.write(f"data: {done_data}\n\n")
            await self.flush()

        except Exception as e:
            error_msg = str(e)
            ChatMessageRepository.add(conversation_id, "assistant", f"[错误] {error_msg}")
            data = json.dumps({
                "type": "error",
                "content": f"请求失败：{error_msg}",
            }, ensure_ascii=False)
            self.write(f"data: {data}\n\n")
            await self.flush()


class ChatHistoryHandler(tornado.web.RequestHandler):
    """获取会话的历史消息"""

    def get(self):
        ok, username = _require_web_login(self)
        if not ok:
            return
        conv_id = int(self.get_argument("conversation_id", "0"))
        user_id = _get_user_id(username)
        conv = ConversationRepository.get_by_id(conv_id)
        if not conv or conv["user_id"] != user_id:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"error": "无权访问"}, ensure_ascii=False))
            return
        messages = ChatMessageRepository.get_by_conversation(conv_id)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "conversation": dict(conv),
            "messages": [dict(m) for m in messages],
        }, ensure_ascii=False))


class ChatEmployeesHandler(tornado.web.RequestHandler):
    """返回可用数字员工列表（供前端 @mention 下拉使用）"""

    def get(self):
        ok, username = _require_web_login(self)
        if not ok:
            return
        employees = _get_available_employees()
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(json.dumps({"employees": employees}, ensure_ascii=False))


def _get_available_employees() -> list:
    """获取启用的数字员工及其技能列表（含技能调度器中注册的技能）"""
    employees = []
    # 先从数据库读取
    if DigitalEmployeeRepository:
        try:
            db_emps = DigitalEmployeeRepository.get_all(enabled_only=True)
            for emp in db_emps:
                emp_dict = dict(emp) if hasattr(emp, 'keys') else emp
                # 解析绑定的技能
                skills_json = emp_dict.get("skills", "[]")
                try:
                    skills = json.loads(skills_json) if isinstance(skills_json, str) else skills_json
                except (json.JSONDecodeError, TypeError):
                    skills = []
                employees.append({
                    "name": emp_dict.get("name", ""),
                    "trigger": (emp_dict.get("name") or "").lower(),
                    "avatar": emp_dict.get("avatar", ""),
                    "role": emp_dict.get("role_name", ""),
                    "skills": skills,
                    "status": emp_dict.get("status", "enabled"),
                })
        except Exception:
            pass
    # 补充默认内置技能
    builtin_names = {e["trigger"] for e in employees}
    builtins = [
        {"name": "天气", "trigger": "天气", "avatar": "", "role": "天气查询助手", "skills": [], "status": "enabled"},
        {"name": "音乐", "trigger": "音乐", "avatar": "", "role": "音乐推荐助手", "skills": [], "status": "enabled"},
        {"name": "西师妹", "trigger": "西师妹", "avatar": "", "role": "AI 伙伴", "skills": [], "status": "enabled"},
        {"name": "search", "trigger": "search", "avatar": "", "role": "网络搜索助手", "skills": [], "status": "enabled"},
        {"name": "help", "trigger": "help", "avatar": "", "role": "帮助助手", "skills": [], "status": "enabled"},
    ]
    for b in builtins:
        if b["trigger"] not in builtin_names:
            employees.append(b)
    # 补充技能调度器中注册的技能
    try:
        reg_skills = get_registered_skills()
        for sk in reg_skills:
            sk_name = sk["name"]
            sk_name_lower = sk_name.lower()
            if sk_name_lower not in builtin_names and sk_name_lower not in [e["trigger"] for e in employees]:
                employees.append({
                    "name": sk_name,
                    "trigger": sk_name_lower,
                    "avatar": "",
                    "role": sk.get("description", f"\\{sk_name} 技能"),
                    "skills": [],
                    "status": "enabled",
                })
    except Exception:
        pass
    return employees


class ChatDeleteHandler(tornado.web.RequestHandler):
    """删除对话"""

    def post(self):
        ok, username = _require_web_login(self)
        if not ok:
            return
        conv_id = int(self.get_body_argument("conversation_id", "0"))
        user_id = _get_user_id(username)
        conv = ConversationRepository.get_by_id(conv_id)
        if not conv or conv["user_id"] != user_id:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"error": "无权操作"}, ensure_ascii=False))
            return
        ConversationRepository.delete(conv_id)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"ok": True}, ensure_ascii=False))


def _detect_intent(message: str) -> str:
    """简单意图识别"""
    sql_keywords = ["查询", "统计", "有多少", "列表", "数据", "记录", "汇总",
                    "查一下", "帮我查", "问数", "数据库", "表", "字段",
                    "哪个", "哪些", "多少条", "一共有"]
    weather_keywords = ["天气", "气温", "下雨", "多云", "晴天", "阴天"]
    music_keywords = ["音乐", "歌曲", "歌", "听", "播放", "专辑"]

    msg_lower = message.lower()
    for kw in weather_keywords:
        if kw in message:
            return "weather"
    for kw in music_keywords:
        if kw in message:
            return "music"
    for kw in sql_keywords:
        if kw in message:
            return "sql"
    return "chat"


def _parse_at_command(message: str):
    """
    [已废弃] 请使用 app.services.skill_scheduler.parse_command 代替。
    解析 @xxx 或 \\xxx 数字员工调用命令。
    返回 (skill_name, cleaned_message, is_skill)
    支持格式：@天气 北京、@音乐 周杰伦、@西师妹 你好、@search Python教程
    也支持反斜杠格式：\\search Python教程
    """
    import re

    # 匹配 @技能名 或 \\技能名
    match = re.match(r'[@\\]([\u4e00-\u9fa5a-zA-Z0-9]+)\s*(.*)', message)
    if match:
        skill_name = match.group(1).lower()
        skill_args = match.group(2).strip()
        return skill_name, skill_args, True
    return None, message, False


def _execute_web_search(query: str) -> dict:
    """执行网络搜索，返回结果摘要"""
    import time as _time
    from app.models.web_search_log import WebSearchLogRepository
    t0 = _time.time()
    try:
        from app.services.web_search import search_web, format_for_ai_prompt
        result = search_web(query, max_results=5)
        source = result.get("source", "fallback")
        items = result.get("results", [])
        # 记录搜索日志
        urls = json.dumps([it.get("url", "") for it in items])
        duration = int((_time.time() - t0) * 1000)
        WebSearchLogRepository.log(
            query=query,
            result_count=len(items),
            source=source,
            source_urls=urls,
            duration_ms=duration,
        )
        return {
            "results": items,
            "source": source,
            "result_count": len(items),
            "prompt_fragment": format_for_ai_prompt(query, result),
            "cached": result.get("cached", False),
        }
    except Exception as e:
        return {
            "results": [],
            "source": "error",
            "result_count": 0,
            "prompt_fragment": f"网络搜索失败：{str(e)}。请基于已有知识回答。",
            "error": str(e),
        }


def _execute_weather(city: str) -> dict:
    """执行天气查询"""
    try:
        if get_weather:
            result = get_weather(city)
            return result
    except Exception as e:
        pass
    return {"error": "天气服务不可用", "city": city}


def _execute_music(query: str) -> dict:
    """执行音乐查询"""
    try:
        if search_music:
            result = search_music(query)
            return result
    except Exception:
        pass
    return {"error": "音乐服务不可用", "query": query, "results": []}


def _execute_report(query: str) -> dict:
    """执行问数报表生成"""
    try:
        if generate_sql_report:
            result = generate_sql_report(query)
            # 预生成 CSV/JSON 以供前端渲染
            if export_report_csv:
                result["csv"] = export_report_csv(result)
            if export_report_json:
                result["json"] = export_report_json(result)
            return result
    except Exception:
        pass
    return {"error": "报表服务不可用", "type": "empty", "title": "报表"}


def _lookup_employee(skill_name: str) -> dict:
    """查找数字员工的显示信息"""
    skill_lower = skill_name.lower()
    if DigitalEmployeeRepository:
        try:
            employees = DigitalEmployeeRepository.get_all(enabled_only=True)
            for emp in employees:
                emp_dict = dict(emp) if hasattr(emp, 'keys') else emp
                if skill_lower == (emp_dict.get("name") or "").lower():
                    return {
                        "display_name": emp_dict.get("name", skill_name),
                        "avatar": emp_dict.get("avatar", ""),
                        "role": emp_dict.get("role_name", ""),
                    }
        except Exception:
            pass
    return {"display_name": skill_name, "avatar": "", "role": ""}


def _build_weather_prompt(data: dict) -> str:
    """将天气API数据格式化为AI提示词"""
    if data.get("error"):
        return f"天气查询失败：{data['error']}。请友好告知用户并建议稍后重试或查询其他城市。"

    city = data.get("city", "未知")
    temp = data.get("temperature", "N/A")
    feels = data.get("feels_like", "N/A")
    weather = data.get("weather", "未知")
    humidity = data.get("humidity", "N/A")
    wind = data.get("wind_speed", "N/A")
    wind_dir = data.get("wind_direction", "")
    pressure = data.get("pressure", "N/A")

    prompt = (
        f"你是一个专业的气象播报员。请根据以下实时天气数据，为用户生成一个自然友好的中文天气播报。\n\n"
        f"**当前天气数据（{city}）：**\n"
        f"- 温度：{temp}°C（体感 {feels}°C）\n"
        f"- 天气：{weather}\n"
        f"- 湿度：{humidity}%\n"
        f"- 风力：{wind} km/h {wind_dir}\n"
        f"- 气压：{pressure} hPa\n"
    )

    forecast = data.get("forecast", [])
    if forecast:
        prompt += "\n**未来预报：**\n"
        for f in forecast:
            prompt += f"- {f['date']}：{f['weather']}，{f['low']}°C ~ {f['high']}°C"
            if f.get("precip_pct"):
                prompt += f"，降水概率 {f['precip_pct']}%"
            prompt += "\n"

    prompt += (
        "\n请以温馨自然的语气播报，包括：\n"
        "1. 一句话概括当前天气\n"
        "2. 逐项说明温湿度、风力等\n"
        "3. 未来趋势\n"
        "4. 生活建议（穿衣/出行/防晒等）\n"
        "使用适当的表情符号让播报更生动。"
    )
    return prompt


def _build_music_prompt(data: dict) -> str:
    """将音乐API数据格式化为AI提示词"""
    if data.get("error"):
        return f"音乐查询失败：{data['error']}。请友好告知用户并建议稍后重试。"

    query = data.get("query", "")
    items = data.get("results", [])
    if not items:
        return f"未找到与「{query}」相关的音乐。请友好告知用户，并建议尝试其他关键词。"

    prompt = (
        f"你是一个音乐推荐助手。用户搜索了「{query}」，以下是通过 Apple Music 获取的真实歌曲数据：\n\n"
    )
    for i, it in enumerate(items[:8]):
        artist = it.get("artist_name", "")
        track = it.get("track_name", "")
        album = it.get("collection_name", "")
        genre = it.get("primary_genre", "")
        url = it.get("track_view_url", "")
        sec = int(it.get("track_time_ms", 0)) // 1000
        dur = f"{sec//60}:{sec%60:02d}" if sec else ""
        prompt += f"{i+1}. {track} — {artist}\n"
        prompt += f"   专辑：{album} | 流派：{genre} | 时长：{dur}\n"
        if url:
            prompt += f"   [试听/购买]({url})\n"

    prompt += (
        "\n请基于以上数据，为用户生成一个专业的音乐推荐回复：\n"
        "1. 简要介绍搜索结果\n"
        "2. 逐首推荐（歌名、歌手、亮点）\n"
        "3. 如果有相似风格，推荐更多试听方向\n"
        "4. 鼓励用户点击链接试听\n"
        "回复格式使用 Markdown，歌曲名用粗体。"
    )
    return prompt


def _build_report_prompt(data: dict) -> str:
    """将报表数据格式化为AI提示词"""
    if data.get("error"):
        return f"报表生成失败：{data['error']}。请友好告知用户。"

    if data.get("type") == "empty":
        return f"报表「{data.get('title', '')}」暂无数据。请友好告知用户。"

    title = data.get("title", "数据报表")
    md_table = data.get("markdown_table", "")
    summary = data.get("summary", {})
    chart_data = data.get("chart_data", {})

    prompt = (
        f"你是一个数据分析师。用户需要生成一份数据报表。\n"
        f"以下是系统从数据库中自动查询并汇总的结果：\n\n"
        f"{md_table}\n\n"
    )
    if summary:
        prompt += "**数据摘要：**\n"
        if summary.get("total"):
            prompt += f"- 总计：{summary['total']}\n"
        if summary.get("avg"):
            prompt += f"- 均值：{summary['avg']}\n"
        if summary.get("max"):
            prompt += f"- 峰值：{summary['max']}\n"
        prompt += "\n"

    prompt += (
        "请基于以上数据，为用户撰写一份专业的分析报告：\n"
        "1. 报告标题\n"
        "2. 数据概览（一句话总结核心发现）\n"
        "3. 关键指标分析\n"
        "4. 趋势解读与洞察\n"
        "5. 建议（如适用）\n"
        "使用 Markdown 格式，包含表格和强调标记。"
    )
    return prompt


def _get_skill_prompt(skill_name: str, skill_args: str) -> tuple:
    """根据技能名称，返回对应的系统提示词。
    优先从数字员工表匹配 → 技能表匹配 → 硬编码回退。
    返回 (prompt, display_name)"""

    # 1. 从数据库查找匹配的数字员工（使用共享函数构建 prompt）
    if DigitalEmployeeRepository and build_employee_system_prompt:
        try:
            employees = DigitalEmployeeRepository.get_all(enabled_only=True)
            for emp in employees:
                emp_dict = dict(emp) if hasattr(emp, 'keys') else emp
                emp_name = (emp_dict.get("name") or "").lower()
                # 按名称匹配
                if skill_name == emp_name:
                    prompt = build_employee_system_prompt(emp_dict)
                    display = emp_dict.get("name", skill_name)
                    return prompt, display
        except Exception:
            pass

    # 2. 从数据库查找匹配的技能（AiSkill 单技能匹配）
    if AiSkillRepository:
        try:
            all_skills = AiSkillRepository.get_all(enabled_only=True)
            for sk in all_skills:
                sk_dict = dict(sk) if hasattr(sk, 'keys') else sk
                sk_name = sk_dict.get("name", "").lower()
                if skill_name == sk_name:
                    prompt = (
                        f"你是 {sk_dict.get('name', skill_name)} 数字员工。\n"
                        f"技能描述：{sk_dict.get('description', '')}\n"
                        f"{sk_dict.get('prompt_template', '')}\n\n"
                    )
                    return prompt, sk_dict.get("name", skill_name)
        except Exception:
            pass

    # 3. 回退：内置硬编码技能（search / help / 通用兜底）
    skill_prompts = {
        "search": (
            "你是一个网络搜索数字员工。用户需要搜索互联网上的信息。\n"
            "请根据你的知识库尽力提供最新、最相关的信息，并给出参考来源的建议。\n"
            "请用条理清晰的方式组织回复，分点列出关键信息。"
        ),
        "help": (
            "请列出当前可用的数字员工列表：\n"
            "- @天气 <地点> — 查询天气信息\n"
            "- @音乐 <歌手/歌曲> — 音乐推荐与介绍\n"
            "- @西师妹 <内容> — 与西师妹 AI 伙伴聊天\n"
            "- @search 或 \\search <关键词> — 搜索网络信息\n"
            "用户输入 @help 即可查看此列表。"
        ),
    }

    for key, prompt in skill_prompts.items():
        if key == skill_name or key.lower() == skill_name:
            return prompt, key

    # 未知技能：给出友好提示
    unknown_prompt = (
        f"用户尝试调用名为「{skill_name}」的数字员工，但该技能尚未上线。\n"
        "请友好地告知用户：该数字员工正在开发中，敬请期待！\n"
        "并建议用户输入 @help 查看当前可用的数字员工列表。"
    )
    return unknown_prompt, skill_name


def _get_db_schema() -> str:
    """获取数据库表结构描述"""
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        schema_parts = []
        for t in tables:
            table_name = t["name"]
            cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            col_descs = [f"  {c['name']} ({c['type']})" for c in cols]
            schema_parts.append(f"表名: {table_name}\n" + "\n".join(col_descs))
        return "\n\n".join(schema_parts)
