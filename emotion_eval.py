"""Measure the emotion checker on labelled Vietnamese messages.

    .venv/bin/python emotion_eval.py

Prints the result for each message, then accuracy for the final answer and for Laya alone.
Add your own real messages to improve the test.
"""

from judge import emotion

# (expected emotion, message)
MESSAGES = [
    ("happy", "Hôm nay mình đậu đại học rồi!!! Vui quá trời luôn á"),
    ("happy", "Cuối tuần được đi Đà Lạt với cả nhà, háo hức ghê"),
    ("grateful", "Cảm ơn anh đã giúp em sửa xe hôm qua, không có anh chắc em đi bộ về rồi"),
    ("grateful", "Con cảm ơn bố mẹ đã luôn ủng hộ con"),
    ("love", "Anh nhớ em nhiều lắm, mong đến cuối tuần để gặp em"),
    ("love", "Thương con gái của mẹ nhất trên đời"),
    ("angry", "Giao hàng trễ 5 ngày mà còn thái độ với khách, quá bực mình!"),
    ("angry", "Đã nói bao nhiêu lần rồi mà vẫn không sửa, tức thật sự"),
    ("sad", "Con mèo nhà mình mất rồi, buồn quá không muốn làm gì"),
    ("sad", "Thi trượt rồi, cố gắng cả năm mà vẫn không được"),
    ("worried", "Mai phỏng vấn mà run quá, sợ trả lời không được"),
    ("worried", "Mẹ nhập viện từ chiều, con lo lắm không biết có sao không"),
    ("surprised", "Trời ơi sao anh lại ở đây? Bất ngờ quá!"),
    ("surprised", "Không thể tin được, đội mình thắng 5-0!"),
    ("neutral", "Cuộc họp dời sang 3 giờ chiều thứ Năm tại phòng 201."),
    ("neutral", "Hóa đơn tháng 9 gồm tiền điện 450k và tiền nước 120k."),
    ("angry", "do lam an kieu gi ma giao sai hang hoai vay, chan that su"),
    ("sad", "hom nay that la mot ngay te hai, chang ai hieu minh ca"),
    # Not used while writing the word list.
    ("happy", "Được tăng lương rồi mọi người ơi 🎉 tối nay mình khao cả phòng nhé"),
    ("happy", "Bé nhà mình biết đi rồi, cả nhà mừng lắm"),
    ("grateful", "Em rất biết ơn cô đã tận tình chỉ bảo em suốt ba năm qua."),
    ("love", "Chúc ngủ ngon nha, yêu em nhiều ❤️"),
    ("angry", "Gọi tổng đài 10 lần không ai bắt máy, dịch vụ gì mà tệ vậy, bực không chịu nổi"),
    ("angry", "Hàng xóm hát karaoke tới 2 giờ sáng, điên mất thôi"),
    ("sad", "Bạn thân chuyển ra nước ngoài rồi, từ nay chẳng còn ai đi cà phê cùng"),
    ("sad", "Mình cố gắng hết sức mà sếp vẫn không ghi nhận, thấy nản quá"),
    ("worried", "Con sốt 39 độ từ tối, uống thuốc rồi mà chưa hạ, sợ quá"),
    ("worried", "Tháng này chưa có tiền đóng học cho con, không biết xoay xở thế nào"),
    ("surprised", "Ủa, sao hôm nay quán đóng cửa vậy? Mọi khi mở tới khuya mà"),
    ("neutral", "Nhắc lịch: nộp báo cáo quý 3 trước ngày 15/10."),
    ("neutral", "Xe buýt số 32 chạy từ 5h30 đến 21h, 15 phút một chuyến."),
    ("neutral", "Em gửi anh file thiết kế bản cuối trong email nhé."),
]


def main():
    final_ok = laya_ok = 0
    for expected, message in MESSAGES:
        r = emotion.check(message)
        final_ok += r["emotion"] == expected
        laya_ok += r["laya_emotion"] == expected
        mark = "✓" if r["emotion"] == expected else "✗"
        words = "; ".join(w for item in r["words"] for w in item["words"]) or "-"
        print(f"{mark} {expected:9} -> {r['emotion']:9} {r['confidence']:.2f} "
              f"(laya {r['laya_emotion']:9} via {r['source']:7}) [{words}]  {message[:40]}")

    n = len(MESSAGES)
    print()
    print(f"Final answer: {final_ok}/{n} ({final_ok / n:.0%})")
    print(f"Laya alone:   {laya_ok}/{n} ({laya_ok / n:.0%})")


if __name__ == "__main__":
    main()
