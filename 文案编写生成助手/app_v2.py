# -*- coding: utf-8 -*-
"""
文案编写生成助手 V2.0 —— FastAPI Web版
技术栈: Python + FastAPI + .md Skill + LLM(qwen3.5-flash) + 原生HTML/CSS/JS
作者: BibeCodingUsers - 何心诚
功能: 与 V1.0 对齐 —— 四步工作流（开始→关键字→10个主题→3种大纲→逐章生成确认）
"""
import os
import time
import json
import asyncio
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

# -------------------------- 全局配置 --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SKILL_FILE = os.path.join(BASE_DIR, "skills", "WriteContent.md")

API_KEY = os.getenv("AIGC_API_KEY", "")
if not API_KEY:
    raise RuntimeError("请设置环境变量 AIGC_API_KEY，例如: set AIGC_API_KEY=你的密钥")
API_URL = "https://aigc-api.aitoolcore.com/api/v1"
MODEL_NAME = "qwen3.5-flash"

client = OpenAI(api_key=API_KEY, base_url=API_URL)

app = FastAPI(title="文案编写生成助手 V2.0", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------- 数据模型 --------------------------
class ChatRequest(BaseModel):
    """通用对话请求体 —— 消息列表 + 启用/禁用 skill"""
    messages: List[Dict[str, Any]] = Field(..., description="对话历史，[{role, content}]")
    use_skill: bool = Field(default=True, description="是否注入 .md Skill 作为 system prompt")
    stream: bool = Field(default=True, description="是否流式响应")
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)


class SkillInfo(BaseModel):
    name: str
    content: str


# -------------------------- 工具函数 --------------------------
def load_skill() -> str:
    """读取 .md Skill 定义"""
    if not os.path.exists(SKILL_FILE):
        return ""
    with open(SKILL_FILE, "r", encoding="utf-8") as f:
        return f.read()


def build_messages(req: ChatRequest) -> List[Dict[str, str]]:
    """根据请求构造发给大模型的消息列表"""
    msgs = []
    if req.use_skill:
        skill = load_skill()
        if skill:
            msgs.append({"role": "system", "content": skill})
    for m in req.messages:
        role = str(m.get("role", "user"))
        content = m.get("content", "")
        if content and role in ("system", "user", "assistant"):
            msgs.append({"role": role, "content": str(content)})
    return msgs


# -------------------------- 路由 --------------------------
@app.get("/")
def index():
    """首页 —— 返回精美 Web UI"""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="static/index.html not found")
    return FileResponse(index_path, media_type="text/html; charset=utf-8")


@app.get("/api/skill", response_model=SkillInfo)
def get_skill():
    """返回当前加载的 Skill 定义（前端可展示）"""
    return SkillInfo(name="WriteContent.md", content=load_skill())


@app.get("/api/info")
def get_info():
    """健康检查与版本信息"""
    return {
        "version": "2.0",
        "author": "BibeCodingUsers - 何心诚",
        "model": MODEL_NAME,
        "has_skill": bool(load_skill()),
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    对话接口：
    - stream=True → Server-Sent Events (SSE) 流式返回
    - stream=False → 一次性返回完整 JSON
    """
    messages = build_messages(req)
    if not messages:
        raise HTTPException(status_code=400, detail="messages 不可为空")

    try:
        if req.stream:
            def generate():
                stream = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    stream=True,
                    temperature=req.temperature,
                )
                full = ""
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            full += delta
                            data = json.dumps({
                                "delta": delta,
                                "full": full,
                                "done": False
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                data = json.dumps({
                    "delta": "",
                    "full": full,
                    "done": True
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream; charset=utf-8")
        else:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                stream=False,
                temperature=req.temperature,
            )
            content = resp.choices[0].message.content or ""
            return {"content": content, "model": resp.model, "usage": resp.usage.model_dump() if resp.usage else {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 请求失败：{str(e)}")


# 静态文件挂载（最后挂载，避免覆盖其他路由）
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# -------------------------- 启动入口 --------------------------
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("📝 文案编写生成助手 V2.0 启动")
    print("   作者: BibeCodingUsers - 何心诚")
    print(f"   模型: {MODEL_NAME}")
    print(f"   访问: http://127.0.0.1:10086/")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=10086, log_level="info")
