"""Livestream chat moderator: sorts each viewer comment into the seller's queue, the chat, or hidden.

Laya on its own is a poor judge of short Vietnamese chat lines: asked "is this spam?" it says yes
to most orders and questions, and it misses common swear words. So the decision comes from rules
for the vocabulary of live selling ("chốt", "bn", "còn size L không", "kb zalo"...). Laya adds one
thing the rules cannot: its negative-sentiment score catches rude comments that use no listed word
("con này xấu như ma"). Rules run on accent-free text like scam.py, so unaccented comments match too.
"""

import re

from . import analyzer
from .scam import RULES as SCAM_RULES, original_span, plain_with_positions

# Shown in the chat with a badge and added to the seller's queue.
QUEUE_KINDS = {
    "order": {"label": "Chốt đơn", "emoji": "🛒"},
    "price": {"label": "Hỏi giá", "emoji": "💰"},
    "product": {"label": "Hỏi sản phẩm", "emoji": "❓"},
    # Kept out of the public chat but not lost: an unhappy buyer still needs an answer.
    "complaint": {"label": "Khiếu nại", "emoji": "⚠️"},
}
# Hidden from viewers. Moderators can still see them and put them back.
BLOCKED_KINDS = {
    "spam": {"label": "Spam", "emoji": "🚫"},
    "toxic": {"label": "Xúc phạm", "emoji": "🤬"},
    "negative": {"label": "Tiêu cực", "emoji": "👎"},
}
KINDS = {
    **QUEUE_KINDS,
    **BLOCKED_KINDS,
    "chat": {"label": "Trò chuyện", "emoji": "💬"},
    # Written by the shop owner or a moderator: never checked, never queued.
    "host": {"label": "Chủ phiên", "emoji": "🎙️"},
}
HIDDEN_KINDS = set(BLOCKED_KINDS) | {"complaint"}

LAYA_QUESTIONS = {
    "sentiment": {
        "type": "choice",
        "instructions": "What is the overall sentiment of this livestream comment?",
        "criteria": {
            "positive": "happy, praising, excited",
            "neutral": "factual, a question or an order",
            "negative": "rude, mocking, angry or critical",
        },
    },
}
# Laya must be this sure a comment is negative to hide it without any rule matching. High on
# purpose: hiding a buyer's message costs more than letting one rude line through.
NEGATIVE_AT = 0.85

_LINK_RULES = [pattern for rule_id, _, _, pattern in SCAM_RULES if rule_id in ("short_link", "suspicious_domain", "link")]

