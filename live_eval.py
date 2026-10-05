"""Measure the livestream chat moderator on labelled Vietnamese comments.

    .venv/bin/python live_eval.py

Prints the result for each comment, then accuracy, how many buyers were wrongly hidden and how
many bad comments slipped into the chat. Add real comments from your own lives to improve the test.
"""

from judge import live

# (expected kind, comment)
COMMENTS = [
    ("order", "chốt đơn 2 cái áo trắng size M nha shop"),
    ("order", "lay 1 cai mau den sdt 0912345678"),
    ("order", "em lấy 3 hộp ạ"),
    ("order", "chot"),
    ("order", "ib em nha shop"),
    ("order", "c ơi để cho e 1 bộ màu be"),
    ("price", "giá bao nhiêu vậy shop"),
    ("price", "cai nay bn tien"),
    ("price", "áo này nhiêu ạ"),
    ("price", "cho xin giá set này"),
    ("product", "còn size L không shop"),
    ("product", "có ship cod không ạ"),
    ("product", "chất vải gì vậy chị"),
    ("product", "freeship ko shop"),
    ("product", "e cao 1m6 nặng 50kg mặc size gì ạ"),
    ("complaint", "đặt hàng 1 tuần chưa nhận được"),
    ("complaint", "hàng giao bị rách, shop làm ăn kiểu gì vậy"),
    ("complaint", "nhắn tin mấy lần không ai trả lời"),
    ("spam", "kiếm tiền online 500k/ngày inbox mình"),
    ("spam", "ghé shop mình xem hàng giá rẻ hơn bit.ly/abc"),
    ("spam", "kb zalo 0987654321 nhận quà"),
    ("spam", "tuyển ctv làm việc tại nhà thu nhập cao"),
    ("toxic", "đồ lừa đảo, hàng dỏm"),
    ("toxic", "dm shop ngu vcl"),
    ("toxic", "con này xấu như ma"),
    ("toxic", "cút đi bán hàng gì mà như hạch"),
    ("chat", "chào shop ạ"),
    ("chat", "đẹp quá chị ơi"),
    ("chat", "haha vui quá"),
    ("chat", "hôm nay live lâu không chị"),
    ("chat", "cảm ơn shop nhiều"),
    ("chat", "chị mặc áo này xinh ghê"),
    # Not used while writing the rules.
    ("order", "+1 áo sơ mi xanh size L, giao Hà Nội"),
    ("order", "Mình mua 2 chai nhé, sđt 0905123456"),
    ("order", "chốt cho chị cái váy đỏ"),
    ("order", "hốt 1 em túi đen nha"),
    ("price", "set này bnh vậy c"),
    ("price", "váy hoa giá sao shop ơi"),
    ("product", "váy có màu xanh không c"),
    ("product", "hàng có sẵn không hay phải đặt trước"),
    ("product", "đổi size được không shop"),
    ("complaint", "mua rồi mà chưa thấy ai gọi xác nhận"),
    ("complaint", "áo về bị phai màu sau 1 lần giặt"),
    ("spam", "follow kênh mình đi mọi người, mình follow lại"),
    ("spam", "vay tiền nhanh không cần thế chấp, lh 0988111222"),
    ("toxic", "bán đắt như cắt cổ, đồ ăn cướp"),
    ("toxic", "nhìn mặt là biết lừa rồi"),
    ("chat", "chị ơi live tiếp mai nha"),
    ("chat", "xinh quá trời ơi 😍"),
    ("chat", "bà con vào đông vui quá"),
]
HELD_OUT_FROM = 32


def main():
    ok = held_ok = buyers_hidden = bad_shown = 0
    for i, (expected, comment) in enumerate(COMMENTS):
        r = live.classify(comment)
        right = r["kind"] == expected
        ok += right
        held_ok += right and i >= HELD_OUT_FROM
        buyers_hidden += expected in ("order", "price", "product", "chat") and r["hidden"]
        bad_shown += expected in live.BLOCKED_KINDS and not r["hidden"]
        mark = "✓" if right else "✗"
        print(f"{mark} {expected:9} -> {r['kind']:9} via {r['source']:7} "
              f"(laya neg {r['laya_negative']:.2f}) [{r['match'] or '-'}]  {comment[:45]}")

    n, held = len(COMMENTS), len(COMMENTS) - HELD_OUT_FROM
    print()
    print(f"Correct:            {ok}/{n} ({ok / n:.0%})")
    print(f"Unseen comments:    {held_ok}/{held}")
    print(f"Good comments hidden by mistake: {buyers_hidden}")
    print(f"Bad comments shown in chat:      {bad_shown}")


if __name__ == "__main__":
    main()
