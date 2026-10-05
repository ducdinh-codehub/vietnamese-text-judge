(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const CAN_MODERATE = window.LIVE.canModerate;
  const POLL_MS = 1000;
  const form = $("chat-form");
  const chatList = $("chat-list");
  const csrf = () => form.querySelector("input[name=csrfmiddlewaretoken]").value;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Per-viewer conveniences only; the page works the same when storage is blocked.
  const store = {
    get(key, fallback) {
      try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, value); } catch { /* ignore */ }
    },
  };

  // Same name, same colour, like Twitch.
  function nameColor(name) {
    let hash = 0;
    for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
    return `hsl(${hash % 360} 65% var(--name-l, 45%))`;
  }
  if (matchMedia("(prefers-color-scheme: dark)").matches) document.documentElement.style.setProperty("--name-l", "68%");

  async function postJSON(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Lỗi máy chủ ${response.status}`);
    return data;
  }

  // ---------- chat rendering ----------

  const rendered = new Map(); // comment id -> <li>
  const showHidden = $("show-hidden");
  showHidden.checked = store.get("live.showHidden", CAN_MODERATE ? "1" : "0") === "1";
  chatList.classList.toggle("show-hidden", showHidden.checked);

  function renderComment(c) {
    const li = el("li", `msg kind-${c.kind}`);
    li.dataset.id = c.id;
    li.dataset.visible = c.visible;

    if (!c.visible && !CAN_MODERATE) {
      li.classList.add("removed");
      li.textContent = "<Tin nhắn có chứa nội dung không phù hợp/tin nhắn spam>";
      return li;
    }

    const author = el("span", "msg-author", c.author);
    author.style.color = nameColor(c.author);
    li.append(author, el("span", "msg-text", c.text));

    if (!c.visible) {
      li.classList.add("hidden-mod");
      li.append(el("span", "msg-badge", `${c.emoji} ${c.label} · đã ẩn`));
      const why = c.source === "laya" ? `Laya: tiêu cực ${Math.round(c.laya_negative * 100)}%` : `“${c.match}”`;
      const reason = el("span", "msg-reason", `Lý do: ${why}`);
      const restore = el("button", "btn btn-sm", "Hiện lại");
      restore.type = "button";
      restore.addEventListener("click", () => moderate(c.id, "restore"));
      reason.append(restore);
      li.append(reason);
    } else if (c.queued || c.kind === "host") {
      li.classList.toggle("queued", c.queued);
      li.append(el("span", "msg-badge", `${c.emoji} ${c.label}`));
    }
    return li;
  }

  function applyHiddenFilter(li) {
    li.hidden = li.dataset.visible === "false" && !showHidden.checked;
  }

  // Stay pinned to the newest message unless the viewer scrolled up to read.
  let pinned = true;
  chatList.addEventListener("scroll", () => {
    pinned = chatList.scrollHeight - chatList.scrollTop - chatList.clientHeight < 40;
    if (pinned) $("chat-resume").hidden = true;
  });
  $("chat-resume").addEventListener("click", () => {
    chatList.scrollTop = chatList.scrollHeight;
    $("chat-resume").hidden = true;
  });
  function afterAppend() {
    while (chatList.children.length > 300) {
      const old = chatList.firstElementChild;
      rendered.delete(Number(old.dataset.id));
      old.remove();
    }
    if (pinned) chatList.scrollTop = chatList.scrollHeight;
    else $("chat-resume").hidden = false;
  }

  function upsert(c) {
    const li = renderComment(c);
    applyHiddenFilter(li);
    const existing = rendered.get(c.id);
    if (existing) existing.replaceWith(li);
    else chatList.append(li);
    rendered.set(c.id, li);
    return !existing;
  }

  showHidden.addEventListener("change", () => {
    store.set("live.showHidden", showHidden.checked ? "1" : "0");
    rendered.forEach(applyHiddenFilter);
    if (pinned) chatList.scrollTop = chatList.scrollHeight;
  });

  async function moderate(id, action) {
    try {
      upsert(await postJSON(`/api/live/queue/${id}`, { action }));
    } catch (err) {
      $("chat-error").textContent = err.message;
    }
  }

  // ---------- polling the shared chat ----------

  let lastId = 0;
  async function poll() {
    try {
      const response = await fetch(`/api/live/comments?after=${lastId}`);
      const data = await response.json();
      // Someone started over: everything on screen is gone from the server.
      const oldest = data.stats.oldest;
      const shown = rendered.size ? Math.min(...rendered.keys()) : null;
      if (shown !== null && (oldest === null || oldest > shown)) clearChat();
      let added = false;
      for (const c of data.comments) {
        lastId = Math.max(lastId, c.id);
        added = upsert(c) || added;
      }
      if (added) afterAppend();
      $("stat-queued").textContent = data.stats.queued;
      $("stat-hidden").textContent = data.stats.hidden;
      if ($("queue-count")) $("queue-count").textContent = data.stats.queued;
    } catch {
      /* the next poll retries */
    }
    setTimeout(poll, POLL_MS);
  }
  poll();

  // ---------- sending ----------

  const authorInput = $("chat-author");
  const textInput = $("chat-text");
  authorInput.value = store.get("live.author", "");
  authorInput.addEventListener("change", () => store.set("live.author", authorInput.value.trim()));

  async function send(author, text, asViewer = false) {
    return postJSON("/api/live/post", { author, text, as_viewer: asViewer });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    $("chat-error").textContent = "";
    const text = textInput.value.trim();
    if (!text) return;
    const author = authorInput.value.trim() || "Khách";
    textInput.value = "";

    // Show it straight away, greyed out, while Laya checks it.
    const pending = el("li", "msg pending");
    const name = el("span", "msg-author", author);
    name.style.color = nameColor(author);
    pending.append(name, el("span", "msg-text", text), el("span", "msg-reason", "Đang kiểm tra…"));
    chatList.append(pending);
    afterAppend();

    try {
      const c = await send(author, text);
      // The poll may already have drawn it; otherwise draw it now and let the poll update it.
      if (rendered.has(c.id)) {
        pending.remove();
      } else {
        const li = renderComment(c);
        applyHiddenFilter(li);
        pending.replaceWith(li);
        rendered.set(c.id, li);
      }
      if (!c.visible) {
        // Viewers are not told why; moderators see the reason on the message itself.
        const notice = el("li", "msg msg-notice",
          "Tin nhắn của bạn đã được chuyển cho shop xem trước, chưa hiện trong trò chuyện.");
        chatList.append(notice);
        afterAppend();
      }
    } catch (err) {
      pending.remove();
      textInput.value = text;
      $("chat-error").textContent = err.message;
    }
  });

  // ---------- simulated audience ----------

  const NAMES = ["Lan Anh", "minhthu99", "Hoàng Nam", "bé_Na", "Tuấn Kiệt", "Thảo Vy", "cuong.dt", "Mai Hương",
    "Ngọc Trâm", "phuong_linh", "Quốc Bảo", "Hà My", "anhduc.88", "Kim Ngân", "Thanh Tâm", "trangnguyen"];
  const LINES = [
    "chốt đơn 2 cái áo trắng size M nha shop", "lay 1 cai mau den sdt 0912345678", "em lấy 3 hộp ạ", "chot 1",
    "ib em nha shop", "c ơi để cho e 1 bộ màu be", "Mình mua 2 chai nhé", "chốt cho chị cái váy đỏ",
    "giá bao nhiêu vậy shop", "cai nay bn tien", "áo này nhiêu ạ", "cho xin giá set này", "set này bnh vậy c",
    "còn size L không shop", "có ship cod không ạ", "chất vải gì vậy chị", "freeship ko shop",
    "e cao 1m6 nặng 50kg mặc size gì ạ", "đổi size được không shop", "váy có màu xanh không c",
    "đặt hàng 1 tuần chưa nhận được", "hàng giao bị rách, shop làm ăn kiểu gì vậy",
    "kiếm tiền online 500k/ngày inbox mình", "ghé shop mình xem hàng giá rẻ hơn bit.ly/abc",
    "kb zalo 0987654321 nhận quà", "follow kênh mình đi mọi người",
    "đồ lừa đảo, hàng dỏm", "dm shop ngu vcl", "con này xấu như ma",
    "chào shop ạ", "đẹp quá chị ơi", "haha vui quá", "hôm nay live lâu không chị", "cảm ơn shop nhiều",
    "chị mặc áo này xinh ghê", "xinh quá trời ơi 😍", "bà con vào đông vui quá", "chị ơi live tiếp mai nha",
    "❤️❤️❤️", "mới vào, chị đang bán gì vậy",
  ];
  const pick = (list) => list[Math.floor(Math.random() * list.length)];

  // A run sends exactly `count` messages at the chosen pace, then stops on its own.
  const simCount = $("sim-count");
  const simSpeed = $("sim-speed");
  const simStart = $("sim-start");
  const simProgress = $("sim-progress");
  simCount.value = store.get("live.simCount", simCount.value);
  simSpeed.value = store.get("live.simSpeed", simSpeed.value);
  simCount.addEventListener("change", () => store.set("live.simCount", simCount.value));
  simSpeed.addEventListener("change", () => store.set("live.simSpeed", simSpeed.value));

  const MAX_SIM = 500;
  const sim = { running: false, sent: 0, total: 0, timer: null };

  function simTarget() {
    const n = Math.round(Number(simCount.value));
    return Number.isFinite(n) ? Math.min(Math.max(n, 1), MAX_SIM) : 30;
  }

  function renderSim() {
    simStart.textContent = sim.running ? "■ Dừng" : "▶ Bắt đầu";
    simStart.classList.toggle("btn-primary", !sim.running);
    simCount.disabled = sim.running;
    if (!sim.total) simProgress.textContent = "";
    else if (sim.running) simProgress.textContent = `Đang gửi ${sim.sent}/${sim.total}`;
    else simProgress.textContent = sim.sent >= sim.total ? `✓ Đã gửi ${sim.sent}/${sim.total}` : `Đã dừng ở ${sim.sent}/${sim.total}`;
  }

  function stopSim() {
    clearTimeout(sim.timer);
    sim.running = false;
    renderSim();
  }

  function nextSim(delay) {
    sim.timer = setTimeout(async () => {
      if (!sim.running) return;
      if (document.hidden) return nextSim(1000);
      try {
        await send(pick(NAMES), pick(LINES), true);
        sim.sent += 1;
      } catch {
        // Busy or rate limited: wait a little and send that message again, so the count stays exact.
        return nextSim(2000);
      }
      renderSim();
      if (sim.sent >= sim.total) stopSim();
      else nextSim(Number(simSpeed.value) * (0.7 + Math.random() * 0.6));
    }, delay);
  }

  simStart.addEventListener("click", () => {
    if (sim.running) return stopSim();
    simCount.value = simTarget();
    Object.assign(sim, { running: true, sent: 0, total: simTarget() });
    renderSim();
    nextSim(0);
  });

  // ---------- start over (moderators only) ----------

  function clearChat() {
    chatList.replaceChildren();
    rendered.clear();
    pinned = true;
    $("chat-resume").hidden = true;
  }

  const resetBtn = $("live-reset");
  if (resetBtn) {
    // Two clicks instead of a browser dialog: the first arms the button for a few seconds.
    let armTimer = null;
    const disarm = () => {
      clearTimeout(armTimer);
      resetBtn.classList.remove("confirm");
      resetBtn.textContent = "↺ Làm lại từ đầu";
    };
    resetBtn.addEventListener("click", async () => {
      if (!resetBtn.classList.contains("confirm")) {
        resetBtn.classList.add("confirm");
        resetBtn.textContent = "Bấm lần nữa để xóa toàn bộ chat";
        armTimer = setTimeout(disarm, 4000);
        return;
      }
      disarm();
      resetBtn.disabled = true;
      stopSim();
      Object.assign(sim, { sent: 0, total: 0 });
      renderSim();
      try {
        await postJSON("/api/live/reset", {});
        clearChat();
        $("chat-error").textContent = "";
      } catch (err) {
        $("chat-error").textContent = err.message;
      } finally {
        resetBtn.disabled = false;
      }
    });
  }

  // ---------- stage: webcam or a video file ----------

  const video = $("stage-video");
  const empty = $("stage-empty");
  const webcamToggle = $("webcam-toggle");
  const soundToggle = $("sound-toggle");
  let camStream = null;
  let fileUrl = null;

  function showSource() {
    $("stage-error").textContent = "";
    if (camStream) {
      video.srcObject = camStream;
      video.removeAttribute("src");
      video.muted = true;
      video.classList.add("mirror");
      soundToggle.hidden = true;
    } else if (fileUrl) {
      video.srcObject = null;
      video.src = fileUrl;
      video.classList.remove("mirror");
      soundToggle.hidden = false;
    } else {
      video.srcObject = null;
      video.removeAttribute("src");
      video.load();
      soundToggle.hidden = true;
    }
    empty.hidden = Boolean(camStream || fileUrl);
    video.play().catch(() => {});
  }

  webcamToggle.addEventListener("change", async () => {
    if (webcamToggle.checked) {
      try {
        camStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      } catch (err) {
        webcamToggle.checked = false;
        showSource();
        $("stage-error").textContent = err.name === "NotAllowedError"
          ? "Trình duyệt chưa cho phép dùng webcam."
          : "Không mở được webcam.";
        return;
      }
    } else if (camStream) {
      camStream.getTracks().forEach((t) => t.stop());
      camStream = null;
    }
    showSource();
  });

  $("video-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (fileUrl) URL.revokeObjectURL(fileUrl);
    fileUrl = URL.createObjectURL(file);
    // Choosing a video means "show this": switch the webcam off.
    if (camStream) {
      camStream.getTracks().forEach((t) => t.stop());
      camStream = null;
      webcamToggle.checked = false;
    }
    showSource();
  });

  soundToggle.addEventListener("click", () => {
    video.muted = !video.muted;
    soundToggle.textContent = video.muted ? "🔇 Bật tiếng" : "🔊 Tắt tiếng";
  });

  // A gently drifting viewer count, for the look of a live market.
  let viewers = 1284;
  setInterval(() => {
    viewers = Math.max(800, viewers + Math.round((Math.random() - 0.45) * 12));
    $("viewer-count").textContent = viewers.toLocaleString("vi-VN");
  }, 3000);

  // ---------- model status ----------

  // The chat box stays a skeleton until the model can check messages.
  function setModelLoading(loading) {
    form.classList.toggle("is-loading", loading);
    form.setAttribute("aria-busy", String(loading));
    form.querySelectorAll("input, button").forEach((field) => (field.disabled = loading));
    simStart.disabled = loading;
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
