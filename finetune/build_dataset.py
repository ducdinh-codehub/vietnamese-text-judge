"""Build the Vietnamese school multiple-choice dataset for fine-tuning Laya.

    python3 finetune/build_dataset.py

Reads the raw downloads in finetune/data/raw/ (see finetune/README.md for how to get them), cleans and labels
every question, removes duplicates and writes finetune/data/processed/{train,val,test}.jsonl plus a report.

Each line is one question:
    {"id", "source", "license", "level", "grade", "subject", "stem", "options": {"A": ...},
     "answer", "explanation", "year", "flags": [...], "usable": bool}

"usable" is false when a flag means the text alone cannot be answered (a picture, the Atlat,
a reading passage that was not kept) or the question could not be parsed reliably. Those rows are
kept in the files so they can be fixed later, but training and evaluation should skip them.
"""

import glob
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
SEED = 13
# Share of question clusters held out; split by (level, subject) so every slice is represented.
VAL_SHARE, TEST_SHARE = 0.1, 0.15

LEVELS = ("primary", "lower_secondary", "upper_secondary")
SUBJECTS = {
    # VNHSGE folder names
    "Mathematics": "toan", "Physics": "vat_ly", "Chemistry": "hoa_hoc", "Biology": "sinh_hoc",
    "History": "lich_su", "Geography": "dia_ly", "CivicEducation": "gdcd", "English": "tieng_anh",
    # M3Exam subject names
    "math": "toan", "physics": "vat_ly", "chemistry": "hoa_hoc", "biology": "sinh_hoc",
    "history": "lich_su", "geography": "dia_ly", "civic": "gdcd", "english": "tieng_anh",
    "vietnamese": "tieng_viet", "literature": "ngu_van", "science": "khoa_hoc",
    "natural-science": "khoa_hoc", "social-science": "lich_su_dia_ly",
}
# M3Exam levels are the exit exams of each school stage.
M3_LEVELS = {"low": ("primary", 5), "mid": ("lower_secondary", 9), "high": ("upper_secondary", 12)}

LICENSES = {
    "vnhsge": "CC BY-NC-ND 4.0 (VNHSGE paper); non-commercial",
    "m3exam": "no license stated (M3Exam); treat as research only",
    "vietjack_math": "no license; scraped from VietJack by hllj/vi_grade_school_math_mcq; research only",
}

# The question depends on something that is not in the text.
NEEDS_ATLAS = re.compile(r"\bAtlat\b", re.IGNORECASE)
# A chart or picture the question points at. Data tables ("Cho bảng số liệu: ...") and reaction
# schemes ("sơ đồ phản ứng") are written out in the text, and "which chart suits this data?"
# questions need no chart, so those do not count.
NEEDS_FIGURE = re.compile(
    r"\b(cho|theo|dựa vào|căn cứ vào|quan sát|xem) (các )?(biểu đồ|đồ thị)\b"
    r"|\b(biểu đồ|đồ thị|hình|sơ đồ) (vẽ )?(bên|dưới|sau|trên|đây)\b"
    r"|\b(cho|quan sát|xem) hình (vẽ|\d)|\bnhư hình\b|\bhình vẽ\b",
    re.IGNORECASE,
)
DATA_TABLE = re.compile(r"bảng số liệu", re.IGNORECASE)
LATEX = re.compile(r"\\[a-zA-Z]+|\$")
QUESTION_PREFIX = re.compile(r"^\s*(?:c[âa]u|question)\s*\d{1,3}\s*[.:)\-]?\s*", re.IGNORECASE)
# An option at the start of a line: "A. text", "A) text", "B kỉ luật" (dot missing).
OPTION_LINE = re.compile(r"^\s*([A-D])\s*(?:[.:)]\s*|\s+)(.*)$")
# Later options on the same line: "A. 3 cm   B. 4 cm".
INLINE_OPTION = re.compile(r"\s+([B-D])\s*[.:)]\s+")
# Where an explanation names the answer: "Chọn đáp án D", "Đáp án: B", "Đáp án B chọn vì...".
# Not "Đáp án A loại vì..." (A is ruled out), which is why "đáp án X" alone does not count.
CHOICE_IN_EXPLANATION = re.compile(
    r"chọn\s*(?:đáp án|phương án|câu)?\s*:?\s*((?-i:[A-D]))\b"
    r"|đáp án\s*(?:đúng\s*)?(?:là|:)\s*((?-i:[A-D]))\b"
    r"|đáp án\s*((?-i:[A-D]))\s*(?:chọn|đúng)\b",
    re.IGNORECASE,
)
# The VietJack primary-math explanations name the key more loosely: "Đáp án B", "Đáp án cần chọn
# là B", "Đáp án đúng nhất trong các đáp án đã cho là B". Elimination ("Đáp án A sai") is rare there.
VIETJACK_KEY = re.compile(
    r"(?:đáp án[^.\n]{0,40}?(?:là|:)?|chọn(?:\s*đáp án)?|khoanh(?:\s*vào)?)\s*:?\s*((?-i:[A-D]))\b(?!\s*(?:loại|sai))",
    re.IGNORECASE,
)
# A fraction that was an image and got dropped when scraping: "chiều rộng bằng     chiều dài".
LOST_MATH = re.compile(
    r"\b(bằng|gấp|là|lấy|của|còn|thêm|bớt|đi|giảm|tăng)[ \t ]{3,}(?=[a-zà-ỹđ])", re.IGNORECASE
)
# Primary explanations often reveal a picture the question needs ("Quan sát hình vẽ ta thấy").
PICTURE_HINT = re.compile(r"\b(trong|ở|vào|quan sát|nhìn) (hình|tranh)\b|\bhình vẽ\b|\bbức tranh\b", re.IGNORECASE)


