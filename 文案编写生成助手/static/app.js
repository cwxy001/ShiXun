/* ============================================================
   文案编写生成助手 · 交互逻辑
   - 流式对话 (SSE)
   - 简易 markdown 渲染（段落 / 代码块 / 行内代码 / 强调）
   - 自适应 textarea 高度
   ============================================================ */
(function () {
    "use strict";

    const $form      = document.getElementById("inputForm");
    const $input     = document.getElementById("inputBox");
    const $send      = document.getElementById("sendBtn");
    const $list      = document.getElementById("messageList");
    const $clear     = document.getElementById("clearBtn");
    const $progress  = document.getElementById("scrollProgress");
    const $topBtn   = document.getElementById("scrollTopBtn");

    let history     = [];   // 发送给模型的消息列表
    let isStreaming = false;

    // ============================================================
    // 渲染：简易 markdown → HTML
    // ============================================================
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function renderInline(text) {
        // 先转义
        let html = escapeHtml(text);

        // **bold**
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

        // *em* （注意：必须排除 ** 这种情况，上面已经处理）
        html = html.replace(/(^|[^*])\*([^*\s][^*]*?)\*/g, "$1<em>$2</em>");

        // `inline code`
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

        return html;
    }

    function renderMarkdown(raw) {
        if (!raw) return "";

        // 归一化换行
        const text = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();

        // 切分为块（按空行）。但先把 ``` 代码块整体提取出来，避免被段落切分破坏
        const blocks = [];
        const lines = text.split("\n");
        let i = 0;
        let inCode = false;
        let codeLang = "";
        let codeLines = [];

        while (i < lines.length) {
            const line = lines[i];

            // 代码块开始
            if (!inCode && line.trim().startsWith("```")) {
                inCode = true;
                codeLang = line.trim().slice(3).trim();
                codeLines = [];
                i++;
                continue;
            }
            // 代码块结束
            if (inCode && line.trim().startsWith("```")) {
                inCode = false;
                blocks.push({ type: "code", lang: codeLang, content: codeLines.join("\n") });
                i++;
                continue;
            }
            if (inCode) {
                codeLines.push(line);
                i++;
                continue;
            }

            // 普通段落：按空行分隔为一段
            if (line.trim() === "") { i++; continue; }
            let paraLines = [];
            while (i < lines.length && lines[i].trim() !== "" && !lines[i].trim().startsWith("```")) {
                paraLines.push(lines[i]);
                i++;
            }
            if (paraLines.length) {
                blocks.push({ type: "paragraph", content: paraLines.join("\n") });
            }
        }
        // 若代码块未闭合，兜底
        if (inCode && codeLines.length) {
            blocks.push({ type: "code", lang: codeLang, content: codeLines.join("\n") });
        }

        // 渲染块
        let html = "";
        for (const b of blocks) {
            if (b.type === "code") {
                html += `<pre><code>${escapeHtml(b.content)}</code></pre>`;
            } else {
                html += `<p>${renderInline(b.content).replace(/\n/g, "<br />")}</p>`;
            }
        }
        return html;
    }

    // ============================================================
    // DOM：插入 / 更新消息
    // ============================================================
    function createMsg(role, rawText, typing = false) {
        const article = document.createElement("article");
        article.className = "msg " + role;

        const avatar = document.createElement("div");
        avatar.className = "msg-avatar";
        avatar.textContent = role === "user" ? "我" : "西";

        const body = document.createElement("div");
        body.className = "msg-content";
        body.innerHTML = renderMarkdown(rawText);
        if (typing) body.classList.add("typing");

        article.appendChild(avatar);
        article.appendChild(body);
        $list.appendChild(article);
        $list.scrollTop = $list.scrollHeight;
        return { article, body };
    }

    function updateMsg(body, rawText, isDone) {
        body.innerHTML = renderMarkdown(rawText);
        if (isDone) body.classList.remove("typing");
        else body.classList.add("typing");
        $list.scrollTop = $list.scrollHeight;
    }

    // ============================================================
    // textarea 自适应高度
    // ============================================================
    function autoResize() {
        $input.style.height = "auto";
        $input.style.height = Math.min($input.scrollHeight, 180) + "px";
    }
    $input.addEventListener("input", autoResize);

    $input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            $form.requestSubmit();
        }
    });

    // ============================================================
    // 发送消息
    // ============================================================
    async function send() {
        const text = $input.value.trim();
        if (!text || isStreaming) return;

        isStreaming = true;
        $send.disabled = true;
        $input.value = "";
        autoResize();

        createMsg("user", text);
        history.push({ role: "user", content: text });

        // 先放一个「思考中」占位，等首字节到达再替换
        const { body } = createMsg("assistant", "…", true);

        try {
            const resp = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    messages: history,
                    use_skill: true,
                    stream: true,
                    temperature: 0.85,
                }),
            });

            if (!resp.ok || !resp.body) {
                updateMsg(body, "⚠️ 请求失败（" + resp.status + "），请稍后再试。", true);
                history.pop();
                return;
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";
            let fullText = "";
            let firstChunk = true;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                // SSE：每条事件以 "data: ..." 开头，空行分隔
                const lines = buffer.split(/\r?\n/);
                buffer = lines.pop(); // 保留不完整段

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || !trimmed.startsWith("data:")) continue;
                    const payload = trimmed.slice(5).trim();
                    if (!payload) continue;
                    try {
                        const obj = JSON.parse(payload);
                        if (typeof obj.full === "string") {
                            fullText = obj.full;
                            // 首字节到达时清除占位符动画
                            if (firstChunk) { firstChunk = false; }
                            updateMsg(body, fullText, !!obj.done);
                        }
                    } catch (_) { /* 非 JSON 事件忽略 */ }
                }
            }
            // 确保最后一次渲染不带 typing 光标
            updateMsg(body, fullText, true);

            // 保留完整回复（仅保留实际文本，减少 token 浪费）
            if (fullText) history.push({ role: "assistant", content: fullText });
            else history.pop(); // 空回复则不保留

        } catch (err) {
            updateMsg(body, "❌ 网络异常：" + (err.message || err), true);
            history.pop();
        } finally {
            isStreaming = false;
            $send.disabled = false;
            $input.focus();
        }
    }

    $form.addEventListener("submit", (e) => {
        e.preventDefault();
        send();
    });

    // ============================================================
    // 清空
    // ============================================================
    $clear.addEventListener("click", () => {
        if (!confirm("确认清空当前对话？")) return;
        history = [];
        $list.innerHTML = "";
        const welcome =
            "对话已清空 ✨\n\n" +
            "输入 **开始** 重新启动四步流程，或直接告诉我你的关键词（例如：*四川 南充 西华师范大学 软件工程*）。";
        createMsg("assistant", welcome, false);
    });

    // ============================================================
    // 滚动：进度条 + 回到顶部按钮
    // ============================================================
    function updateScrollUI() {
        const scrollTop = $list.scrollTop;
        const max = $list.scrollHeight - $list.clientHeight;
        const p = max > 0 ? (scrollTop / max) * 100 : 0;

        // 顶部进度条
        if ($progress) $progress.style.setProperty("--p", p.toFixed(1) + "%");

        // 回到顶部按钮：滚动超过 300px 时显示
        if ($topBtn) {
            if (scrollTop > 300) $topBtn.classList.add("show");
            else $topBtn.classList.remove("show");
        }
    }
    $list.addEventListener("scroll", updateScrollUI, { passive: true });

    if ($topBtn) {
        $topBtn.addEventListener("click", () => {
            $list.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    // 内容有变化（新消息到达）时也刷新一次
    const _ro = new ResizeObserver(updateScrollUI);
    _ro.observe($list);
    window.addEventListener("resize", updateScrollUI);

    // 初始化
    autoResize();
    updateScrollUI();
    $input.focus();
})();
