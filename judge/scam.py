"""Scam and phishing checker: Laya's overall judgement combined with keyword rules that explain it.

Laya is good at a single "is this a scam?" question but unreliable on narrower ones (it says
"asks for an OTP" about ordinary family messages), so the reasons shown to the user come from rules.
Rules run on text with accents removed, so unaccented Vietnamese matches too.
"""

import re
import unicodedata

from . import analyzer

# Two wordings of the same question: the first rarely raises false alarms but misses some scams,
# the second catches more scams but also flags real bank notices. Their average does better than either.
LAYA_QUESTIONS = {
    "trick": {
        "type": "noul",
        "instructions": "Does the message try to trick the reader into giving money, passwords, OTP codes or personal data?",
    },
    "phishing": {
        "type": "noul",
        "instructions": "Is this message a scam or phishing attempt?",
    },
}
# How much Laya alone can push the risk up. Each rule adds its own weight on top.
LAYA_WEIGHT = 0.5
# Real banks remind you never to share codes; that halves the risk.
PROTECTIVE_FACTOR = 0.5

DANGER_AT = 0.7
SUSPICIOUS_AT = 0.4

# (id, weight, label shown to the user, pattern on accent-free lowercase text)
# Weights: how strongly the sign alone suggests a scam. Money transfers are common between family
# and friends, so they count less than asking for a code or installing an app.
RULES = [
    (
        "asks_secret", 0.7, "Yêu cầu gửi mã OTP, mật khẩu hoặc số thẻ",
        r"(gui|cung cap|nhap|doc|bao|cho biet|xac nhan|dien|xin|send|enter)\W+(\w+\W+){0,4}?"
        r"(otp|mat khau|mat ma|ma pin|cvv|ma xac (thuc|nhan)|so the|password)",
    ),
    (
        "short_link", 0.5, "Có đường link rút gọn (che giấu trang thật)",
        r"\b(bit\.ly|tinyurl\.com|goo\.gl|t\.ly|cutt\.ly|is\.gd|rb\.gy|s\.id|shorturl\.at|tiny\.cc|ow\.ly)/\S*",
    ),
    (
        "suspicious_domain", 0.45, "Có đường link giả mạo hoặc tên miền lạ",
        r"\b[a-z0-9-]+(\.[a-z0-9-]+)*\.(xyz|top|click|online|site|info|cc|icu|buzz|live|shop)\b(/\S*)?"
        r"|\b[a-z0-9]+-(xac-?(thuc|minh)|ho-?tro|cskh|verify|login|secure|support|express|online)[a-z0-9-]*\.[a-z]{2,}\b(/\S*)?",
    ),
    (
        "link", 0.25, "Có đường link",
        r"(https?://|www\.)\S+|\b[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|net|org|vn|info|xyz|top|online|site|click|app|link|shop|cc|me|io)\b(/\S*)?",
    ),
    (
        "install_app", 0.6, "Yêu cầu tải hoặc cài ứng dụng lạ",
        r"\.apk\b|(tai|cai|cai dat|download|install)\W+(ve\W+)?(ung dung|app)",
    ),
    (
        "money", 0.3, "Yêu cầu chuyển tiền, nạp tiền hoặc đóng phí",
        r"chuyen (khoan|tien)|nap (tien|\d)|dat coc|\bstk\b|so tai khoan|dong phi"
        r"|phi (van chuyen|kich hoat|ho so|xac minh|thu tuc|bao hiem)|transfer money",
    ),
    (
        "prize", 0.35, "Hứa hẹn quà, trúng thưởng hoặc việc nhẹ lương cao",
        r"trung thuong|nhan thuong|qua tang|tang qua|phan thuong|tri an khach hang|viec nhe luong cao"
        r"|kiem tien (tai nha|online)|thu nhap (cao|\d)|hoa hong|lam nhiem vu|\bctv\b|you (have )?won",
    ),
    (
        "authority", 0.2, "Tự xưng là ngân hàng, cơ quan nhà nước hoặc công ty lớn",
        r"ngan hang|vietcombank|techcombank|\bbidv\b|agribank|vietinbank|\bmb ?bank\b|tpbank|vpbank|sacombank"
        r"|acb\b|cong an|toa an|vien kiem sat|dien luc|\bevn\b|co quan thue|cuc thue|bao hiem xa hoi|\bbhxh\b"
        r"|buu dien|shopee|lazada|tiktok shop|\bmomo\b|zalopay|viettel|\bvnpt\b|mobifone",
    ),
    (
        "pressure", 0.3, "Đe dọa hoặc hối thúc phải làm ngay",
        r"trong (vong )?\d+ ?(gio|h|phut)\b|bi khoa|khoa tai khoan|tam khoa|dinh chi|ngay lap tuc|khan cap"
        r"|bi phat|bat giu|chuyen (tien |khoan )?gap|khoi to|cat dien|truy na|rua tien|lien quan (den|toi) vu an",
    ),
]
PROTECTIVE = (
    r"khong (duoc )?(chia se|cung cap|tiet lo|gui|dua)\W+(\w+\W+){0,4}?(ma|otp|mat khau)"
    r"|khong bao gio yeu cau|never share"
)

