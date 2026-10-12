"""Download hllj/vi_grade_school_math_mcq (primary math, grades 1-5) into finetune/data/raw/.

    python3 finetune/download_vietjack_math.py

Uses the Hugging Face dataset viewer API, 100 rows per request with a pause in between, because
huggingface.co itself often rate-limits plain downloads. The questions were scraped from VietJack
and carry no license: keep them local and use them for research only.
"""

import json
import time
import urllib.request
from pathlib import Path

DATASET = "hllj/vi_grade_school_math_mcq"
OUT = Path(__file__).resolve().parent / "data" / "raw" / "hllj_vi_grade_school_math_mcq.json"
ROWS = "https://datasets-server.huggingface.co/rows?dataset={}&config=default&split=train&offset={}&length=100"


def fetch(url):
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(url, timeout=60))
        except OSError as e:  # 429 / 502 from the viewer: back off and retry
            print(f"retry in {10 * (attempt + 1)}s: {e}")
            time.sleep(10 * (attempt + 1))
    raise SystemExit(f"giving up on {url}")


def main():
    rows, offset = [], 0
    while True:
        page = fetch(ROWS.format(DATASET, offset))
        batch = [r["row"] for r in page["rows"]]
        rows += batch
        offset += len(batch)
        print(f"{offset}/{page['num_rows_total']}")
        if not batch or offset >= page["num_rows_total"]:
            break
        time.sleep(1.5)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} worksheets, {sum(len(r['problems']) for r in rows)} problems -> {OUT}")


if __name__ == "__main__":
    main()
