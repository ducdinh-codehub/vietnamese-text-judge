(function () {
  "use strict";

  const LIVE_MIN_CHARS = 3;

  const $ = (id) => document.getElementById(id);
  const form = $("judge-form");
  const bodyInput = $("body");
  const thresholdInput = $("threshold");
  const errorBox = $("form-error");
  const liveState = $("live-state");
  const LAYOUT = JSON.parse($("layout-data").textContent);

  // ---------- formatting ----------

  const clamp01 = (x) => Math.min(Math.max(Number(x) || 0, 0), 1);
  const pct = (p) => `${Math.round(p * 100)}%`;
  const ms = (x) => `${Math.round(x).toLocaleString()} ms`;
  const threshold = () => Number(thresholdInput.value);
  const confidenceTone = (c) => (c >= threshold() ? "good" : "warn");

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

  // ---------- analysis queue ----------
  // Only one request runs at a time. Text typed meanwhile is sent as soon as it finishes, so the
  // server never builds a backlog of requests for text that is already out of date.

  let running = false;
  let queued = false;

  function setBusy(on) {
    $("busy").classList.toggle("on", on);
  }

  function collectRequest() {
    return {
      subject: $("subject").value,
      body: bodyInput.value,
      checkpoint: $("checkpoint").value,
      threshold: threshold(),
      groups: Object.keys(LAYOUT.groups),
    };
  }

  async function runAnalysis() {
    if (running) {
      queued = true;
      liveState.textContent = "Analyzing…";
      return;
    }
    errorBox.textContent = "";
    const payload = collectRequest();
    if (payload.body.trim().length < LIVE_MIN_CHARS) {
      setBusy(false);
      liveState.textContent = "Keep typing…";
      return;
    }

    running = true;
    setBusy(true);
    liveState.textContent = "Analyzing…";
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
      if (queued) {
        queued = false;
        runAnalysis();
      } else {
        setBusy(false);
      }
    }
  }

  // Enter in the subject field would submit the form; analysis already runs as you type.
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

  ["subject", "body"].forEach((id) => $(id).addEventListener("input", afterTypingPause(runAnalysis)));
  $("checkpoint").addEventListener("change", runAnalysis);
  thresholdInput.addEventListener("change", runAnalysis);

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
      const names = Object.keys(data.loaded);
      if (names.length) {
        pill.className = "pill pill-good";
        pill.textContent = `Model ready`;
        pill.title = `Loaded: ${names.join(", ")}`;
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

  // ---------- page layout (built once) ----------
  // Every question and bar is drawn when the page loads. Results only change the values and bar
  // widths, so nothing jumps around while typing and the bars animate between results.

  const view = { stats: {}, groups: {}, cards: {}, notices: {} };

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
    buildStat("average", "Avg confidence");
    buildStat("lowest", "Lowest confidence");
  }

  function buildNotice(key, text) {
    const notice = el("div", "notice warn", text);
    notice.hidden = true;
    $("notices").append(notice);
    view.notices[key] = notice;
  }

  function buildNotices() {
    buildNotice("truncated", "The text is longer than the checkpoint can read. The end of it was cut off and not judged.");
    buildNotice("calibration", "This checkpoint reported uncalibrated confidence values. Treat the percentages as rough.");
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
        if (q.experimental) {
          const tag = el("div", "card-type experimental", "experimental");
          tag.title = "Laya's score type is its weakest area";
          names.append(tag);
        }
        const status = el("span", "pill pill-muted", "—");
        head.append(names, status);
        const answer = el("div", "answer", "—");
        const optionBox = el("div", "meters");
        card.append(head, answer, optionBox);
        cards.append(card);

        const options = {};
        for (const name of q.options) options[name] = createMeter(name, optionBox);
        view.cards[q.id] = { card, status, answer, options };
      }
    }
  }

  buildSummary();
  buildNotices();
  buildQuestions();

  // ---------- updating values ----------

  function render(data) {
    updateSummary(data.summary, data.questions, data.request);
    updateQuestions(data.questions);
    view.notices.truncated.hidden = !data.request.tokens?.truncated;
    view.notices.calibration.hidden = !data.request.calibration_warnings.length;
  }

  function setStat(stat, fraction, text, tone) {
    stat.value.textContent = text;
    stat.fill.style.width = `${(clamp01(fraction) * 100).toFixed(1)}%`;
    stat.bar.className = `bar ${tone}`;
  }

  function updateSummary(summary, questions, request) {
    const isAuto = summary.verdict === "auto";
    const flaggedLabels = questions.filter((q) => summary.flagged.includes(q.id)).map((q) => q.label);
    const s = view.stats;

    s.verdict.root.className = `stat verdict verdict-${summary.verdict}`;
    s.verdict.value.textContent = isAuto ? "Safe to automate" : "Send to a human";
    s.verdict.hint.textContent = summary.flagged.length
      ? `Needs review: ${flaggedLabels.join(", ")}`
      : `All answers are above the ${request.threshold.toFixed(2)} threshold`;

    setStat(s.average, summary.average_confidence, pct(summary.average_confidence),
      confidenceTone(summary.average_confidence));
    setStat(s.lowest, summary.lowest_confidence, pct(summary.lowest_confidence),
      confidenceTone(summary.lowest_confidence));

    const top = $("top-verdict");
    top.hidden = false;
    top.className = `pill ${isAuto ? "pill-good" : "pill-warn"}`;
    top.textContent = isAuto ? "Auto" : `Review ${summary.flagged.length}/${questions.length}`;
  }

  function updateQuestions(questions) {
    for (const q of questions) {
      const c = view.cards[q.id];
      if (c) updateCard(c, q);
    }
    for (const [groupKey, g] of Object.entries(view.groups)) {
      const review = questions.filter((q) => q.group === groupKey && q.status === "review").length;
      g.pill.className = `pill ${review ? "pill-warn" : "pill-good"}`;
      g.pill.textContent = review ? `${review} review` : "all auto";
    }
  }

  function updateCard(c, q) {
    c.card.className = `card ${q.status}`;
    c.status.className = `pill ${q.status === "auto" ? "pill-good" : "pill-warn"}`;
    c.status.textContent = `${q.status === "auto" ? "Auto" : "Review"} · ${pct(q.confidence)}`;
    c.answer.className = q.type === "noul" ? `answer band-${q.band}` : "answer";
    c.answer.textContent = q.type === "noul" ? q.band : q.answer;

    const ranked = Object.entries(q.probabilities).sort((a, b) => b[1] - a[1]).map(([name]) => name);
    for (const [name, m] of Object.entries(c.options)) {
      const p = q.probabilities[name] ?? 0;
      const rank = ranked.indexOf(name);
      setMeter(m, p, pct(p), rank === 0 ? "" : "muted");
      m.key.classList.toggle("strong", rank === 0);
      m.badge.hidden = rank > 1;
      m.badge.textContent = rank === 0 ? "1st" : rank === 1 ? "2nd" : "";
    }
  }
})();
