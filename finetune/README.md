# Fine-tuning Laya on Vietnamese school tests

Everything for training lives in this folder; the web app (`judge/`, `judge_site/`) does not import
it. The two meet at `checkpoints/laya-vi-school/` in the project root: `train.py` writes it and the
worksheet page loads it.

| File | What it does |
|---|---|
| `download_vietjack_math.py` | Downloads the primary math source into `data/raw/` |
| `build_dataset.py` | Cleans, labels, deduplicates and splits everything in `data/raw/` into `data/processed/` |
| `train.py` | Fine-tunes the multilingual checkpoint on `data/processed/` and saves `checkpoints/laya-vi-school/` |
| `SOURCES.md` | Research on other data sources, their licenses and robots.txt |

## Training data

Vietnamese multiple-choice questions from real exams, cleaned and labelled for fine-tuning and
measuring Laya. The data is not in git: VNHSGE is non-commercial and forbids
sharing modified copies, M3Exam states no license, and the primary math was scraped from VietJack, so
each person downloads it and builds it locally.

## Get the raw data

```bash
mkdir -p finetune/data/raw && cd finetune/data/raw
git clone --depth 1 https://github.com/Xdao85/VNHSGE.git
# M3Exam: password 12317, from https://github.com/DAMO-NLP-SG/M3Exam
curl -L "https://drive.usercontent.google.com/download?id=1eREETRklmXJLXrNPTyHxQ3RFdPhq_Nes&export=download&confirm=t" -o m3exam.zip
unzip -P 12317 m3exam.zip 'data/text-question/vietnamese*' -d m3exam
cd ../../..
python3 finetune/download_vietjack_math.py   # optional: primary math, grades 1-5 (~2 min)
python3 finetune/build_dataset.py
```

This writes `finetune/data/processed/{train,val,test}.jsonl` and `REPORT.md` (counts by level and subject).

## Sources

| Source | What | License |
|---|---|---|
| [VNHSGE](https://github.com/Xdao85/VNHSGE) | National high-school graduation exams and mock exams, grade 12 | CC BY-NC-ND 4.0 (stated in the paper) |
| [M3Exam](https://github.com/DAMO-NLP-SG/M3Exam) (Vietnamese part) | Exit exams for grades 5, 9 and 12 | None stated; treat as research only |
| [hllj/vi_grade_school_math_mcq](https://huggingface.co/datasets/hllj/vi_grade_school_math_mcq) (`vietjack_math`) | Math worksheets and tests, grades 1–5, scraped from VietJack | None; VietJack holds the copyright. Research only |

None allows commercial use: a Laya checkpoint fine-tuned on them should not be sold or used in a paid
product.

## What the build does

- **Parse**: splits VNHSGE questions into stem and options A–D; drops the literature essays and
  VietJack's fill-in-the-blank problems.
- **Clean**: Unicode NFC, strips "Câu 12:" prefixes, control characters and extra spaces.
- **Label**: `level` (primary, lower_secondary, upper_secondary), `grade` (1–5 for VietJack math; 5, 9 or
  12 for the exams: the exam's grade, not always the grade the topic is taught in) and `subject` (toan, ngu_van, tieng_viet,
  tieng_anh, vat_ly, hoa_hoc, sinh_hoc, lich_su, dia_ly, gdcd, khoa_hoc, lich_su_dia_ly).
- **Flag** questions the text alone cannot answer, and mark them `"usable": false`:
  `image`, `figure` (a chart or picture that is missing), `atlas` (needs the Atlat Địa lí Việt
  Nam), `no_passage` (English reading questions without their passage), `lost_math` (a fraction
  that was an image and vanished when VietJack was scraped).
- **Check answer keys**: VietJack keys are read from the explanation ("Đáp án cần chọn là B");
  `no_key` when there is none, `answer_mismatch` when the explanation names a different answer than
  the key or several answers, `conflicting_keys` when the same question has different answers in different exams,
  `answer_not_in_options`.
- **Deduplicate**: national exams reuse questions, often with options shuffled. Exact copies are
  merged (`duplicates` lists the ids), and near-copies (same stem, or same set of options) are kept in
  the same split, so a test question never has a copy in train.
- **Split** 75/10/15 train/val/test by (level, subject), seed 13. Slices with fewer than 7
  questions all go to test.

`latex` and `data_table` are informational: the question is answerable, but math notation or a
flattened table makes it harder for Laya.

## Training

```bash
.venv/bin/python finetune/train.py --eval-only              # score the original checkpoint
.venv/bin/python finetune/train.py --limit 300 --epochs 1   # smoke test, ~1 min
.venv/bin/python finetune/train.py                          # full run, ~45 min on an M3 Pro
```

It trains the encoder and decision head (the embedding table stays frozen), shuffles which letter
each answer sits under every epoch, keeps the epoch with the best val accuracy and fits a temperature
on val so the confidence the app shows stays calibrated. Gradient checkpointing and token-capped
batches (`--max-tokens`) keep GPU memory near 5 GB; lower `--max-tokens` if the Mac starts swapping.

First run: test accuracy 29.4% → 44.6% on 2,126 held-out questions (chance 26%). Grade 12 math did
not improve.
