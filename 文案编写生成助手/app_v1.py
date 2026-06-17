import os
import gradio as gr
from openai import OpenAI

# -------------------------- 全局接口配置 --------------------------
api_key = os.getenv("AIGC_API_KEY", "")
if not api_key:
    raise RuntimeError("请设置环境变量 AIGC_API_KEY，例如: set AIGC_API_KEY=你的密钥")
api_url = "https://aigc-api.aitoolcore.com/api/v1"
model_name = "qwen3.5-flash"
skils_file_path = "./skills/WriteContent.md"

# 初始化大模型请求客户端
client = OpenAI(
    api_key=api_key,
    base_url=api_url
)

# -------------------------- 读取角色提示词文件函数 --------------------------
def read_skills_by(filepath):
    """读取本地md技能提示文件，返回完整文本"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

# -------------------------- 流式对话核心函数（生成器） --------------------------
def chat(message, history, system_prompt):
    """
    :param message: 当前用户输入文本
    :param history: gradio 存储的历史对话列表
    :param system_prompt: 全局系统角色提示词
    :yield: 逐段流式返回AI拼接后的完整回复
    """
    messages = []
    # 插入系统角色设定
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    # 解析Gradio嵌套格式历史对话，转换为大模型标准消息格式
    for h in history:
        role = h.get("role")
        content_list = h.get("content", [])
        # 兼容多层content嵌套结构，安全提取文本
        text = content_list[0].get("text", "") if content_list else ""
        messages.append({"role": role, "content": text})
    
    # 追加当前用户提问
    messages.append({"role": "user", "content": message})

    # 发起大模型流式SSE请求
    stream = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True  # 开启流式分段响应
    )

    reply = ""
    # 多层判空防御，避免空chunk、空choices导致程序崩溃
    for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            choice = chunk.choices[0]
            if choice.delta and choice.delta.content:
                delta_content = choice.delta.content
                if delta_content is not None:
                    reply += delta_content
                    yield reply

# -------------------------- 程序入口、Gradio网页界面 --------------------------
if __name__ == "__main__":
    # 读取预设角色文案
    skillContent = read_skills_by(skils_file_path)
    
    # 搭建网页UI
    with gr.Blocks(title="文案编写生成助手 V1.0") as demo:
        gr.Markdown("## 文案编写生成助手 V1.0")
        gr.Markdown("**作者：** BibeCodingUsers - 何心诚 ｜ **技术栈：** Python + Gradio + .md Skill + LLM(qwen3.5-flash)")
        # 全局状态存储系统提示词，传递给对话函数
        system = gr.State(skillContent)
        # 聊天交互组件，绑定流式chat函数
        gr.ChatInterface(fn=chat, additional_inputs=[system])
    
    # 启动web服务，固定端口10086
    demo.launch(server_port=10086, share=False)
