"""Runs Laya on user text and turns the result into everything the page displays."""

import json
import os
import threading
import time
import warnings
from pathlib import Path

# Must be set before huggingface_hub is imported (by laya) to hide the "Fetching files" bar.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from laya import Router  # noqa: E402
from laya.common import encode_text, serialize_state  # noqa: E402
from laya.lang import analyse  # noqa: E402

from . import metrics  # noqa: E402

CONFIG = json.loads((Path(__file__).with_name("questions.json")).read_text(encoding="utf-8"))
GROUPS = CONFIG["groups"]
QUESTIONS = CONFIG["questions"]

CHECKPOINTS = ("multilingual", "english", "auto")
DEFAULT_THRESHOLD = 0.7

_router = Router()
_load_lock = threading.Lock()
# name -> {"load_ms": float, "warnings": [str]}
_loaded = {}


def _ensure_loaded(name):
    """Load a checkpoint once, remembering how long it took and any warnings it raised."""
    if name in _loaded:
        return 0.0
    with _load_lock:
        if name in _loaded:
            return 0.0
        start = time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _router.preload([name])
        load_ms = (time.perf_counter() - start) * 1000
        _loaded[name] = {
            "load_ms": load_ms,
            "warnings": [str(w.message) for w in caught],
        }
        return load_ms


def warm_up():
    _ensure_loaded("multilingual")


def loaded_checkpoints():
    return {name: dict(info) for name, info in _loaded.items()}


def _token_usage(state, checkpoint):
    """How many tokens the text uses, against how many the checkpoint can read."""
    # Router has no public accessor for a loaded agent's tokenizer and config.
    agent = _router._agents.get(checkpoint)
    if agent is None:
        return None
    max_len = agent.cfg.get("max_len", 512)
    head_max_len = agent.cfg.get("head_max_len", 192)
    # Room left for the text once the question and options take their share of the window.
    budget = max_len - head_max_len - 8
    text = serialize_state(state).replace(agent.tok.mask_token, " ")
    tokens = len(encode_text(agent.tok, text, add_special_tokens=False)["input_ids"])
    return {
        "tokens": tokens,
        "budget": budget,
        "max_len": max_len,
        "percent_used": tokens / budget * 100,
        "truncated": tokens > budget,
    }


def _language(state, text):
    detection = analyse(state)
    if metrics.looks_vietnamese(text):
        code, how = "vi", "Vietnamese letters found"
    elif detection.get("language"):
        code, how = detection["language"], "Laya language detector"
    elif detection.get("is_english"):
        code, how = "en?", "Laya guess: English (undecided, may be unaccented Vietnamese)"
    else:
        code, how = "unknown", "Laya could not decide"
    return {
        "code": code,
        "how": how,
        "script": detection.get("script"),
        "diacritic_rate": detection.get("diacritic_rate"),
    }


def predict(state, laya_questions, checkpoint="multilingual"):
    """Ask Laya a set of questions, loading the checkpoint first if needed."""
    if checkpoint not in CHECKPOINTS:
        raise ValueError(f"checkpoint must be one of {CHECKPOINTS}")
    decision = _router.route(state, laya_questions, model=None if checkpoint == "auto" else checkpoint)
    routed = decision.model
    load_ms = _ensure_loaded(routed)

    start = time.perf_counter()
    result = _router.predict(state, laya_questions, model=routed)
    predict_ms = (time.perf_counter() - start) * 1000
    return {"result": result, "decision": decision, "model": routed, "load_ms": load_ms, "predict_ms": predict_ms}


def analyze(subject, body, checkpoint="multilingual", threshold=DEFAULT_THRESHOLD, groups=None):
    groups = set(groups or GROUPS)
    selected = {qid: spec for qid, spec in QUESTIONS.items() if spec["group"] in groups}
    if not selected:
        raise ValueError("select at least one question group")

    state = {"subject": subject, "body": body} if subject else {"body": body}
    laya_questions = {
        qid: {k: v for k, v in spec.items() if k in ("type", "instructions", "criteria")}
        for qid, spec in selected.items()
    }

    run = predict(state, laya_questions, checkpoint)
    result, decision, routed = run["result"], run["decision"], run["model"]
    load_ms, predict_ms = run["load_ms"], run["predict_ms"]

    per_question = {
        qid: metrics.question_metrics(result["answers"][qid], spec, threshold)
        for qid, spec in selected.items()
    }
    questions_out = [
        {
            "id": qid,
            "label": spec["label"],
            "group": spec["group"],
            "type": spec["type"],
            "experimental": spec["type"] == "score",
            **per_question[qid],
        }
        for qid, spec in selected.items()
    ]

    full_text = f"{subject}\n{body}" if subject else body
    return {
        "summary": metrics.overall(per_question),
        "questions": questions_out,
        "groups": GROUPS,
        "request": {
            "text": metrics.text_stats(full_text),
            "tokens": _token_usage(state, routed),
            "language": _language(state, full_text),
            "checkpoint": {
                "requested": checkpoint,
                "used": routed,
                "repo": decision.get("repo"),
                "reason": decision.reason,
            },
            "latency_ms": {
                "load": load_ms,
                "predict": predict_ms,
                "total": load_ms + predict_ms,
            },
            "question_count": len(selected),
            "total_questions": len(QUESTIONS),
            "threshold": threshold,
            "calibration_warnings": _loaded[routed]["warnings"],
        },
    }
