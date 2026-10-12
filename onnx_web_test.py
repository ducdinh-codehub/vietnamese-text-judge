"""Serve a test page that runs the int8 ONNX model in a phone's browser (onnxruntime-web).

    .venv/bin/python export_onnx.py      # once, creates onnx/laya-multilingual-int8.onnx
    .venv/bin/python onnx_web_test.py    # then open the printed URL on a phone on the same Wi-Fi

The page does not port laya's preprocessing yet: this script builds the exact model inputs for a
few real messages in Python, plus the answers the same model gives here, and the page checks the
browser reproduces them. It measures whether a phone can download, load and run the model at all.
Only the page, the cases and the model file are served; nothing else in the repo is reachable.
"""

import json
import socket
import subprocess
import warnings
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

import emotion_eval
import scam_eval
from export_onnx import REPO
from judge import emotion, scam

MODEL = Path("onnx/laya-multilingual-int8.onnx")
CASES = Path("onnx/web-cases.json")
PAGE = Path("webtest/index.html")
PORT = 8765

MESSAGES = [m for _, m in scam_eval.MESSAGES[:3] + scam_eval.MESSAGES[12:14]]
MESSAGES += [m for _, m in emotion_eval.MESSAGES[0:16:4]]
QUESTION_SETS = {"scam": scam.LAYA_QUESTIONS, "emotion": emotion.LAYA_QUESTIONS}


def option_labels(question):
    if question["type"] == "noul":
        return ["false", "true"]
    criteria = question["criteria"]
    return [str(i) for i in range(len(criteria))] if question["type"] == "score" else list(criteria)


def tensor(array):
    return {"dims": list(array.shape), "data": array.reshape(-1).astype(np.int64 if array.dtype != bool else bool).tolist()}


def build_cases():
    """Model inputs and expected outputs for each message, from laya's own ONNX runtime."""
    from laya.common import collate_items
    from laya.onnx_agent import ONNXAgent

    agent = ONNXAgent(REPO, onnx_path=str(MODEL), subfolder="multilingual")
    max_len, head_max_len = agent.cfg.get("max_len", 512), agent.cfg.get("head_max_len", 192)
    cases = []
    for name, questions in QUESTION_SETS.items():
        ids = list(questions)
        internal = {qid: agent._to_internal(questions[qid]) for qid in ids}
        for message in MESSAGES:
            items = agent._encode_state({"body": message}, ids, internal, max_len, head_max_len)
            b = collate_items([items], agent.tok.pad_token_id)
            inputs = {
                "input_ids": b["input_ids"].numpy(),
                "attention_mask": b["attention_mask"].numpy(),
                "marker_pos": b["marker_pos"].numpy(),
                "marker_mask": b["marker_mask"].numpy().astype(bool),
                "qtype": b["qtype"].numpy(),
            }
            logits, act_logits = agent.session.run(["logits", "act_logits"], inputs)
            cases.append({
                "set": name,
                "message": message,
                "questions": [{"id": qid, "options": option_labels(questions[qid])} for qid in ids],
                "inputs": {k: tensor(v) for k, v in inputs.items()},
                "expected": {"logits": logits.tolist(), "act_logits": act_logits.tolist()},
            })
    CASES.write_text(json.dumps(cases, ensure_ascii=False))
    print(f"Wrote {len(cases)} cases to {CASES}")


class Handler(SimpleHTTPRequestHandler):
    ROUTES = {"/": (PAGE, "text/html; charset=utf-8"),
              "/web-cases.json": (CASES, "application/json"),
              "/model.onnx": (MODEL, "application/octet-stream")}

    def do_GET(self):
        route = self.ROUTES.get(self.path.split("?")[0])
        if route is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path, content_type = route
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with path.open("rb") as f:
            self.copyfile(f, self.wfile)


def lan_ip():
    try:
        return subprocess.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def main():
    if not MODEL.exists():
        raise SystemExit(f"{MODEL} not found; run export_onnx.py first")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_cases()
    print(f"\nOn this Mac:  http://localhost:{PORT}/")
    print(f"On a phone:   http://{lan_ip()}:{PORT}/   (same Wi-Fi)\nCtrl+C to stop.")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
