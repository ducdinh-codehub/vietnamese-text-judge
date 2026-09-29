(function () {
  "use strict";

  const SAMPLES = {
    refund: {
      subject: "Bị trừ tiền hai lần",
      body: "Tháng 3 công ty tôi bị tính phí hai lần. Vui lòng hoàn tiền ngay hôm nay, nếu không chúng tôi sẽ hủy dịch vụ.",
    },
    outage: {
      subject: "Hệ thống sập toàn bộ",
      body: "Từ 8 giờ sáng toàn bộ nhân viên không đăng nhập được, báo lỗi 500. Cả công ty đang ngừng làm việc! Bao giờ thì sửa xong?",
    },
    thanks: {
      subject: "Cảm ơn team",
      body: "Cảm ơn các bạn đã hỗ trợ nhanh hôm qua nha, mọi thứ chạy ngon rồi :)",
    },
    scam: {
      subject: "Tài khoản của bạn sắp bị khóa",
      body: "Tài khoản ngân hàng của quý khách sẽ bị khóa trong 24 giờ. Vui lòng bấm vào link bit.ly/xacminh và nhập mật khẩu cùng mã OTP để xác minh.",
    },
    noaccent: {
      subject: "gap!!! ko thanh toan dc",
      body: "khach hang cua minh ko thanh toan dc qua cong VNPay tu sang toi gio, mat don lien tuc, xu ly gap giup",
    },
  };

  const LIVE_MIN_CHARS = 3;
  // Reference points for bars that have no natural 0-100% scale.
  const LATENCY_SCALE_MS = 1000;
  const MAX_CHARS = 20000;

  const $ = (id) => document.getElementById(id);
  const form = $("judge-form");
  const bodyInput = $("body");
  const thresholdInput = $("threshold");
  const submitButton = $("submit");
  const errorBox = $("form-error");
  const liveToggle = $("live");
  const liveState = $("live-state");

  // ---------- formatting ----------

  const clamp01 = (x) => Math.min(Math.max(Number(x) || 0, 0), 1);
  const pct = (p) => `${Math.round(p * 100)}%`;
  const num = (x, digits = 2) => (x === null || x === undefined ? "—" : Number(x).toFixed(digits));
  const ms = (x) => `${Math.round(x).toLocaleString()} ms`;
  const threshold = () => Number(thresholdInput.value);
  const confidenceTone = (c) => (c >= threshold() ? "good" : "warn");
  // High uncertainty is bad news, so its colour runs the other way.
  const uncertaintyTone = (u) => (u <= 1 - threshold() ? "good" : "warn");

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** A labelled bar that stays on the page; only its value and width change. */
  function createMeter(label, parent) {
    const root = el("div", "m");
    const top = el("div", "m-top");
    const key = el("span", "k", label);
    const badge = el("span", "rank");
    badge.hidden = true;
    key.append(badge);
    const value = el("span", "v", "—");
    top.append(key, value);
    const bar = el("div", "bar muted");
    const fill = el("span");
    fill.style.width = "0%";
    bar.append(fill);
    root.append(top, bar);
    parent.append(root);
    return { key, badge, value, bar, fill };
  }

  /** `fraction` is 0-1; `tone` is good | warn | bad | muted | "" (accent). */
  function setMeter(m, fraction, text, tone = "") {
    m.fill.style.width = `${(clamp01(fraction) * 100).toFixed(1)}%`;
    m.value.textContent = text;
    m.bar.className = `bar ${tone}`;
  }

  function clearMeter(m) {
    setMeter(m, 0, "—", "muted");
    m.badge.hidden = true;
    m.key.classList.remove("strong");
  }

  function csrfToken() {
    return form.querySelector("input[name=csrfmiddlewaretoken]").value;
  }

  // ---------- form behaviour ----------

  function updateCharCount() {
    $("char-count").textContent = `${bodyInput.value.length.toLocaleString()} characters`;
  }
  bodyInput.addEventListener("input", updateCharCount);

  thresholdInput.addEventListener("input", () => {
    $("threshold-value").textContent = threshold().toFixed(2);
  });

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      const sample = SAMPLES[button.dataset.sample];
      $("subject").value = sample.subject;
      bodyInput.value = sample.body;
      updateCharCount();
      scheduleLive();
    });
  });

  // ---------- analysis queue ----------
  // Only one request runs at a time. Text typed meanwhile is sent as soon as it finishes, so the
  // server never builds a backlog of requests for text that is already out of date.

  let running = false;
  let queued = null; // { live } for the next run, or null

  function setBusy(on) {
    $("busy").classList.toggle("on", on);
  }

  function collectRequest() {
    return {
      subject: $("subject").value,
      body: bodyInput.value,
      checkpoint: $("checkpoint").value,
      threshold: threshold(),
      groups: [...form.querySelectorAll("input[name=groups]:checked")].map((el) => el.value),
    };
  }

  async function runAnalysis({ live }) {
    if (running) {
      queued = { live: queued ? queued.live && live : live };
      liveState.textContent = "Analyzing…";
      return;
    }
    errorBox.textContent = "";
    const payload = collectRequest();
    if (!payload.groups.length) {
      setBusy(false);
      errorBox.textContent = "Select at least one question group.";
      return;
    }
    if (live && payload.body.trim().length < LIVE_MIN_CHARS) {
      setBusy(false);
      liveState.textContent = "Keep typing…";
      return;
    }

    running = true;
    setBusy(true);
    liveState.textContent = "Analyzing…";
    if (!live) submitButton.disabled = true;
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Server error ${response.status}`);
      render(data);
      liveState.textContent = `Updated ${new Date().toLocaleTimeString()} · ${ms(data.request.latency_ms.total)}`;
      refreshStatus();
    } catch (err) {
      errorBox.textContent = err.message;
      liveState.textContent = "Error";
    } finally {
      running = false;
      submitButton.disabled = false;
      if (queued) {
        const next = queued;
        queued = null;
        runAnalysis(next);
      } else {
        setBusy(false);
      }
    }
  }

  // Every keystroke starts an analysis straight away. While one is running, keystrokes only mark
  // the text as changed, and the latest text is sent the moment the running request finishes.
  function scheduleLive() {
    if (!liveToggle.checked) return;
    runAnalysis({ live: true });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runAnalysis({ live: false });
  });

  ["subject", "body"].forEach((id) => $(id).addEventListener("input", scheduleLive));
  $("checkpoint").addEventListener("change", scheduleLive);
  thresholdInput.addEventListener("change", scheduleLive);
  form.querySelectorAll("input[name=groups]").forEach((el) => el.addEventListener("change", scheduleLive));
  liveToggle.addEventListener("change", () => {
    if (liveToggle.checked) scheduleLive();
    else liveState.textContent = "Live analysis off";
  });

  // ---------- model status ----------

  async function refreshStatus() {
    const pill = $("model-status");
    try {
      const data = await (await fetch("/api/status")).json();
      const names = Object.keys(data.loaded);
      if (names.length) {
        pill.className = "pill pill-good";
        pill.textContent = `Model ready`;
        pill.title = `Loaded: ${names.join(", ")}`;
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

  // ---------- page layout (built once) ----------
  // Every question, number and bar is drawn when the page loads. Results only change the values and
  // bar widths, so nothing jumps around while typing and the bars animate between results.

  const LAYOUT = JSON.parse($("layout-data").textContent);
  const METRIC_LABELS = {
    confidence: "Confidence",
    margin: "Margin (1st − 2nd)",
    uncertainty: "Normalized uncertainty",
    entropy: "Entropy",
    expected: "Expected score",
    spread: "Score spread (std)",
    p_true: "P(true)",
    odds: "Odds (yes : no)",
    model_confidence: "Laya model confidence",
    act_probability: "Act probability",
  };
  const METRICS_BY_TYPE = {
    choice: ["confidence", "margin", "uncertainty", "entropy", "model_confidence", "act_probability"],
    score: ["confidence", "margin", "uncertainty", "entropy", "expected", "spread", "model_confidence", "act_probability"],
    noul: ["confidence", "margin", "uncertainty", "entropy", "p_true", "odds", "model_confidence", "act_probability"],
  };

  const view = { stats: {}, groups: {}, cards: {}, request: {} };

  function buildStat(key, label, { verdict = false, hint = "" } = {}) {
    const root = el("div", verdict ? "stat verdict" : "stat");
    root.append(el("div", "label", label));
    const value = el("div", "value", "—");
    root.append(value);
    const stat = { root, value };
    if (!verdict) {
      stat.bar = el("div", "bar muted");
      stat.fill = el("span");
      stat.fill.style.width = "0%";
      stat.bar.append(stat.fill);
      root.append(stat.bar);
    }
    stat.hint = el("div", "hint", hint);
    root.append(stat.hint);
    $("summary").append(root);
    view.stats[key] = stat;
  }

  function buildSummary() {
    buildStat("verdict", "Overall", { verdict: true, hint: "Start typing to analyze." });
    buildStat("automated", "Automated");
    buildStat("average", "Avg confidence");
    buildStat("lowest", "Lowest confidence");
    buildStat("latency", "Latency", { hint: "bar full = 1 s" });
  }

  function buildQuestions() {
    const container = $("question-groups");
    for (const [groupKey, groupName] of Object.entries(LAYOUT.groups)) {
      const title = el("h2", "group-title", groupName);
      const pill = el("span", "pill pill-muted", "waiting");
      title.append(" ", pill);
      const cards = el("div", "cards");
      container.append(title, cards);
      view.groups[groupKey] = { pill };

      for (const q of LAYOUT.questions.filter((item) => item.group === groupKey)) {
        const card = el("article", "card pending");
        const head = el("div", "card-head");
        const names = el("div");
        names.append(el("div", "card-title", q.label));
        const type = el("div", "card-type", q.type);
        if (q.experimental) {
          type.append(" · ");
          const tag = el("span", "experimental", "experimental");
          tag.title = "Laya's score type is its weakest area";
          type.append(tag);
        }
        names.append(type);
        const status = el("span", "pill pill-muted", "—");
        head.append(names, status);
        const answer = el("div", "answer", "—");

        card.append(head, answer, el("h4", "", "Options"));
        const optionBox = el("div", "meters");
        card.append(optionBox, el("h4", "", "Metrics"));
        const metricBox = el("div", "meters");
        card.append(metricBox);
        cards.append(card);

        const options = {};
        for (const name of q.options) options[name] = createMeter(name, optionBox);
        const metrics = {};
        for (const key of METRICS_BY_TYPE[q.type]) metrics[key] = createMeter(METRIC_LABELS[key], metricBox);
        view.cards[q.id] = { spec: q, card, status, answer, options, metrics };
      }
    }
  }

  function buildBlock(title, meterLabels, kvLabels, noticeText) {
    const root = el("div", "info-block");
    root.append(el("h3", "", title));
    const box = el("div", "meters");
    root.append(box);
    const meters = {};
    for (const [key, label] of Object.entries(meterLabels)) meters[key] = createMeter(label, box);
    const kv = {};
    if (Object.keys(kvLabels).length) {
      const dl = el("dl", "kv");
      for (const [key, label] of Object.entries(kvLabels)) {
        kv[key] = el("dd", "", "—");
        dl.append(el("dt", "", label), kv[key]);
      }
      root.append(dl);
    }
    let notice = null;
    if (noticeText) {
      notice = el("div", "notice warn", noticeText);
      notice.hidden = true;
      root.append(notice);
    }
    $("request-info").append(root);
    return { meters, kv, notice };
  }

  function buildRequest() {
    view.request.text = buildBlock("Text", { chars: "Characters" }, { words: "Words", sentences: "Sentences" });
    view.request.tokens = buildBlock("Tokens", { used: "Context used", tokens: "Text tokens" },
      { window: "Model window", truncated: "Truncated" },
      "The text is longer than the checkpoint can read. The end of it was cut off and not judged.");
    view.request.language = buildBlock("Language", { diacritics: "Diacritic rate" },
      { detected: "Detected", method: "Method", script: "Script" });
    view.request.latency = buildBlock("Latency", { predict: "Prediction", load: "Model load", total: "Total" },
      { scale: "Bar scale" });
    view.request.latency.kv.scale.textContent = "full = 1 s";
    view.request.checkpoint = buildBlock("Checkpoint", { questions: "Questions asked", threshold: "Review threshold" },
      { requested: "Requested", used: "Used", repo: "Repo", reason: "Reason" },
      "This checkpoint reported uncalibrated confidence values. Treat the percentages as rough.");
  }

  buildSummary();
  buildQuestions();
  buildRequest();

  // ---------- updating values ----------

  function render(data) {
    updateSummary(data.summary, data.questions, data.request);
    updateQuestions(data.questions);
    updateRequest(data.request);
  }

  function setStat(stat, fraction, text, tone, hint) {
    stat.value.textContent = text;
    stat.fill.style.width = `${(clamp01(fraction) * 100).toFixed(1)}%`;
    stat.bar.className = `bar ${tone}`;
    if (hint !== undefined) stat.hint.textContent = hint;
  }

  function updateSummary(summary, questions, request) {
    const isAuto = summary.verdict === "auto";
    const flaggedLabels = questions.filter((q) => summary.flagged.includes(q.id)).map((q) => q.label);
    const autoCount = questions.length - summary.flagged.length;
    const s = view.stats;

    s.verdict.root.className = `stat verdict verdict-${summary.verdict}`;
    s.verdict.value.textContent = isAuto ? "Safe to automate" : "Send to a human";
    s.verdict.hint.textContent = summary.flagged.length
      ? `Needs review: ${flaggedLabels.join(", ")}`
      : `All answers are above the ${num(request.threshold)} threshold`;

    setStat(s.automated, autoCount / questions.length, `${autoCount}/${questions.length}`, isAuto ? "good" : "warn");
    setStat(s.average, summary.average_confidence, pct(summary.average_confidence),
      confidenceTone(summary.average_confidence));
    setStat(s.lowest, summary.lowest_confidence, pct(summary.lowest_confidence),
      confidenceTone(summary.lowest_confidence));
    setStat(s.latency, request.latency_ms.predict / LATENCY_SCALE_MS, ms(request.latency_ms.predict), "");

    const top = $("top-verdict");
    top.hidden = false;
    top.className = `pill ${isAuto ? "pill-good" : "pill-warn"}`;
    top.textContent = isAuto ? "Auto" : `Review ${summary.flagged.length}/${questions.length}`;
  }

  function updateQuestions(questions) {
    const byId = Object.fromEntries(questions.map((q) => [q.id, q]));
    for (const [id, c] of Object.entries(view.cards)) {
      const q = byId[id];
      if (q) updateCard(c, q);
      else clearCard(c);
    }
    for (const [groupKey, g] of Object.entries(view.groups)) {
      const inGroup = questions.filter((q) => q.group === groupKey);
      const review = inGroup.filter((q) => q.status === "review").length;
      if (!inGroup.length) {
        g.pill.className = "pill pill-muted";
        g.pill.textContent = "not asked";
      } else if (review) {
        g.pill.className = "pill pill-warn";
        g.pill.textContent = `${review} review`;
      } else {
        g.pill.className = "pill pill-good";
        g.pill.textContent = "all auto";
      }
    }
  }

  function clearCard(c) {
    c.card.className = "card inactive";
    c.status.className = "pill pill-muted";
    c.status.textContent = "Off";
    c.answer.className = "answer";
    c.answer.textContent = "not asked";
    Object.values(c.options).forEach(clearMeter);
    Object.values(c.metrics).forEach(clearMeter);
  }

  function updateCard(c, q) {
    c.card.className = `card ${q.status}`;
    c.status.className = `pill ${q.status === "auto" ? "pill-good" : "pill-warn"}`;
    c.status.textContent = q.status === "auto" ? "Auto" : "Review";
    c.answer.className = q.type === "noul" ? `answer band-${q.band}` : "answer";
    c.answer.textContent = q.type === "noul" ? `${q.band} · ${pct(q.p_true)}` : q.answer;

    const ranked = Object.entries(q.probabilities).sort((a, b) => b[1] - a[1]).map(([name]) => name);
    for (const [name, m] of Object.entries(c.options)) {
      const p = q.probabilities[name] ?? 0;
      const rank = ranked.indexOf(name);
      setMeter(m, p, pct(p), rank === 0 ? "" : "muted");
      m.key.classList.toggle("strong", rank === 0);
      m.badge.hidden = rank > 1;
      m.badge.textContent = rank === 0 ? "1st" : rank === 1 ? "2nd" : "";
    }

    const m = c.metrics;
    const maxEntropy = Math.log(c.spec.options.length);
    setMeter(m.confidence, q.confidence, pct(q.confidence), confidenceTone(q.confidence));
    setMeter(m.margin, q.margin, num(q.margin));
    setMeter(m.uncertainty, q.uncertainty, num(q.uncertainty), uncertaintyTone(q.uncertainty));
    setMeter(m.entropy, maxEntropy ? q.entropy / maxEntropy : 0,
      `${num(q.entropy, 3)} / ${num(maxEntropy)} nats`, uncertaintyTone(q.uncertainty));
    if (q.type === "score") {
      setMeter(m.expected, q.expected_score / q.max_score, `${num(q.expected_score)} / ${q.max_score}`);
      // The widest possible spread over levels 0..max is max / 2.
      setMeter(m.spread, q.max_score ? q.spread / (q.max_score / 2) : 0, num(q.spread), "muted");
    }
    if (q.type === "noul") {
      setMeter(m.p_true, q.p_true, pct(q.p_true), q.band === "yes" ? "bad" : q.band === "no" ? "good" : "warn");
      // odds / (1 + odds) = P(true), so the bar is the same length as P(true).
      setMeter(m.odds, q.p_true, q.odds === null ? "∞ : 1" : `${num(q.odds)} : 1`, "muted");
    }
    setMeter(m.model_confidence, q.model_confidence, num(q.model_confidence), "muted");
    setMeter(m.act_probability, q.act_probability, num(q.act_probability), "muted");
  }

  function updateRequest(r) {
    const v = view.request;
    const t = r.tokens;
    const lat = r.latency_ms;

    setMeter(v.text.meters.chars, r.text.characters / MAX_CHARS,
      `${r.text.characters.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`);
    v.text.kv.words.textContent = r.text.words.toLocaleString();
    v.text.kv.sentences.textContent = r.text.sentences.toLocaleString();

    if (t) {
      setMeter(v.tokens.meters.used, t.percent_used / 100, `${t.percent_used.toFixed(1)}%`, t.truncated ? "warn" : "good");
      setMeter(v.tokens.meters.tokens, t.tokens / t.budget,
        `${t.tokens.toLocaleString()} / ${t.budget.toLocaleString()}`, t.truncated ? "warn" : "");
      v.tokens.kv.window.textContent = `${t.max_len.toLocaleString()} tokens`;
      v.tokens.kv.truncated.textContent = t.truncated ? "yes" : "no";
      v.tokens.notice.hidden = !t.truncated;
    } else {
      Object.values(v.tokens.meters).forEach(clearMeter);
      v.tokens.kv.window.textContent = "unavailable";
      v.tokens.kv.truncated.textContent = "—";
      v.tokens.notice.hidden = true;
    }

    setMeter(v.language.meters.diacritics, r.language.diacritic_rate, num(r.language.diacritic_rate, 3), "muted");
    v.language.kv.detected.textContent = r.language.code;
    v.language.kv.method.textContent = r.language.how;
    v.language.kv.script.textContent = r.language.script || "—";

    setMeter(v.latency.meters.predict, lat.predict / LATENCY_SCALE_MS, ms(lat.predict));
    setMeter(v.latency.meters.load, lat.load / LATENCY_SCALE_MS, lat.load ? ms(lat.load) : "already loaded", "muted");
    setMeter(v.latency.meters.total, lat.total / LATENCY_SCALE_MS, ms(lat.total));

    setMeter(v.checkpoint.meters.questions, r.question_count / r.total_questions,
      `${r.question_count} / ${r.total_questions}`);
    setMeter(v.checkpoint.meters.threshold, r.threshold, num(r.threshold), "muted");
    v.checkpoint.kv.requested.textContent = r.checkpoint.requested;
    v.checkpoint.kv.used.textContent = r.checkpoint.used;
    v.checkpoint.kv.repo.textContent = r.checkpoint.repo || "—";
    v.checkpoint.kv.reason.textContent = r.checkpoint.reason;
    v.checkpoint.notice.hidden = !r.calibration_warnings.length;
  }
})();
