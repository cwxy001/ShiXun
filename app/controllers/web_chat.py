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
except ImportError:
    DigitalEmployeeRepository = None
    AiSkillRepository = None


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

        # @xxx 数字员工调用检测
        skill_name, skill_args, is_skill = _parse_at_command(user_message)
        resolved_name = skill_name
        cached_skill_prompt = ""
        search_result = None  # 网络搜索结果
        if is_skill:
            cached_skill_prompt, resolved_name = _get_skill_prompt(skill_name, skill_args)
            # 如果是搜索类技能，执行实际网络搜索
            if skill_name.lower() in ("search", "搜索"):
                search_result = _execute_web_search(skill_args or user_message)

        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        try:
            # 如果是 @xxx 数字员工调用，先发送通知事件（含员工信息）
            if is_skill:
                emp_info = _lookup_employee(skill_name)
                extra = ""
                if search_result:
                    rc = search_result.get("result_count", 0)
                    source = search_result.get("source", "live")
                    extra = f" | 已检索到 {rc} 条结果 ({source})"
                skill_start = json.dumps({
                    "type": "skill_start",
                    "skill": resolved_name,
                    "display_name": emp_info.get("display_name", resolved_name),
                    "avatar": emp_info.get("avatar", ""),
                    "role": emp_info.get("role", ""),
                    "content": f"正在调用网络搜索: {skill_args}{extra}",
                    "search_info": search_result,
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

            # 系统提示词：@xxx 数字员工 > SQL > 自定义 > 默认
            if is_skill:
                # 搜索类技能：如有实时搜索结果，注入结果；否则用静态 prompt
                if search_result and search_result.get("prompt_fragment"):
                    messages.append({
                        "role": "system",
                        "content": (
                            "你是一个网络搜索助手。用户正在进行网络信息检索。\n"
                            "你的任务是基于以下搜索结果，为用户提供准确、全面的回答。\n\n"
                            + search_result["prompt_fragment"]
                        )
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
    """获取启用的数字员工及其技能列表"""
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
                    "trigger": emp_dict.get("trigger_word", emp_dict.get("name", "").lower()),
                    "avatar": emp_dict.get("avatar", ""),
                    "role": emp_dict.get("role_desc", ""),
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


def _lookup_employee(skill_name: str) -> dict:
    """查找数字员工的显示信息"""
    skill_lower = skill_name.lower()
    if DigitalEmployeeRepository:
        try:
            employees = DigitalEmployeeRepository.get_all(enabled_only=True)
            for emp in employees:
                emp_dict = dict(emp) if hasattr(emp, 'keys') else emp
                if skill_lower in (emp_dict.get("name", "").lower(), emp_dict.get("trigger_word", "").lower()):
                    return {
                        "display_name": emp_dict.get("name", skill_name),
                        "avatar": emp_dict.get("avatar", ""),
                        "role": emp_dict.get("role_desc", ""),
                    }
        except Exception:
            pass
    return {"display_name": skill_name, "avatar": "", "role": ""}


def _get_skill_prompt(skill_name: str, skill_args: str) -> tuple:
    """根据数字员工技能名称，返回对应的系统提示词。
    优先从数据库查询数字员工和技能配置。
    返回 (prompt, display_name)"""

    # 1. 从数据库查找匹配的数字员工
    if DigitalEmployeeRepository:
        try:
            employees = DigitalEmployeeRepository.get_all(enabled_only=True)
            for emp in employees:
                emp_dict = dict(emp) if hasattr(emp, 'keys') else emp
                emp_name = emp_dict.get("name", "").lower()
                trigger = emp_dict.get("trigger_word", "").lower()
                # 匹配名称或触发词
                if skill_name in (emp_name, trigger):
                    # 获取绑定的技能 Prompt
                    skills_json = emp_dict.get("skills", "[]")
                    try:
                        bound_skills = json.loads(skills_json) if isinstance(skills_json, str) else skills_json
                    except (json.JSONDecodeError, TypeError):
                        bound_skills = []
                    # 查找技能详细 Prompt
                    skill_prompt_text = ""
                    if AiSkillRepository and bound_skills:
                        for sid in bound_skills:
                            try:
                                skill = AiSkillRepository.get_by_id(int(sid))
                                if skill:
                                    skill_prompt_text += f"\n【技能：{skill['name']}】{skill.get('prompt_template', '')}"
                            except (ValueError, Exception):
                                pass

                    welcome = emp_dict.get("welcome_message", "")
                    role = emp_dict.get("role_desc", "")
                    system_prompt = (
                        f"你是 {emp_dict.get('name', skill_name)}，一个 AI 数字员工。\n"
                        f"角色定位：{role}\n"
                    )
                    if welcome:
                        system_prompt += f"欢迎语风格参考：{welcome}\n"
                    if skill_prompt_text:
                        system_prompt += f"能力范围：{skill_prompt_text}\n"
                    system_prompt += f"\n用户对你说：{skill_args}\n"
                    system_prompt += f"请以「{emp_dict.get('name', skill_name)}」的身份和风格回复，保持友好、专业。"
                    return system_prompt, emp_dict.get("name", skill_name)
        except Exception:
            pass

    # 2. 从数据库查找匹配的技能（AiSkill）
    if AiSkillRepository:
        try:
            all_skills = AiSkillRepository.get_all(enabled_only=True)
            for sk in all_skills:
                sk_dict = dict(sk) if hasattr(sk, 'keys') else sk
                sk_name = sk_dict.get("name", "").lower()
                keywords = sk_dict.get("trigger_keywords", "")
                # 匹配技能名称或触发关键词
                if skill_name == sk_name or skill_name in (keywords or "").split(","):
                    prompt = sk_dict.get("prompt_template", "")
                    system_prompt = (
                        f"你是 {sk_dict.get('name', skill_name)} 数字员工。\n"
                        f"技能描述：{sk_dict.get('description', '')}\n"
                        f"{prompt}\n\n"
                        f"用户输入：{skill_args}\n"
                    )
                    return system_prompt, sk_dict.get("name", skill_name)
        except Exception:
            pass

    # 3. 回退：内置硬编码技能
    skill_prompts = {
        "天气": (
            "你是一个天气查询数字员工。用户询问天气情况。\n"
            "请根据你的知识回答天气相关问题，包括温度、湿度、风力、穿衣建议等。\n"
            f"用户查询：{skill_args}\n"
            "请用友好、专业的语气回答。"
        ),
        "音乐": (
            "你是一个音乐推荐数字员工。用户询问音乐相关的内容。\n"
            "请根据你的知识推荐歌曲、专辑、歌手，介绍音乐风格、背景等。\n"
            f"用户需求：{skill_args}\n"
            "请用热情、有品味的语气回答。"
        ),
        "西师妹": (
            "你是西师妹，一个活泼可爱、幽默风趣的 AI 数字员工。\n"
            "你喜欢用轻松俏皮的语气和人聊天，偶尔会开个玩笑，但也能认真回答问题。\n"
            "你擅长 Python 编程、数据分析、AI 技术等话题。\n"
            f"对方对你说：{skill_args}\n"
            "请以「西师妹」的身份和风格回复。"
        ),
        "search": (
            "你是一个网络搜索数字员工。用户需要搜索互联网上的信息。\n"
            "请根据你的知识库尽力提供最新、最相关的信息，并给出参考来源的建议。\n"
            f"搜索内容：{skill_args}\n"
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
