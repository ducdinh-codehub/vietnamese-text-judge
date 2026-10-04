"""Emotion checker: Laya's emotion answer blended with a Vietnamese emotion word list.

Laya names specific feelings well (love, gratitude, sadness, worry) but never answers "neutral":
a bill or a meeting notice comes back "sad" or "surprised". It is also weak on unaccented text.
The word list fixes both: its matches add evidence, and when it finds nothing and Laya's sentiment
answer is neutral, the result leans to neutral. Matching runs on accent-free text, like scam.py.
"""

import re

from . import analyzer
from .scam import original_span, plain_with_positions

EMOTIONS = {
    "happy": {"label": "Vui vẻ", "emoji": "😄", "criteria": "joy, excitement, pleasure"},
    "grateful": {"label": "Biết ơn", "emoji": "🙏", "criteria": "thanks, appreciation"},
    "love": {"label": "Yêu thương", "emoji": "❤️", "criteria": "love, affection, caring, missing someone"},
    "angry": {"label": "Tức giận", "emoji": "😠", "criteria": "anger, frustration, irritation"},
    "sad": {"label": "Buồn", "emoji": "😢", "criteria": "sadness, disappointment, loneliness"},
    "worried": {"label": "Lo lắng", "emoji": "😟", "criteria": "worry, anxiety, fear"},
    "surprised": {"label": "Ngạc nhiên", "emoji": "😮", "criteria": "surprise, shock, amazement"},
    "neutral": {"label": "Trung tính", "emoji": "😐",
                "criteria": "no feeling at all: plain information such as schedules, prices, facts or instructions"},
}
SENTIMENTS = {
    "positive": {"label": "Tích cực", "criteria": "happy, satisfied, thankful, loving"},
    "neutral": {"label": "Trung tính", "criteria": "factual, no clear feeling"},
    "negative": {"label": "Tiêu cực", "criteria": "unhappy, angry, sad, worried, critical"},
}
LAYA_QUESTIONS = {
    "emotion": {
        "type": "choice",
        "instructions": "Which emotion does the author mainly express?",
        "criteria": {key: e["criteria"] for key, e in EMOTIONS.items()},
    },
    "sentiment": {
        "type": "choice",
        "instructions": "What is the overall sentiment of the text?",
        "criteria": {key: s["criteria"] for key, s in SENTIMENTS.items()},
    },
}

# How much the word list counts against Laya when both have something to say.
WORDS_WEIGHT = 0.5
# Laya's sentiment must be at least this sure of "neutral" to pull a message with no emotion words there.
NEUTRAL_SENTIMENT_AT = 0.5

# Patterns on accent-free lowercase text. Most words need a companion ("buon qua", not "buon")
# because without accents they collide with other words: buồn/buôn, tức/tục, sợ/số, yêu/yếu.
WORDS = {
    "happy": r"\bvui (qua|ghe|that|lam|the|vay)|\bvui\b(?! long)|hanh phuc|hao huc|phan khoi|sung suong|tuyet voi"
             r"|qua da|\bhaha+|\bhihi+|\byay\b|😄|😁|😂|🥳|😊|😆|🎉",
    "grateful": r"cam on|biet on|tri an|\bthanks?\b|thank you|🙏",
    "love": r"\b(yeu|thuong) (em|anh|con|ban|chi|me|bo|nhieu|lam|qua|nhat)|yeu thuong|\bnho (em|anh|con|ban|chi|me|bo|nha|nhieu)"
            r"|mong (den|toi) (ngay|luc|cuoi tuan) (gap|duoc gap)|❤|😍|🥰|😘|<3",
    "angry": r"\btuc (qua|that|ghe|minh|chet|dien)|tuc gian|nong gian|\bgian (qua|du|that|lam)|buc (minh|boi|qua|that|xuc)"
             r"|kho chiu|chan (that|qua|ghe)|\bghet\b|vo trach nhiem|qua dang|thai do|lam an kieu gi|dien mat|😠|😡|🤬",
    "sad": r"\bbuon (qua|that|ghe|lam|the|so)|\bbuon\b(?! ban)|that vong|co don|te hai|dau long|dau kho|\bkhoc\b|chan nan"
           r"|tiec (qua|that)|mat roi|khong ai hieu|😢|😭|💔|😞",
    "worried": r"\blo (lang|qua|lam|so|ghe)|\bso (qua|lam|hai|that|rang|ghe)|hoi hop|\brun (qua|lam|ghe)|bat an|cang thang"
               r"|khong biet (co sao|the nao)|😰|😟|😨|😥",
    "surprised": r"bat ngo|ngac nhien|khong the tin|troi (oi|dat)|\bwow\b|\bsoc\b|😮|😲|🤯|😱",
}


def find_words(text):
    """{emotion: [matched words from the user's text]} for every emotion the word list recognises."""
    plain, positions = plain_with_positions(text)
    found = {}
    for emotion, pattern in WORDS.items():
        for match in re.finditer(pattern, plain):
            words = original_span(text, positions, match)
            found.setdefault(emotion, [])
            if words not in found[emotion]:
                found[emotion].append(words)
    return found


def blend(laya_probs, words, sentiment):
    """Final probability per emotion, and which evidence decided it."""
    if words:
        counts = {e: len(w) for e, w in words.items()}
        total = sum(counts.values())
        evidence = {e: counts.get(e, 0) / total for e in EMOTIONS}
        source = "words"
    elif sentiment["neutral"] >= NEUTRAL_SENTIMENT_AT:
        evidence = {e: 1.0 if e == "neutral" else 0.0 for e in EMOTIONS}
        source = "neutral"
    else:
        return dict(laya_probs), "laya"
    return {e: (1 - WORDS_WEIGHT) * laya_probs[e] + WORDS_WEIGHT * evidence[e] for e in EMOTIONS}, source


def check(body, checkpoint="multilingual"):
    body = body.strip()
    run = analyzer.predict({"body": body}, LAYA_QUESTIONS, checkpoint)
    answers = run["result"]["answers"]
    laya_probs = answers["emotion"]["probabilities"]
    sentiment = answers["sentiment"]["probabilities"]

    words = find_words(body)
    probs, source = blend(laya_probs, words, sentiment)
    ranked = sorted(probs, key=probs.get, reverse=True)
    top = ranked[0]
    return {
        "emotion": top,
        "confidence": probs[top],
        "emotions": [{"id": e, **{k: EMOTIONS[e][k] for k in ("label", "emoji")}, "p": probs[e]} for e in ranked],
        "sentiment": max(sentiment, key=sentiment.get),
        "sentiments": [{"id": s, "label": SENTIMENTS[s]["label"], "p": sentiment[s]} for s in SENTIMENTS],
        "words": [{"id": e, "label": EMOTIONS[e]["label"], "words": w} for e, w in words.items()],
        "laya_emotion": max(laya_probs, key=laya_probs.get),
        "source": source,
        "latency_ms": run["load_ms"] + run["predict_ms"],
        "checkpoint": run["model"],
    }