def clean(text):
    """NFC Unicode, no zero-width or control characters, single spaces."""
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"[\u200b-\u200f\ufeff\x00-\x08\x0b-\x1f]", " ", text)
    return " ".join(text.split())


def parse_question_text(text):
    """(stem, {letter: option}) from a question whose options are written inside it, or None.

    Options must appear in order A, B, C, D, each starting a line; a line may hold several options.
    """
    stem_lines, options, expected = [], {}, "A"
    for line in text.splitlines():
        match = OPTION_LINE.match(line)
        if match and match.group(1) == expected:
            rest = match.group(2)
            letter = expected
            # Split later options on the same line, still in order.
            while True:
                nxt = chr(ord(letter) + 1)
                inline = next((m for m in INLINE_OPTION.finditer(rest) if m.group(1) == nxt), None)
                if not inline:
                    break
                options[letter] = rest[:inline.start()]
                letter, rest = nxt, rest[inline.end():]
            options[letter] = rest
            expected = chr(ord(letter) + 1)
        elif options:
            if expected > "D" or OPTION_LINE.match(line):
                # Text after D, or an option out of order (a pasted duplicate): not trustworthy.
                return None
            last = list(options)[-1]
            options[last] += " " + line
        else:
            stem_lines.append(line)
    options = {k: clean(v) for k, v in options.items()}
    if list(options) != list("ABCD") or not all(options.values()):
        return None
    stem = clean(QUESTION_PREFIX.sub("", "\n".join(stem_lines)))
    return (stem, options) if stem else None


def label_flags(stem, options, has_image):
    flags = []
    text = stem + " " + " ".join(options.values())
    if has_image:
        flags.append("image")
    if NEEDS_ATLAS.search(stem):
        flags.append("atlas")
    if NEEDS_FIGURE.search(stem):
        flags.append("figure")
    if DATA_TABLE.search(stem):
        flags.append("data_table")  # flattened to one line; answerable but hard to read
    if LATEX.search(text):
        flags.append("latex")
    if len(set(options.values())) < len(options):
        flags.append("duplicate_options")
    return flags


# Flags that make a question unanswerable from its text, or untrustworthy.
BLOCKING = {"image", "atlas", "figure", "duplicate_options", "answer_mismatch", "unparsed", "no_passage",
            "lost_math", "no_key"}


def load_vnhsge():
    base = RAW / "VNHSGE/Dataset/VNHSGE-V/JSON format"
    for path in sorted(glob.glob(str(base / "*/*/*.json"))):
        split, subject = Path(path).parts[-3:-1]
        if subject == "Literature":  # essays, no options
            continue
        exam = Path(path).stem
        year = next(iter(re.findall(r"(20\d\d|\b\d\d)\b", exam)), None)
        for q in json.load(open(path, encoding="utf-8")):
            parsed = parse_question_text(unicodedata.normalize("NFC", q.get("Question", "")))
            answer = clean(q.get("Choice", "")).upper()
            explanation = clean(q.get("Explanation", ""))
            flags = []
            if parsed:
                stem, options = parsed
            else:
                stem, options = clean(q.get("Question", "")), {}
                flags.append("unparsed")
            flags += label_flags(stem, options, bool(q.get("Image_Question")))
            stated = {letter.upper() for m in CHOICE_IN_EXPLANATION.finditer(explanation)
                      for letter in m.groups() if letter}
            if stated and answer not in stated:
                flags.append("answer_mismatch")
            if subject == "English" and re.search(r"\bpassage\b|read the following", stem, re.I):
                # Reading questions in the JSON do not carry their passage.
                flags.append("no_passage")
            yield {
                "id": f"vnhsge/{q['ID']}",
                "source": "vnhsge",
                "source_split": split,
                "exam": exam,
                "level": "upper_secondary",
                "grade": 12,
                "subject": SUBJECTS[subject],
                "stem": stem,
                "options": options,
                "answer": answer,
                "explanation": explanation,
                "year": (f"20{year}" if year and len(year) == 2 else year),
                "flags": flags,
            }


