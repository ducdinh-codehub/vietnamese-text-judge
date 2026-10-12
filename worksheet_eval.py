"""Measure how often Laya picks the right answer on multiple-choice test questions.

    .venv/bin/python worksheet_eval.py
    LAYA_ONNX=onnx/laya-multilingual-int8.onnx .venv/bin/python worksheet_eval.py   # quantized
    .venv/bin/python worksheet_eval.py vi-school     # checkpoint from finetune/train.py

Questions are given as text, so this measures Laya alone, without OCR mistakes. Compare the score
with chance: with 4 options, picking at random gets 25%. Add questions from your own worksheets.
"""

import sys
from collections import defaultdict

from judge import analyzer, worksheet

# (subject, language, question, options, correct letter)
QUESTIONS = [
    # math
    ("math", "en", "What is 7 x 8?", ["54", "56", "64", "48"], "B"),
    ("math", "en", "12 + 15 = ?", ["25", "27", "28", "37"], "B"),
    ("math", "en", "What is half of 50?", ["20", "25", "30", "100"], "B"),
    ("math", "en", "How many sides does a triangle have?", ["2", "3", "4", "5"], "B"),
    ("math", "vi", "5 x 6 bằng bao nhiêu?", ["30", "11", "36", "25"], "A"),
    ("math", "vi", "100 - 45 = ?", ["65", "55", "45", "35"], "B"),
    ("math", "vi", "Hình vuông có mấy cạnh?", ["3", "4", "5", "6"], "B"),
    ("math", "vi", "Số nào là số chẵn?", ["7", "13", "18", "21"], "C"),
    # science
    ("science", "en", "Which planet is closest to the Sun?", ["Venus", "Earth", "Mars", "Mercury"], "D"),
    ("science", "en", "Water boils at sea level at what temperature?", ["50°C", "100°C", "0°C", "200°C"], "B"),
    ("science", "en", "Which gas do plants absorb from the air?", ["Oxygen", "Nitrogen", "Carbon dioxide", "Helium"], "C"),
    ("science", "en", "Which organ pumps blood around the body?", ["Lungs", "Heart", "Liver", "Brain"], "B"),
    ("science", "vi", "Con vật nào sống dưới nước?", ["Con mèo", "Con cá", "Con gà", "Con chó"], "B"),
    ("science", "vi", "Nước đóng băng ở bao nhiêu độ C?", ["0 độ", "50 độ", "100 độ", "10 độ"], "A"),
    ("science", "vi", "Mặt Trời mọc ở hướng nào?", ["Tây", "Nam", "Bắc", "Đông"], "D"),
    ("science", "vi", "Cây xanh cần gì để quang hợp?", ["Bóng tối", "Ánh sáng", "Muối", "Đá"], "B"),
    # geography and history
    ("social", "en", "What is the capital of France?", ["Berlin", "Madrid", "Paris", "Rome"], "C"),
    ("social", "en", "Which is the largest ocean?", ["Atlantic", "Indian", "Arctic", "Pacific"], "D"),
    ("social", "en", "Which continent is Egypt in?", ["Asia", "Africa", "Europe", "South America"], "B"),
    ("social", "vi", "Thủ đô của Việt Nam là gì?", ["Hồ Chí Minh", "Đà Nẵng", "Hà Nội", "Huế"], "C"),
    ("social", "vi", "Sông nào chảy qua Hà Nội?", ["Sông Hồng", "Sông Hương", "Sông Hàn", "Sông Sài Gòn"], "A"),
    ("social", "vi", "Ngày Quốc khánh Việt Nam là ngày nào?", ["1/5", "2/9", "30/4", "1/1"], "B"),
    # language
    ("language", "en", "Choose the correct word: She ___ to school every day.", ["go", "goes", "going", "gone"], "B"),
    ("language", "en", "The opposite of 'hot' is:", ["warm", "cold", "big", "fast"], "B"),
    ("language", "en", "Which word is a noun?", ["run", "quickly", "table", "blue"], "C"),
    ("language", "en", "What is the plural of 'child'?", ["childs", "children", "childes", "child"], "B"),
    ("language", "vi", "Từ nào trái nghĩa với 'cao'?", ["dài", "thấp", "to", "rộng"], "B"),
    ("language", "vi", "Từ nào chỉ màu sắc?", ["chạy", "xanh", "bàn", "nhanh"], "B"),
    ("language", "vi", "Chọn từ viết đúng chính tả:", ["xinh đẹp", "sinh đẹp", "xing đẹp", "sinh đẹb"], "A"),
    # everyday knowledge
    ("general", "en", "How many days are in a week?", ["5", "6", "7", "8"], "C"),
    ("general", "en", "How many months are in a year?", ["10", "12", "11", "13"], "B"),
    ("general", "en", "What color is a ripe banana?", ["Blue", "Yellow", "Purple", "Black"], "B"),
    ("general", "vi", "Một tuần có mấy ngày?", ["5", "6", "7", "8"], "C"),
    ("general", "vi", "Con gì kêu 'meo meo'?", ["Con chó", "Con mèo", "Con bò", "Con vịt"], "B"),
    ("general", "vi", "Người ta dùng gì để viết lên bảng đen?", ["Phấn", "Kéo", "Thìa", "Lược"], "A"),
]


def main():
    checkpoint = sys.argv[1] if len(sys.argv) > 1 else "multilingual"
    analyzer._ensure_loaded(checkpoint)
    print(f"Backend: {analyzer.loaded_checkpoints()[checkpoint]['backend']}\n")

    total = correct = 0
    chance = 0.0
    picks = defaultdict(int)
    by = {"subject": defaultdict(lambda: [0, 0]), "language": defaultdict(lambda: [0, 0])}
    for subject, lang, stem, options, gold in QUESTIONS:
        q = {"stem": stem, "options": dict(zip(worksheet.LETTERS, options))}
        probs = worksheet.answer(q, checkpoint)
        pick = max(probs, key=probs.get)
        ok = pick == gold
        total += 1
        correct += ok
        chance += 1 / len(options)
        picks[pick] += 1
        for name, value in (("subject", subject), ("language", lang)):
            by[name][value][0] += ok
            by[name][value][1] += 1
        print(f"{'✓' if ok else '✗'} {subject:8} {lang}  pick={pick} ({probs[pick]:.2f}) gold={gold}  {stem[:50]}")

    print()
    print(f"Accuracy:  {correct}/{total} = {correct / total:.0%}   (chance {chance / total:.0%})")
    for name, groups in by.items():
        print(f"By {name}:  " + "  ".join(f"{k} {c}/{n}" for k, (c, n) in sorted(groups.items())))
    print("Picks:     " + "  ".join(f"{k} {picks[k]}" for k in sorted(picks)))


if __name__ == "__main__":
    main()
