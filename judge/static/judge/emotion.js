(function () {
  "use strict";

  const MIN_CHARS = 3;
  // Same order and names as judge/emotion.py, so the bars exist before the first result.
  const EMOTIONS = [
    ["happy", "😄 Vui vẻ"], ["grateful", "🙏 Biết ơn"], ["love", "❤️ Yêu thương"], ["angry", "😠 Tức giận"],
    ["sad", "😢 Buồn"], ["worried", "😟 Lo lắng"], ["surprised", "😮 Ngạc nhiên"], ["neutral", "😐 Trung tính"],
  ];
  const SENTIMENTS = [["positive", "Tích cực", "good"], ["neutral", "Trung tính", "muted"], ["negative", "Tiêu cực", "bad"]];
  const SOURCE = {
    words: "dựa trên AI và từ ngữ cảm xúc",
    neutral: "không thấy từ ngữ cảm xúc, AI đánh giá trung tính",
    laya: "dựa trên AI (không thấy từ ngữ cảm xúc quen thuộc)",
  };

  const $ = (id) => document.getElementById(id);
  const form = $("check-form");
  const bodyInput = $("body");
  const errorBox = $("form-error");
  const liveState = $("live-state");

  const pct = (p) => `${Math.round(p * 100)}%`;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function createMeter(label, parent) {
    const root = el("div", "m");
    const top = el("div", "m-top");
    const key = el("span", "k", label);
    const value = el("span", "v", "—");
    top.append(key, value);
    const bar = el("div", "bar muted");
    const fill = el("span");
    fill.style.width = "0%";
    bar.append(fill);
    root.append(top, bar);
    parent.append(root);
    return { key, value, bar, fill };
  }

  function setMeter(m, p, tone) {
    m.fill.style.width = `${(Math.min(Math.max(p, 0), 1) * 100).toFixed(1)}%`;
    m.value.textContent = pct(p);
    m.bar.className = `bar ${tone}`;
  }

  // ---------- bars are drawn once; results only change their values ----------

  const emotionMeters = Object.fromEntries(EMOTIONS.map(([id, label]) => [id, createMeter(label, $("emotion-bars"))]));
  const sentimentMeters = Object.fromEntries(SENTIMENTS.map(([id, label]) => [id, createMeter(label, $("sentiment-bars"))]));

  // ---------- one request at a time; text typed meanwhile is sent when it finishes ----------

  let running = false;
  let queued = false;

  async function runCheck() {
    if (running) {
      queued = true;
      return;
    }
    errorBox.textContent = "";
    const body = bodyInput.value;
    if (body.trim().length < MIN_CHARS) {
      liveState.textContent = "Nhập thêm nội dung…";
      return;
    }

    running = true;
    $("busy").classList.add("on");
    liveState.textContent = "Đang phân tích…";
    try {
      const response = await fetch("/api/emotion", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector("input[name=csrfmiddlewaretoken]").value,
        },
        body: JSON.stringify({ body }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Lỗi máy chủ ${response.status}`);
      render(data);
      liveState.textContent = `Đã phân tích lúc ${new Date().toLocaleTimeString()} · ${Math.round(data.latency_ms)} ms`;
      refreshStatus();
    } catch (err) {
      errorBox.textContent = err.message;
      liveState.textContent = "Lỗi";
    } finally {
      running = false;
      if (queued) {
        queued = false;
        runCheck();
      } else {
        $("busy").classList.remove("on");
      }
    }
  }

  // Wait until typing pauses before asking the server, so a sentence is one request, not one per key.
  const TYPING_PAUSE_MS = 400;
  let typingTimer = null;
  function afterTypingPause(run) {
    return () => {
      clearTimeout(typingTimer);
      typingTimer = setTimeout(run, TYPING_PAUSE_MS);
    };
  }

  form.addEventListener("submit", (event) => event.preventDefault());
  bodyInput.addEventListener("input", afterTypingPause(runCheck));

  // ---------- rendering ----------

  function render(data) {
    const top = data.emotions[0];
    $("emotion-main").className = `panel emotion-main emotion-${top.id}`;
    $("emotion-emoji").textContent = top.emoji;
    $("emotion-label").textContent = top.label;
    $("emotion-sub").textContent = `Độ tin cậy ${pct(top.p)} · ${SOURCE[data.source]}`;

    const sentiment = SENTIMENTS.find(([id]) => id === data.sentiment);
    const pill = $("sentiment-pill");
    pill.hidden = false;
    pill.className = `pill pill-${sentiment[2]}`;
    pill.textContent = sentiment[1];

    for (const e of data.emotions) {
      const m = emotionMeters[e.id];
      setMeter(m, e.p, e.id === top.id ? "" : "muted");
      m.key.classList.toggle("strong", e.id === top.id);
    }
    for (const s of data.sentiments) {
      setMeter(sentimentMeters[s.id], s.p, SENTIMENTS.find(([id]) => id === s.id)[2]);
    }

    const items = data.words.map((w) => {
      const item = el("li");
      item.append(el("span", "", w.label));
      item.append(el("q", "signal-match", w.words.join(", ")));
      return item;
    });
    if (!items.length) items.push(el("li", "muted", "Không tìm thấy từ ngữ cảm xúc quen thuộc."));
    $("emotion-words").replaceChildren(...items);
  }

  // ---------- model status ----------

  // Fields stay disabled (and drawn as skeletons by .is-loading) until the model is ready.
  function setModelLoading(loading) {
    form.classList.toggle("is-loading", loading);
    form.setAttribute("aria-busy", String(loading));
    form.querySelectorAll("input, textarea, select").forEach((field) => (field.disabled = loading));
  }
  setModelLoading(true);

  async function refreshStatus() {
    const pill = $("model-status");
    try {
      const data = await (await fetch("/api/status")).json();
      if (Object.keys(data.loaded).length) {
        pill.className = "pill pill-good";
        pill.textContent = "Model ready";
        setModelLoading(false);
        return true;
      }
      pill.className = "pill pill-warn";
      pill.textContent = "Loading model…";
    } catch {
      pill.className = "pill pill-bad";
      pill.textContent = "Server unreachable";
    }
    return false;
  }

  (async function pollUntilLoaded() {
    if (!(await refreshStatus())) setTimeout(pollUntilLoaded, 2000);
  })();
})();
