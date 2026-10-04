(function () {
  "use strict";

  const MIN_CHARS = 10;
  const LEVELS = {
    danger: { text: "Nguy hiểm: rất có thể là lừa đảo", tone: "bad" },
    suspicious: { text: "Đáng ngờ: cần kiểm tra kỹ", tone: "warn" },
    low: { text: "Chưa thấy dấu hiệu lừa đảo rõ ràng", tone: "good" },
  };

  const $ = (id) => document.getElementById(id);
  const form = $("scam-form");
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

  function setBar(id, fraction, tone) {
    const fill = $(id);
    fill.style.width = `${(Math.min(Math.max(fraction, 0), 1) * 100).toFixed(1)}%`;
    fill.parentElement.className = `bar ${tone}`;
  }

  function fillList(list, items) {
    list.replaceChildren(...items);
  }

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
    liveState.textContent = "Đang kiểm tra…";
    try {
      const response = await fetch("/api/scam", {
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
      liveState.textContent = `Đã kiểm tra lúc ${new Date().toLocaleTimeString()} · ${Math.round(data.latency_ms)} ms`;
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
    const level = LEVELS[data.verdict];
    $("scam-verdict").className = `panel scam-verdict ${data.verdict}`;
    $("scam-level").textContent = level.text;
    $("scam-risk").textContent = pct(data.risk);
    setBar("scam-risk-bar", data.risk, level.tone);

    const signals = data.signals.map((s) => {
      const item = el("li", "signal");
      item.append(el("span", "", s.label));
      if (s.match) item.append(el("q", "signal-match", s.match));
      return item;
    });
    if (data.protective) {
      signals.push(el("li", "signal protective", "Có lời nhắc không chia sẻ mã, thường gặp ở tin nhắn thật của ngân hàng (giảm rủi ro)"));
    }
    if (!signals.length) signals.push(el("li", "muted", "Không tìm thấy dấu hiệu quen thuộc."));
    fillList($("scam-signals"), signals);
    fillList($("scam-advice"), data.advice.map((text) => el("li", "", text)));

    $("laya-score").textContent = pct(data.laya_score);
    setBar("laya-bar", data.laya_score, "muted");
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