def load_m3exam():
    base = RAW / "m3exam/data/text-question"
    for split in ("dev", "test"):
        path = base / f"vietnamese-questions-{split}.json"
        for i, q in enumerate(json.load(open(path, encoding="utf-8"))):
            options, flags = {}, []
            for raw in q.get("options", []):
                match = re.match(r"^\s*\(?([A-E])\s*[.:)]\s*(.*)$", raw, re.S)
                if match:
                    options[match.group(1)] = clean(match.group(2))
            if list(options) not in (list("ABCD"), list("ABC"), list("ABCDE")) or not all(options.values()):
                flags.append("unparsed")
            background = clean(" ".join(q.get("background_description") or []))
            stem = clean(q.get("question_text", ""))
            if background:
                stem = f"{background}\n{stem}"
            level, grade = M3_LEVELS[q["level"]]
            flags += label_flags(stem, options, q.get("need_image") == "yes")
            yield {
                "id": f"m3exam/{split}/{i}",
                "source": "m3exam",
                "source_split": split,
                "exam": f"m3exam-{q['level']}-{q.get('year')}",
                "level": level,
                "grade": grade,
                "subject": SUBJECTS.get(q.get("subject"), SUBJECTS.get(q.get("subject_category"), "khac")),
                "stem": stem,
                "options": options,
                "answer": clean(q.get("answer_text", "")).upper(),
                "explanation": "",
                "year": q.get("year"),
                "flags": flags,
            }


def load_vietjack_math():
    """Primary math, grades 1-5, from hllj/vi_grade_school_math_mcq (downloaded by download_vietjack_math.py).

    Each row is one worksheet with several problems. Fill-in-the-blank problems (no choices) are
    skipped; the key is read from the explanation.
    """
    path = RAW / "hllj_vi_grade_school_math_mcq.json"
    if not path.exists():
        return
    for sheet in json.load(open(path, encoding="utf-8")):
        for i, p in enumerate(sheet["problems"]):
            if len(p["choices"]) < 2:
                continue
            options, flags = {}, []
            for raw in p["choices"]:
                match = re.match(r"^\s*([A-E])\s*[.:)]\s*(.*)$", raw, re.S)
                if match:
                    options[match.group(1)] = clean(match.group(2))
            if list(options) != list("ABCD")[:len(options)] or len(options) < 2 or not all(options.values()):
                flags.append("unparsed")
            question = unicodedata.normalize("NFC", p["question"])
            explanation = clean(p["explanation"])
            stem = clean(QUESTION_PREFIX.sub("", question))
            keys = {k.upper() for k in VIETJACK_KEY.findall(explanation)}
            if not keys:
                flags.append("no_key")
            elif len(keys) > 1:
                flags.append("answer_mismatch")
            if LOST_MATH.search(question):
                flags.append("lost_math")
            if PICTURE_HINT.search(stem) or PICTURE_HINT.search(explanation):
                flags.append("figure")
            flags += label_flags(stem, options, False)
            yield {
                "id": f"vietjack_math/{sheet['id']}/{i}",
                "source": "vietjack_math",
                "source_split": "train",
                "exam": sheet["id"],
                "level": "primary",
                "grade": int(sheet["grade"]),
                "subject": "toan",
                "stem": stem,
                "options": options,
                "answer": next(iter(keys)) if len(keys) == 1 else "",
                "explanation": explanation,
                "year": None,
                "url": sheet.get("url"),
                "flags": flags,
            }