# (kind, pattern on accent-free lowercase text), checked in order: the first match decides.
# Blocking rules come first so "chốt đi đồ ngu" is hidden, and complaints come before orders so
# "đặt 2 cái mà chưa nhận" goes to the seller as a complaint.
RULES = [
    ("spam", "|".join(_LINK_RULES)),
    ("spam",
     r"ket ban|\bkb\b|\badd\b|(lien he|lh|nhan tin|goi|alo)\W+(zalo|sdt|so)|zalo\W+\d"
     r"|(ghe|qua|vao|ghe tham|xem) (shop|trang|kenh|page|live|nha) (minh|em|toi|tui|ben (minh|em))"
     r"|follow (minh|em|lai|cheo|kenh|trang|page|tiktok|fb|acc)|sub cheo|tuong tac cheo|kiem tien|thu nhap|(viec|job) (lam )?(online|nhe|tai nha)"
     r"|tuyen (ctv|dung|nguoi|si)|\bctv\b|trung thuong|nhan qua (mien phi|free)|(vay|cho vay) (tien|von|nhanh|online)"
     r"|nha cai|ca (do|cuoc)|tai xiu|\bcasino\b|\bx\d+ tai khoan|\d+k ?/ ?ngay"),
    ("toxic",
     r"\b(dm|dmm|dcm|dkm|dit|du ma|vcl|vkl|vl|vcc|clgt|cmm|cc|occ|vai lon)\b|\bdeo (biet|can|mua|hieu|thich|ai)|oc cho|oc heo|oc lon"
     r"|\b(do|may|thang|con|shop|bon|lu|oc|qua|vai|that)\W+(ngu|ngok|ngoc|dien|khung|dan|rac|cho|lon|dot|mat day|vo hoc)\b"
     r"|\bngu (vl|vcl|vai|the|qua|nhu|si|ngoc|dot|lam)|mat day|vo hoc|rac ruoi|\bcut\b|\bim (di|mom|miem)"
     r"|chet (di|me|cha)|cho chet|lua dao|\blua (dao|gat|dao)|treo dau de|\b(hang|do) (dom|fake|nhai|rac|tau)\b"
     r"|xau (nhu|vl|vcl|vai|kinh)|beo (nhu|vl|vcl)|\bbip\b"),
    ("complaint",
     r"chua (nhan|giao|thay|toi|den|ve|ship|gui|duoc giao)|(giao|gui|ship) (cham|sai|thieu|nham|lau|tre)"
     r"|\b(hang|ao|quan|do|sp|san pham)\W+(bi |thi )?(loi|hong|rach|vo|be|moc|sai|thieu|bung|xu)\b"
     r"|\b(bi|thi) (loi|hong|rach|vo|be|moc|bung|xu|phai mau|ra mau|giao sai|giao thieu)\b"
     r"|khong giong (hinh|anh|mo ta|tren live)|(doi|tra) hang|hoan tien|boc phot|that vong|te qua|chat luong (kem|te|qua te)"
     r"|lam an kieu gi|khong (ai )?(tra loi|rep|phan hoi)|seen (khong|ko|k) rep|(mua|dat) (\w+ )?(roi )?ma (chua|khong|ko)"),
    ("order",
     r"\bchot\b|\b(lay|mua|order|om|hot|giu)\W+(\w+\W+){0,3}?"
     r"(\d+|mot|hai|ba|bon|nam|cai|chiec|bo|hop|chai|doi|cap|set|lo|size|sz|mau|cho (em|e|minh|chi|c|anh|a|toi))\b"
     r"|\b(dat|lay|mua)\W+(\d+|mot|hai|ba)\b|\bib\b|\binbox\b|check (ib|tin nhan)|\b0\d{9}\b|\+?84\d{9}\b"
     r"|\b(e|em|minh|toi|c|chi|a|anh) (lay|mua|om|hot|dat|chot)\b|\bde (cho|lai cho) (em|e|minh|chi|c|anh|a|toi)\b"),
    ("price",
     r"bao nhieu|\b(bn|bnh|bnhieu|nhieu tien|bao tien|bao xu)\b|\bgia\W+(bao|bn|nhieu|sao|ca|ntn|bnh|re|si|ban|goc|nhu|the nao|\?)"
     r"|\b(xin|cho|bao|hoi|check|ib|bn|cho em|cho e|cho minh) gia\b|\bgia\W*\?|\bgia (sp|ao|quan|bo|set|cai|nay|do|mau|hop|chai)\b"
     r"|\b(nay|do|kia|cai|sp)\W+nhieu\b"),
    ("product",
     r"\bcon\b\W+(\w+\W+){0,2}?(hang|size|sz|mau|khong|ko|k|hok|hong|hk|hem)\b|het hang|\bsize\b|\bsz\b"
     r"|\bmau (gi|nao|khac|den|trang|do|xanh|hong|be|nau|vang|kem|xam)\b|chat (lieu|vai)|\bvai (gi|nay|day|co)|ship|freeship"
     r"|\bcod\b|giao (hang|tinh|ve|toi|den|o|ra|qua)|thanh toan|chuyen khoan|bao hanh|doi (size|mau)|xuat xu"
     r"|hang (auth|chinh hang|thai|qc|vnxk|that|nhap)|(mac|dung|deo|di) (vua|duoc|on)|\b\d+ ?kg\b|nang \d+|cao (1m|\d)"
     r"|\bco (mau|size|loai|ship|giam|sale|tang|qua|mien phi)|\bsale\b|giam gia|ma giam|voucher|\bfreesize\b"),
]


def find_kind(text):
    """The first rule that matches, and the user's own words that matched it."""
    plain, positions = plain_with_positions(text)
    for kind, pattern in RULES:
        match = re.search(pattern, plain)
        if match:
            return kind, original_span(text, positions, match)
    return None, None


def classify(text, checkpoint="multilingual"):
    text = text.strip()
    run = analyzer.predict({"body": text}, LAYA_QUESTIONS, checkpoint)
    negative = run["result"]["answers"]["sentiment"]["probabilities"]["negative"]

    kind, match = find_kind(text)
    source = "rules"
    if kind is None:
        kind, source = ("negative", "laya") if negative >= NEGATIVE_AT else ("chat", "default")

    return {
        "kind": kind,
        "label": KINDS[kind]["label"],
        "emoji": KINDS[kind]["emoji"],
        "hidden": kind in HIDDEN_KINDS,
        "queued": kind in QUEUE_KINDS,
        "match": match,
        "source": source,
        "laya_negative": negative,
        "latency_ms": run["load_ms"] + run["predict_ms"],
    }
