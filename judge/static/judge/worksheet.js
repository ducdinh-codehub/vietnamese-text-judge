(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("sheet-form");
  const imageInput = $("image");
  const errorBox = $("form-error");

  const pct = (p) => `${Math.round(p * 100)}%`;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function meter(label, p, strong, tone) {
    const root = el("div", "m");
    const top = el("div", "m-top");
    top.append(el("span", strong ? "k strong" : "k", label), el("span", "v", pct(p)));
    const bar = el("div", `bar ${tone}`);
    const fill = el("span");
    fill.style.width = `${(Math.min(Math.max(p, 0), 1) * 100).toFixed(1)}%`;
    bar.append(fill);
    root.append(top, bar);
    return root;
  }

  // ---------- image preview ----------

  imageInput.addEventListener("change", () => {
    const preview = $("preview");
    const file = imageInput.files[0];
    if (preview.src) URL.revokeObjectURL(preview.src);
    preview.hidden = !file;
    if (file) preview.src = URL.createObjectURL(file);
  });

  // ---------- solve ----------

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.textContent = "";
    const file = imageInput.files[0];
    const text = $("text").value.trim();
    if (!file && !text) {
      errorBox.textContent = "Vui lòng chọn ảnh bài kiểm tra hoặc dán nội dung đề.";
      return;
    }

    const body = new FormData();
    if (file) body.append("image", file);
    else body.append("text", text);
    body.append("key", $("key").value);
    body.append("model", $("model").value);

    $("solve").disabled = true;
    $("solve").textContent = file ? "Đang đọc ảnh và giải…" : "Đang giải…";
    $("busy").classList.add("on");
    try {
      const response = await fetch("/api/worksheet", {
        method: "POST",
        headers: { "X-CSRFToken": form.querySelector("input[name=csrfmiddlewaretoken]").value },
        body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Lỗi máy chủ ${response.status}`);
      render(data);
    } catch (err) {
      errorBox.textContent = err.message;
    } finally {
      $("solve").disabled = false;
      $("solve").textContent = "Giải bài";
      $("busy").classList.remove("on");
    }
  });

  // ---------- rendering ----------

  function render(data) {
    const s = data.summary;
    const scoreStat = $("score-stat");
    if (s.graded) {
      $("score").textContent = `${s.correct}/${s.graded} · ${pct(s.correct / s.graded)}`;
      $("score-hint").textContent = `Đoán bừa trung bình được ${s.chance.toFixed(1)}/${s.graded} câu`;
      scoreStat.className = `stat ${s.correct > s.chance ? "verdict-auto" : "verdict-review"}`;
    } else {
      $("score").textContent = "—";
      $("score-hint").textContent = "Nhập đáp án đúng để chấm";
      scoreStat.className = "stat";
    }
    if (s.unmatched_key.length) {
      $("score-hint").textContent += ` · Đáp án cho câu ${s.unmatched_key.join(", ")} không khớp câu nào`;
    }

    $("found").textContent = `${s.answered}/${s.found}`;
    const times = [];
    if (data.ocr_ms !== undefined) times.push(`OCR ${Math.round(data.ocr_ms)} ms`);
    times.push(`Laya ${Math.round(data.latency_ms)} ms`);
    times.push(data.checkpoint === "vi-school" ? "bản fine-tune" : "bản gốc");
    $("timing").textContent = times.join(" · ");

    const cards = data.questions.map(renderQuestion);
    if (!cards.length) {
      cards.push(el("p", "muted", "Không tìm thấy câu hỏi nào. Mỗi câu cần bắt đầu bằng “Câu 1.”, “1.” hoặc “Question 1.”, và đáp án bằng “A.”, “B.”…"));
    }
    $("questions").replaceChildren(...cards);
    $("ocr-lines").textContent = data.lines.join("\n") || "—";
  }

  function renderQuestion(q) {
    let state = "";
    if (q.problem) state = "is-problem";
    else if (q.correct === true) state = "is-correct";
    else if (q.correct === false) state = "is-wrong";
    const card = el("article", `card ${state}`);

    const head = el("div", "card-head");
    head.append(el("div", "card-title", `Câu ${q.number}`));
    if (q.problem) head.append(el("span", "pill pill-warn", "Đọc lỗi"));
    else if (q.correct === true) head.append(el("span", "pill pill-good", "Đúng"));
    else if (q.correct === false) head.append(el("span", "pill pill-bad", `Sai · đáp án ${q.key}`));
    card.append(head, el("p", "stem", q.stem || "(không đọc được đề)"));

    if (q.problem) {
      card.append(el("p", "muted small", q.problem));
      return card;
    }

    card.append(el("div", "answer", `Laya chọn ${q.pick} · ${pct(q.confidence)}`));
    const meters = el("div", "meters");
    for (const [letter, text] of Object.entries(q.options)) {
      const tone = letter === q.pick ? "" : letter === q.key ? "good" : "muted";
      meters.append(meter(`${letter}. ${text}`, q.probabilities[letter], letter === q.pick, tone));
    }
    card.append(meters);
    return card;
  }

  // ---------- model status ----------

  function setModelLoading(loading) {
    form.classList.toggle("is-loading", loading);
    form.setAttribute("aria-busy", String(loading));
    form.querySelectorAll("input, textarea, select, button").forEach((field) => (field.disabled = loading));
  }
  setModelLoading(true);

  async function refreshStatus() {
    const pill = $("model-status");
    try {
      const data = await (await fetch("/api/status")).json();
      const loaded = Object.values(data.loaded);
      if (loaded.length) {
        pill.className = "pill pill-good";
        pill.textContent = `Model ready · ${loaded[0].backend}`;
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