def norm_key(text):
    """Accent-insensitive key for spotting the same question written twice."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", text)


def clusters(rows):
    """Group ids of rows that share a stem or the same set of options (repeated across exam years).

    Splitting by cluster keeps a question and its near-copy out of train and test at the same time.
    """
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, row in enumerate(rows):
        keys = [("stem", norm_key(row["stem"]))]
        option_key = "|".join(sorted(norm_key(v) for v in row["options"].values()))
        if len(option_key) > 20:  # short option sets ("1/2/3/4") are shared by unrelated questions
            keys.append(("options", option_key))
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            else:
                seen[key] = i
    groups = defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(i)
    return list(groups.values())


def main():
    rows = list(load_vnhsge()) + list(load_m3exam()) + list(load_vietjack_math())
    loaded = Counter(r["source"] for r in rows)

    for row in rows:
        if row["answer"] not in row["options"] and not {"no_key", "unparsed", "answer_mismatch"} & set(row["flags"]):
            row["flags"].append("answer_not_in_options")
        row["license"] = LICENSES[row["source"]]
        row["flags"] = sorted(set(row["flags"]))
        row["usable"] = not (set(row["flags"]) & (BLOCKING | {"answer_not_in_options"}))

    # Exact duplicates: keep one, prefer a usable copy and the one with an explanation.
    groups = clusters(rows)
    kept, dropped_dupes = [], 0
    split_groups = []
    for group in groups:
        exact = defaultdict(list)
        for i in group:
            r = rows[i]
            exact[(norm_key(r["stem"]), tuple(sorted(norm_key(v) for v in r["options"].values())))].append(r)
        members = []
        for copies in exact.values():
            copies.sort(key=lambda r: (not r["usable"], not r["explanation"]))
            # Compare answer text, not letter: repeats across exams often shuffle the options.
            answers = {norm_key(c["options"][c["answer"]]) for c in copies if c["usable"]}
            best = copies[0]
            if len(answers) > 1:
                # Same question, different keys: no way to tell which is right without a human.
                best["flags"] = sorted(set(best["flags"]) | {"conflicting_keys"})
                best["usable"] = False
            best["duplicates"] = [c["id"] for c in copies[1:]]
            dropped_dupes += len(copies) - 1
            members.append(best)
        kept.extend(members)
        split_groups.append(members)

    # Split by cluster, stratified by the (level, subject) of the cluster's first question.
    rng = random.Random(SEED)
    by_slice = defaultdict(list)
    for members in split_groups:
        by_slice[(members[0]["level"], members[0]["subject"])].append(members)
    splits = {"train": [], "val": [], "test": []}
    for key in sorted(by_slice):
        bucket = by_slice[key]
        rng.shuffle(bucket)
        n = len(bucket)
        # Tiny slices go to test only, so they still get measured.
        n_test = max(1, round(n * TEST_SHARE)) if n >= 7 else n
        n_val = round(n * VAL_SHARE) if n >= 10 else 0
        for j, members in enumerate(bucket):
            name = "test" if j < n_test else "val" if j < n_test + n_val else "train"
            splits[name].extend(members)

    OUT.mkdir(exist_ok=True)
    for name, items in splits.items():
        items.sort(key=lambda r: r["id"])
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = build_report(loaded, kept, dropped_dupes, splits)
    (OUT / "REPORT.md").write_text(report, encoding="utf-8")
    print(report)


def build_report(loaded, kept, dropped_dupes, splits):
    lines = ["# Dataset report", "", f"Seed {SEED}. Generated by `finetune/build_dataset.py`.", ""]
    lines += ["## Sources", ""] + [f"- {s}: {n} questions loaded ({LICENSES[s]})" for s, n in loaded.items()]
    lines += ["", f"Exact duplicates removed: {dropped_dupes}. Kept: {len(kept)}.", ""]

    flags = Counter(f for r in kept for f in r["flags"])
    lines += ["## Flags (a question can have several)", "", "| flag | count | blocks training |", "|---|---|---|"]
    lines += [f"| {f} | {n} | {'yes' if f in BLOCKING | {'answer_not_in_options', 'conflicting_keys'} else 'no'} |"
              for f, n in flags.most_common()]

    lines += ["", "## Usable questions by split", "", "| level | subject | train | val | test |", "|---|---|---|---|---|"]
    table = defaultdict(Counter)
    for name, items in splits.items():
        for r in items:
            if r["usable"]:
                table[(r["level"], r["subject"])][name] += 1
    for (level, subject) in sorted(table, key=lambda k: (LEVELS.index(k[0]), k[1])):
        c = table[(level, subject)]
        lines.append(f"| {level} | {subject} | {c['train']} | {c['val']} | {c['test']} |")
    totals = {name: sum(r["usable"] for r in items) for name, items in splits.items()}
    lines.append(f"| **all** | | **{totals['train']}** | **{totals['val']}** | **{totals['test']}** |")

    answers = Counter(r["answer"] for items in splits.values() for r in items if r["usable"])
    lines += ["", "## Answer letter balance (usable)", ""] + [f"- {k}: {v}" for k, v in sorted(answers.items())]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
