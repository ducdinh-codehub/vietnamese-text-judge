"""Worksheet solver: read a photo of a multiple-choice test, split it into questions, let Laya pick.

Laya is a text judge, not a knowledge model: it was trained to match text against criteria such as
intent or emotion, not to know that 7 x 8 = 56. This page exists to measure how well it does on test
questions anyway, so it shows Laya's pick for every question and, given an answer key, its score.

OCR is PaddleOCR (PP-OCRv5, Latin-script model) run through ONNX Runtime by rapidocr. It keeps most
Vietnamese accents but loses stacked ones (ệ, ộ, ừ), which also makes Laya's job harder.
"""

import re
import threading
import time

from . import analyzer

LETTERS = "ABCDEF"

# "Câu 1.", "Cau 1:", "Question 2)", "Q3.", "Bài 4 -", "5." at the start of a line.
QUESTION_START = re.compile(
    r"^\s*(?:(?:c[âa]u|question|q|b[àa]i)\s*)?(\d{1,3})\s*[.:)\-]\s*(.*)$", re.IGNORECASE
)
# An option letter like "A." "B)" "C:" not glued to a word before it ("Vitamin C." still matches,
# which is why options must also come in order, see _split_options).
OPTION_MARK = re.compile(r"(?<![A-Za-zÀ-ỹ])([A-F])\s*[.):]\s*")

# The fine-tuned checkpoint (finetune/train.py) was trained with this exact prompt; change both together.
LAYA_INSTRUCTIONS = "Which option correctly answers the question?"

_engine = None
_engine_lock = threading.Lock()


def _ocr_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

            _engine = RapidOCR(params={
                "Rec.lang_type": LangRec.LATIN,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
            })
        return _engine


def read_image(data):
    """Text lines in reading order from image bytes (PNG, JPEG...)."""
    result = _ocr_engine()(data)
    return list(result.txts or [])


def _split_options(text, expected):
    """[(letter, text)] for option marks in `text` that continue A, B, C... from `expected`.

    A mark that is not the next letter (the C in "Vitamin C. is found in") stays part of the text.
    """
    found, last_end, next_letter = [], None, expected
    for match in OPTION_MARK.finditer(text):
        if next_letter >= len(LETTERS) or match.group(1) != LETTERS[next_letter]:
            continue
        if found:
            found[-1][1] = text[last_end:match.start()]
        elif match.start() and text[:match.start()].strip():
            # Text before the first mark belongs to whatever came before.
            found.append([None, text[:match.start()]])
        found.append([match.group(1), ""])
        last_end, next_letter = match.end(), next_letter + 1
    if found and last_end is not None:
        found[-1][1] = text[last_end:]
    return [(letter, " ".join(t.split())) for letter, t in found]


def parse(lines):
    """Questions as [{"number", "stem", "options": {letter: text}}], in sheet order.

    Lines that come before the first question (titles, names) are dropped. Questions with fewer than
    two options are kept with "problem" set, so the page can show what was misread.
    """
    questions = []
    for line in lines:
        start = QUESTION_START.match(line)
        if start:
            questions.append({"number": int(start.group(1)), "stem": "", "options": {}})
            line = start.group(2)
        if not questions:
            continue
        q = questions[-1]
        parts = _split_options(line, len(q["options"]))
        if not parts:
            if q["options"]:
                last = list(q["options"])[-1]
                q["options"][last] = f"{q['options'][last]} {line.strip()}".strip()
            else:
                q["stem"] = f"{q['stem']} {line.strip()}".strip()
            continue
        for letter, text in parts:
            if letter is None:
                if q["options"]:
                    last = list(q["options"])[-1]
                    q["options"][last] = f"{q['options'][last]} {text}".strip()
                else:
                    q["stem"] = f"{q['stem']} {text}".strip()
            else:
                q["options"][letter] = text

    for q in questions:
        if len(q["options"]) < 2:
            q["problem"] = "Không đọc được đủ đáp án (cần ít nhất A và B)."
        elif not q["stem"]:
            q["problem"] = "Không đọc được đề bài."
    return questions


def parse_key(text):
    """{question number: letter} from "1A 2B 3-C", "1.A, 2.B" or plain "ABCD" (numbered from 1)."""
    text = (text or "").upper()
    pairs = re.findall(r"(\d{1,3})\s*[.:)\-]?\s*([A-F])\b", text)
    if pairs:
        return {int(n): letter for n, letter in pairs}
    letters = re.sub(r"[^A-F]", "", text)
    return {i + 1: letter for i, letter in enumerate(letters)}


def answer(question, checkpoint="multilingual"):
    """Laya's probability for each option of one question."""
    laya_question = {
        "mcq": {
            "type": "choice",
            "instructions": LAYA_INSTRUCTIONS,
            "criteria": dict(question["options"]),
        }
    }
    run = analyzer.predict({"body": question["stem"]}, laya_question, checkpoint)
    return run["result"]["answers"]["mcq"]["probabilities"]


def solve(lines, key_text="", checkpoint="multilingual"):
    """Everything the page shows for one sheet: what OCR read, each question with Laya's pick, and
    the score against the answer key when one is given.

    `checkpoint` is "multilingual" (the Hub model) or analyzer.FINETUNED (fine-tuned on school tests).
    """
    start = time.perf_counter()
    questions = parse(lines)
    key = parse_key(key_text)
    for q in questions:
        if "problem" in q:
            continue
        probs = answer(q, checkpoint)
        pick = max(probs, key=probs.get)
        q["probabilities"] = probs
        q["pick"] = pick
        q["confidence"] = probs[pick]
        if q["number"] in key:
            q["key"] = key[q["number"]]
            q["correct"] = pick == q["key"]

    graded = [q for q in questions if "correct" in q]
    answered = [q for q in questions if "pick" in q]
    # What picking at random would score on the same questions, for comparison.
    chance = sum(1 / len(q["options"]) for q in graded)
    return {
        "lines": lines,
        "questions": questions,
        "checkpoint": checkpoint,
        "summary": {
            "found": len(questions),
            "answered": len(answered),
            "graded": len(graded),
            "correct": sum(q["correct"] for q in graded),
            "chance": chance,
            "unmatched_key": sorted(n for n in key if n not in {q["number"] for q in questions}),
        },
        "latency_ms": (time.perf_counter() - start) * 1000,
    }