ADVICE = {
    "danger": [
        "Không bấm vào link, không gọi lại số trong tin nhắn.",
        "Tuyệt đối không gửi mã OTP, mật khẩu hay số thẻ cho bất kỳ ai.",
        "Không chuyển tiền. Nếu lo lắng, gọi tổng đài chính thức in trên thẻ hoặc website ngân hàng.",
        "Báo cáo lừa đảo tại canhbao.ncsc.gov.vn và cảnh báo người thân.",
    ],
    "suspicious": [
        "Chưa chắc chắn: đừng làm theo yêu cầu trong tin nhắn vội.",
        "Tự liên hệ tổ chức đó qua số điện thoại hoặc website chính thức để kiểm tra.",
        "Không nhập thông tin cá nhân vào link được gửi kèm.",
    ],
    "low": [
        "Chưa thấy dấu hiệu lừa đảo rõ ràng, nhưng công cụ có thể bỏ sót.",
        "Nếu tin nhắn đòi tiền, mã OTP hoặc cài ứng dụng, hãy luôn kiểm tra lại.",
    ],
}


def _plain_char(ch):
    ch = ch.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")


def normalize(text):
    """Lowercase and strip Vietnamese accents: "Chuyển khoản" -> "chuyen khoan"."""
    return "".join(_plain_char(ch) for ch in text)


def plain_with_positions(text):
    """normalize(text), plus the index in `text` that each of its characters came from."""
    plain, positions = [], []
    for i, ch in enumerate(text):
        for c in _plain_char(ch):
            plain.append(c)
            positions.append(i)
    return "".join(plain), positions


def original_span(text, positions, match):
    """The user's own words (with accents) behind a match on the plain text."""
    # End where the next plain character starts, so accents typed as separate marks stay attached.
    end = positions[match.end()] if match.end() < len(positions) else len(text)
    return text[positions[match.start()]:end].strip()


def find_signals(text):
    """Rules that match, each with the matched words from the user's own text."""
    plain, positions = plain_with_positions(text)
    signals = []
    for rule_id, weight, label, pattern in RULES:
        match = re.search(pattern, plain)
        if not match:
            continue
        if rule_id == "link" and any(s["id"] in ("short_link", "suspicious_domain") for s in signals):
            continue
        snippet = original_span(text, positions, match)
        signals.append({"id": rule_id, "weight": weight, "label": label, "match": snippet.strip()})
    return signals, bool(re.search(PROTECTIVE, plain))


def level(risk):
    if risk >= DANGER_AT:
        return "danger"
    if risk >= SUSPICIOUS_AT:
        return "suspicious"
    return "low"


def combine(laya_score, signals, protective):
    """Risk 0-1: each piece of evidence independently removes part of the chance it is safe."""
    safe = 1 - LAYA_WEIGHT * laya_score
    for signal in signals:
        safe *= 1 - signal["weight"]
    risk = 1 - safe
    return risk * PROTECTIVE_FACTOR if protective else risk


def check(body, checkpoint="multilingual"):
    body = body.strip()
    run = analyzer.predict({"body": body}, LAYA_QUESTIONS, checkpoint)
    answers = run["result"]["answers"]
    laya = {qid: answers[qid]["noul"] for qid in LAYA_QUESTIONS}
    laya_score = sum(laya.values()) / len(laya)

    signals, protective = find_signals(body)
    risk = combine(laya_score, signals, protective)
    verdict = level(risk)
    return {
        "verdict": verdict,
        "risk": risk,
        "laya_score": laya_score,
        "laya": laya,
        "signals": signals,
        "protective": protective,
        "advice": ADVICE[verdict],
        "latency_ms": run["load_ms"] + run["predict_ms"],
        "checkpoint": run["model"],
    }
