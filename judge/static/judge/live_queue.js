(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const POLL_MS = 2000;
  const list = $("queue-list");
  const csrf = () => document.querySelector("input[name=csrfmiddlewaretoken]").value;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function ago(iso) {
    const s = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
    if (s < 60) return `${s} giây trước`;
    if (s < 3600) return `${Math.floor(s / 60)} phút trước`;
    return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  }

  let view = "open";
  let kindFilter = "";
  let me = "";
  let lastData = null;

  // ---------- rendering ----------

  function button(label, className, action, id) {
    const b = el("button", `btn btn-sm ${className}`, label);
    b.type = "button";
    b.addEventListener("click", () => act(id, action, b));
    return b;
  }

  function card(c) {
    const blocked = view === "hidden";
    const li = el("li", `q-card kind-${c.kind}${blocked ? " blocked" : ""}${c.restored ? " restored" : ""}`);

    const head = el("div", "q-head");
    head.append(
      el("span", `pill ${blocked ? "pill-bad" : c.kind === "order" ? "pill-good" : c.kind === "complaint" ? "pill-warn" : "pill-muted"}`,
        `${c.emoji} ${c.label}`),
      el("strong", "", c.author),
      el("span", "", ago(c.time)),
    );
    if (c.assigned_to && c.status === "new") head.append(el("span", "pill pill-muted", `👤 ${c.assigned_to} đang xử lý`));
    li.append(head, el("div", "q-text", c.text));

    const why = c.source === "laya" ? `Laya đánh giá tiêu cực ${Math.round(c.laya_negative * 100)}%`
      : c.match ? `Nhận ra từ “${c.match}”` : "";
    const meta = el("div", "q-meta", why);
    if (view === "done" && c.handled_at) meta.textContent = `✓ ${c.assigned_to || "?"} xử lý ${ago(c.handled_at)}`;
    if (blocked && c.restored) meta.textContent = `${why} · đã hiện lại trong chat`;
    li.append(meta);

    const actions = el("div", "q-actions");
    if (view === "open") {
      if (c.assigned_to !== me) actions.append(button(c.assigned_to ? "Nhận lại" : "Nhận xử lý", "", "claim", c.id));
      else actions.append(button("Bỏ nhận", "", "unclaim", c.id));
      actions.append(button("✓ Xong", "btn-good", "done", c.id));
      if (c.kind === "order" || c.kind === "complaint") {
        actions.append(copyButton(c));
      }
    } else if (view === "done") {
      actions.append(button("Mở lại", "", "reopen", c.id));
    } else {
      actions.append(c.restored ? button("Ẩn lại", "", "hide", c.id) : button("Hiện lại trong chat", "", "restore", c.id));
    }
    li.append(actions);
    return li;
  }

  function copyButton(c) {
    const b = el("button", "btn btn-sm", "📋 Chép");
    b.type = "button";
    b.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(`${c.author}: ${c.text}`);
        b.textContent = "Đã chép";
      } catch {
        b.textContent = "Không chép được";
      }
      setTimeout(() => (b.textContent = "📋 Chép"), 1500);
    });
    return b;
  }

  function render() {
    if (!lastData) return;
    const comments = lastData.comments.filter((c) => !kindFilter || view !== "open" || c.kind === kindFilter);
    list.replaceChildren(...comments.map(card));
    const empty = $("queue-empty");
    empty.hidden = comments.length > 0;
    empty.textContent = {
      open: "Không còn gì trong hàng chờ. 🎉",
      done: "Chưa xử lý mục nào.",
      hidden: "Chưa có tin nhắn nào bị ẩn.",
    }[view];
    $("kind-filter").hidden = view !== "open";
  }

  // ---------- data ----------

  let lastJson = "";
  async function load() {
    try {
      const response = await fetch(`/api/live/queue?view=${view}`);
      if (response.status === 403) {
        location.reload();
        return;
      }
      const text = await response.text();
      if (!response.ok) throw new Error(JSON.parse(text).error);
      $("queue-error").textContent = "";
      // Redraw only when something changed, so a click never lands on a button being replaced.
      if (text === lastJson) return;
      lastJson = text;
      lastData = JSON.parse(text);
      me = lastData.me;
      $("count-open").textContent = lastData.counts.open;
      $("count-hidden").textContent = lastData.counts.hidden;
      document.title = lastData.counts.open ? `(${lastData.counts.open}) Hàng chờ Live` : "Hàng chờ Live";
      render();
    } catch (err) {
      $("queue-error").textContent = err.message || "Mất kết nối, đang thử lại…";
    }
  }

  let pollTimer = null;
  async function poll() {
    clearTimeout(pollTimer);
    await load();
    pollTimer = setTimeout(poll, POLL_MS);
  }

  async function act(id, action, btn) {
    btn.disabled = true;
    try {
      const response = await fetch(`/api/live/queue/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ action }),
      });
      if (!response.ok) throw new Error((await response.json()).error);
      lastJson = "";
      poll();
    } catch (err) {
      btn.disabled = false;
      $("queue-error").textContent = err.message;
    }
  }

  // ---------- tabs and filter ----------

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      view = tab.dataset.view;
      document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      lastJson = "";
      lastData = null;
      list.replaceChildren();
      poll();
    });
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      kindFilter = chip.dataset.kind;
      document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
      render();
    });
  });

  // "x giây trước" keeps moving even when nothing else changes.
  setInterval(render, 15000);
  poll();
})();
