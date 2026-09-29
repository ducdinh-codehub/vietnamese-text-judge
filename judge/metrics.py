"""Numbers derived from Laya's answer distributions. Pure functions, no model needed."""

import math
import re

# noul bands: below NO_BELOW is "no", above YES_ABOVE is "yes", in between is "unsure".
NO_BELOW = 0.3
YES_ABOVE = 0.7


def entropy(probs):
    """Shannon entropy in nats of a list of probabilities."""
    # max() turns the -0.0 of a certain answer into 0.0.
    return max(0.0, -sum(p * math.log(p) for p in probs if p > 0))


def normalized_uncertainty(probs):
    """Entropy scaled to 0-1 so questions with different option counts compare."""
    if len(probs) < 2:
        return 0.0
    return entropy(probs) / math.log(len(probs))


def _ranked(options):
    """[(name, p), ...] sorted by probability, highest first."""
    return sorted(options.items(), key=lambda kv: kv[1], reverse=True)


def choice_metrics(answer, threshold):
    ranked = _ranked(answer["probabilities"])
    probs = [p for _, p in ranked]
    top_name, top_p = ranked[0]
    second_p = ranked[1][1] if len(ranked) > 1 else 0.0
    return {
        "answer": top_name,
        "probabilities": dict(ranked),
        "confidence": top_p,
        "margin": top_p - second_p,
        "top2": [{"option": n, "p": p} for n, p in ranked[:2]],
        "entropy": entropy(probs),
        "uncertainty": normalized_uncertainty(probs),
        "status": "auto" if top_p >= threshold else "review",
    }


def score_metrics(answer, levels, threshold):
    # Laya keys score probabilities by level index ("0", "1", ...) and returns the expected
    # value as `score`.
    probs = [answer["probabilities"][str(i)] for i in range(len(levels))]
    by_level = dict(zip(levels, probs))
    ranked = _ranked(by_level)
    top_name, top_p = ranked[0]
    second_p = ranked[1][1] if len(ranked) > 1 else 0.0
    expected = answer.get("score", sum(i * p for i, p in enumerate(probs)))
    spread = math.sqrt(sum(p * (i - expected) ** 2 for i, p in enumerate(probs)))
    return {
        "answer": top_name,
        "probabilities": by_level,
        "confidence": top_p,
        "margin": top_p - second_p,
        "top2": [{"option": n, "p": p} for n, p in ranked[:2]],
        "entropy": entropy(probs),
        "uncertainty": normalized_uncertainty(probs),
        "expected_score": expected,
        "max_score": len(levels) - 1,
        "spread": spread,
        "status": "auto" if top_p >= threshold else "review",
    }


def noul_metrics(answer, threshold):
    p = answer["noul"]
    probs = [p, 1 - p]
    if p < NO_BELOW:
        band = "no"
    elif p > YES_ABOVE:
        band = "yes"
    else:
        band = "unsure"
    confidence = max(p, 1 - p)
    return {
        "answer": band,
        "probabilities": {"yes": p, "no": 1 - p},
        "p_true": p,
        "confidence": confidence,
        "margin": abs(2 * p - 1),
        "odds": p / (1 - p) if p < 1 else math.inf,
        "band": band,
        "entropy": entropy(probs),
        "uncertainty": normalized_uncertainty(probs),
        "status": "auto" if confidence >= threshold and band != "unsure" else "review",
    }


def question_metrics(answer, spec, threshold):
    kind = spec["type"]
    if kind == "choice":
        out = choice_metrics(answer, threshold)
    elif kind == "score":
        out = score_metrics(answer, spec["criteria"], threshold)
    elif kind == "noul":
        out = noul_metrics(answer, threshold)
    else:
        raise ValueError(f"unknown question type {kind!r}")
    # Laya's own fields, kept for the details view.
    out["model_confidence"] = answer.get("confidence")
    out["act_probability"] = (answer.get("action") or {}).get("act_probability")
    return out


def overall(per_question):
    flagged = [qid for qid, m in per_question.items() if m["status"] == "review"]
    confidences = [m["confidence"] for m in per_question.values()]
    return {
        "verdict": "review" if flagged else "auto",
        "flagged": flagged,
        "average_confidence": sum(confidences) / len(confidences) if confidences else 0.0,
        "lowest_confidence": min(confidences) if confidences else 0.0,
    }


# Letters only Vietnamese uses among Latin-script languages (lowercase; input is lowercased).
_VI_LETTERS = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")


def looks_vietnamese(text):
    lowered = text.lower()
    return sum(ch in _VI_LETTERS for ch in lowered) >= 2


def text_stats(text):
    words = re.findall(r"\w+", text)
    sentences = [s for s in re.split(r"[.!?…]+", text) if s.strip()]
    return {
        "characters": len(text),
        "words": len(words),
        "sentences": len(sentences),
    }
