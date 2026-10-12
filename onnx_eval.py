"""Compare the ONNX exports from export_onnx.py against the original PyTorch checkpoint.

    .venv/bin/python onnx_eval.py

Runs the same messages and questions through PyTorch, ONNX fp32 and ONNX int8, then prints how far
each ONNX model's probabilities drift from PyTorch, how often its top answer changes, and whether
the scam and emotion checkers reach the same verdicts.
"""

import os
import time

import numpy as np
from laya.onnx_agent import ONNXAgent

import emotion_eval
import scam_eval
from export_onnx import REPO
from judge import analyzer, emotion, scam

ONNX_FILES = {
    "onnx-fp32": "onnx/laya-multilingual.onnx",
    "onnx-int8": "onnx/laya-multilingual-int8.onnx",
}

TEXTS = [m for _, m in scam_eval.MESSAGES] + [m for _, m in emotion_eval.MESSAGES]
QUESTION_SETS = {
    "scam": scam.LAYA_QUESTIONS,
    "emotion": emotion.LAYA_QUESTIONS,
    "analyze": {
        qid: {k: v for k, v in spec.items() if k in ("type", "instructions", "criteria")}
        for qid, spec in analyzer.QUESTIONS.items()
    },
}


def distribution(answer):
    """One answer as a probability vector, whatever its question type."""
    if answer["type"] == "noul":
        return np.array([1 - answer["noul"], answer["noul"]])
    return np.array(list(answer["probabilities"].values()))


def run_all(predict):
    """{(text index, set, qid): probability vector} and the mean latency per call."""
    out, times = {}, []
    for i, text in enumerate(TEXTS):
        for name, questions in QUESTION_SETS.items():
            start = time.perf_counter()
            answers = predict({"body": text}, questions)["answers"]
            times.append(time.perf_counter() - start)
            for qid, answer in answers.items():
                out[(i, name, qid)] = distribution(answer)
    return out, 1000 * sum(times) / len(times)


def checker_verdicts(predict):
    """Final scam verdicts and emotion labels with Laya swapped for `predict`."""
    original = analyzer.predict

    def patched(state, questions, checkpoint="multilingual"):
        return {"result": predict(state, questions), "model": checkpoint, "load_ms": 0, "predict_ms": 0}

    analyzer.predict = patched
    try:
        return ([scam.check(m)["verdict"] for _, m in scam_eval.MESSAGES],
                [emotion.check(m)["emotion"] for _, m in emotion_eval.MESSAGES])
    finally:
        analyzer.predict = original


def main():
    print("Loading PyTorch checkpoint...")
    analyzer._ensure_loaded("multilingual")
    torch_agent = analyzer._router._agents["multilingual"]
    backends = {"pytorch": torch_agent.predict}
    for name, path in ONNX_FILES.items():
        agent = ONNXAgent(REPO, onnx_path=path, subfolder="multilingual")
        backends[name] = agent.predict

    results, latency, verdicts = {}, {}, {}
    for name, predict in backends.items():
        print(f"Running {name}...")
        results[name], latency[name] = run_all(predict)
        verdicts[name] = checker_verdicts(predict)

    ref = results["pytorch"]
    ref_scam, ref_emotion = verdicts["pytorch"]
    n = len(ref)
    print(f"\n{len(TEXTS)} messages x {sum(map(len, QUESTION_SETS.values()))} questions = {n} answers\n")
    print(f"{'backend':10} {'file MB':>8} {'ms/call':>8} {'max |dp|':>9} {'mean |dp|':>10} "
          f"{'top changed':>12} {'scam same':>10} {'emotion same':>13}")
    for name in backends:
        diffs = [np.abs(results[name][k] - ref[k]).max() for k in ref]
        flips = sum(results[name][k].argmax() != ref[k].argmax() for k in ref)
        scam_v, emotion_v = verdicts[name]
        size = os.path.getsize(ONNX_FILES[name]) / 1e6 if name in ONNX_FILES else float("nan")
        print(f"{name:10} {size:8.0f} {latency[name]:8.0f} {max(diffs):9.4f} {np.mean(diffs):10.4f} "
              f"{flips:>5}/{n:<6} "
              f"{sum(a == b for a, b in zip(scam_v, ref_scam)):>4}/{len(ref_scam):<5} "
              f"{sum(a == b for a, b in zip(emotion_v, ref_emotion)):>6}/{len(ref_emotion)}")


if __name__ == "__main__":
    main()
