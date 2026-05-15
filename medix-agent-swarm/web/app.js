/**
 * MediX Web Chat UI
 */
(function () {
  const API = "";

  const $ = (sel) => document.querySelector(sel);
  const messagesEl = $("#messages");
  const welcomeCard = $("#welcomeCard");
  const messagesWrap = $("#messagesWrap");
  const form = $("#chatForm");
  const input = $("#userInput");
  const sendBtn = $("#sendBtn");
  const sessionDisplay = $("#sessionDisplay");
  const statusPill = $("#statusPill");
  const statusText = $("#statusText");
  const swarmToggle = $("#swarmToggle");
  const btnNewChat = $("#btnNewChat");
  const tplThinking = $("#tplThinking");

  let sessionId = null;
  let busy = false;

  const THINKING_LINES = [
    "正在检索知识库与记忆…",
    "分析症状与临床指南…",
    "多智能体协作推理中…",
    "整合循证医学建议…",
    "生成个性化健康参考…",
  ];

  if (typeof marked !== "undefined") {
    marked.setOptions({ breaks: true, gfm: true });
  }

  function setStatus(text, mode) {
    statusText.textContent = text;
    statusPill.classList.remove("busy", "error");
    if (mode) statusPill.classList.add(mode);
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesWrap.scrollTop = messagesWrap.scrollHeight;
    });
  }

  function hideWelcome() {
    if (welcomeCard && !welcomeCard.classList.contains("hidden")) {
      welcomeCard.classList.add("hidden");
    }
  }

  function renderMarkdown(text) {
    if (typeof marked !== "undefined") {
      return marked.parse(text || "");
    }
    return (text || "").replace(/</g, "&lt;").replace(/\n/g, "<br>");
  }

  function appendUserMessage(text) {
    hideWelcome();
    const row = document.createElement("div");
    row.className = "msg-row user";
    row.innerHTML = `
      <div class="avatar user-av">您</div>
      <div class="bubble user-bubble">${escapeHtml(text)}</div>
    `;
    messagesEl.appendChild(row);
    scrollToBottom();
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML.replace(/\n/g, "<br>");
  }

  function showThinking() {
    const node = tplThinking.content.cloneNode(true);
    const row = node.querySelector(".thinking-row");
    row.id = "thinkingIndicator";
    const sub = row.querySelector("[data-thinking-text]");
    let idx = 0;
    const timer = setInterval(() => {
      if (!document.getElementById("thinkingIndicator")) {
        clearInterval(timer);
        return;
      }
      idx = (idx + 1) % THINKING_LINES.length;
      if (sub) sub.textContent = THINKING_LINES[idx];
    }, 2200);
    row.dataset.timerId = String(timer);
    messagesEl.appendChild(row);
    scrollToBottom();
    return row;
  }

  function removeThinking() {
    const el = document.getElementById("thinkingIndicator");
    if (el) {
      const tid = el.dataset.timerId;
      if (tid) clearInterval(Number(tid));
      el.remove();
    }
  }

  function appendAssistantMessage(data) {
    hideWelcome();
    const modeLabel = data.swarm_enabled
      ? `群体智能 · ${(data.agents_involved || []).length} Agent`
      : "单 Agent 模式";

    let suggestionsHtml = "";
    if (data.suggestions && data.suggestions.length) {
      const items = data.suggestions
        .map((s) => `<li>${escapeHtml(s)}</li>`)
        .join("");
      suggestionsHtml = `
        <div class="suggestions">
          <div class="suggestions-title">核心建议</div>
          <ol>${items}</ol>
        </div>`;
    }

    const row = document.createElement("div");
    row.className = "msg-row assistant";
    row.innerHTML = `
      <div class="avatar assistant-av">
        <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2a3 3 0 0 1 3 3v1h2a2 2 0 0 1 2 2v2h-1v8a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4V10H5V8a2 2 0 0 1 2-2h2V5a3 3 0 0 1 3-3z"/></svg>
      </div>
      <div class="bubble assistant-bubble">
        <div class="md-content">${renderMarkdown(data.answer)}</div>
        ${suggestionsHtml}
        ${data.disclaimer ? `<p class="disclaimer">${escapeHtml(data.disclaimer)}</p>` : ""}
        <div class="msg-meta">
          <span class="tag">${escapeHtml(modeLabel)}</span>
          <span>耗时 ${data.execution_time_sec}s</span>
          ${data.timeout_occurred ? '<span class="tag" style="color:#fbbf24">部分超时</span>' : ""}
        </div>
      </div>
    `;
    messagesEl.appendChild(row);
    scrollToBottom();
  }

  function appendErrorMessage(msg) {
    hideWelcome();
    const row = document.createElement("div");
    row.className = "msg-row assistant";
    row.innerHTML = `
      <div class="avatar assistant-av">!</div>
      <div class="bubble assistant-bubble" style="border-color: rgba(248,113,113,0.4)">
        <p>抱歉，处理时出现问题：</p>
        <p><strong>${escapeHtml(msg)}</strong></p>
        <p class="disclaimer">请确认后端已启动，且 Redis / PostgreSQL / API Key 配置正确。</p>
      </div>
    `;
    messagesEl.appendChild(row);
    scrollToBottom();
  }

  function setBusy(on) {
    busy = on;
    sendBtn.disabled = on;
    sendBtn.classList.toggle("loading", on);
    input.disabled = on;
    setStatus(on ? "临床分析中…" : "系统就绪", on ? "busy" : null);
  }

  async function api(path, options) {
    const res = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    const data = await api("/api/session", { method: "POST" });
    sessionId = data.session_id;
    sessionDisplay.textContent = sessionId;
    return sessionId;
  }

  async function newSession() {
    sessionId = null;
    messagesEl.innerHTML = "";
    welcomeCard.classList.remove("hidden");
    const data = await api("/api/session", { method: "POST" });
    sessionId = data.session_id;
    sessionDisplay.textContent = sessionId;
    setStatus("新会话已创建", null);
    input.focus();
  }

  async function sendMessage(text) {
    const message = (text || input.value).trim();
    if (!message || busy) return;

    await ensureSession();
    appendUserMessage(message);
    input.value = "";
    autoResizeInput();

    setBusy(true);
    showThinking();

    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          message,
          session_id: sessionId,
          enable_swarm: swarmToggle.checked,
        }),
      });
      sessionId = data.session_id;
      sessionDisplay.textContent = sessionId;
      removeThinking();
      appendAssistantMessage(data);
      setStatus("分析完成", null);
    } catch (e) {
      removeThinking();
      appendErrorMessage(e.message || String(e));
      setStatus("请求失败", "error");
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  function autoResizeInput() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener("input", autoResizeInput);

  document.querySelectorAll(".quick-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) {
        input.value = prompt;
        autoResizeInput();
        sendMessage(prompt);
      }
    });
  });

  btnNewChat.addEventListener("click", () => {
    if (busy) return;
    newSession().catch((e) => setStatus(e.message, "error"));
  });

  ensureSession()
    .then(() => setStatus("系统就绪", null))
    .catch(() => setStatus("等待后端连接", "error"));

  input.focus();
})();
