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

# LAYA_ONNX=onnx/laya-multilingual-int8.onnx serves the multilingual checkpoint from an ONNX file
# made by export_onnx.py instead of PyTorch. Relative paths are from the project root.
ONNX_PATH = os.environ.get("LAYA_ONNX")
if ONNX_PATH:
    ONNX_PATH = str(Path(__file__).resolve().parent.parent / ONNX_PATH)

# Checkpoint fine-tuned on Vietnamese school tests by finetune/train.py. The Router only knows the Hub
# checkpoints, so this one is loaded as its own Agent on first use. LAYA_VI_SCHOOL moves it.
FINETUNED = "vi-school"
FINETUNED_DIR = Path(os.environ.get("LAYA_VI_SCHOOL")
                     or Path(__file__).resolve().parent.parent / "checkpoints" / "laya-vi-school")
_finetuned_agent = None

_router = Router()
_load_lock = threading.Lock()


def finetuned_available():
    return (FINETUNED_DIR / "model.safetensors").exists()
# name -> {"load_ms": float, "warnings": [str], "backend": str}
_loaded = {}


def _load(name):
    """Build the agent for `name` and hand it to the router; returns the backend's name."""
    if name == FINETUNED:
        from laya.agent import Agent

        global _finetuned_agent
        _finetuned_agent = Agent(str(FINETUNED_DIR))
        return "pytorch: " + FINETUNED_DIR.name
    if ONNX_PATH and name == "multilingual":
        from laya.onnx_agent import ONNXAgent

        _router.attach(name, ONNXAgent("convaiinnovations/laya", onnx_path=ONNX_PATH, subfolder="multilingual"))
        return "onnx: " + Path(ONNX_PATH).name
    _router.preload([name])
    return "pytorch"


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
            backend = _load(name)
        load_ms = (time.perf_counter() - start) * 1000
        _loaded[name] = {
            "load_ms": load_ms,
            "warnings": [str(w.message) for w in caught],
            "backend": backend,
        }
        return load_ms


def warm_up():
    _ensure_loaded("multilingual")


_warm_up_started = threading.Event()
_warm_up_lock = threading.Lock()


def start_warm_up():
    """Load the default checkpoint in a background thread, once per process."""
    if _warm_up_started.is_set():
        return
    with _warm_up_lock:
        if _warm_up_started.is_set():
            return
        _warm_up_started.set()
    threading.Thread(target=warm_up, daemon=True).start()


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
    if checkpoint == FINETUNED:
        load_ms = _ensure_loaded(FINETUNED)
        start = time.perf_counter()
        result = _finetuned_agent.system_one(state, laya_questions)
        predict_ms = (time.perf_counter() - start) * 1000
        return {"result": result, "decision": None, "model": FINETUNED, "load_ms": load_ms,
                "predict_ms": predict_ms}
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
