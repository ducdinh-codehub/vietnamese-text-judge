"""Measure the scam checker on labelled Vietnamese messages.

    .venv/bin/python scam_eval.py

A scam counts as caught when it is rated "suspicious" or "danger". A normal message counts as a
false alarm when it is rated "danger" or "suspicious". Add your own real messages to improve the test.
"""

from judge import scam

# (is_scam, message)
MESSAGES = [
    # scams
    (True, "Tài khoản ngân hàng của quý khách sẽ bị khóa trong 24 giờ. Vui lòng bấm vào link bit.ly/xacminh và nhập mật khẩu cùng mã OTP để xác minh."),
    (True, "Chúc mừng bạn đã trúng thưởng iPhone 15 từ Shopee! Vui lòng chuyển 500.000đ phí vận chuyển vào STK 0123456789 để nhận quà."),
    (True, "Bộ Công an thông báo: bạn liên quan đến vụ án rửa tiền. Gọi ngay 0987654321 để được hướng dẫn, nếu không sẽ bị bắt giữ."),
    (True, "Tuyển CTV làm việc tại nhà, việc nhẹ lương cao 500k-2tr/ngày, chỉ cần điện thoại. Nạp 200k để kích hoạt nhiệm vụ."),
    (True, "Điện lực thông báo: quý khách nợ tiền điện, sẽ cắt điện trong hôm nay. Tải ứng dụng tại evn-vn.apk để thanh toán."),
    (True, "tai khoan cua ban bi khoa, vui long gui ma OTP vua nhan duoc de mo khoa"),
    (True, "Con đang bị tai nạn ở bệnh viện, mẹ chuyển gấp 20 triệu vào số tài khoản này cho bạn con nhé, con hết pin rồi."),
    (True, "[VCB] Tài khoản của quý khách đã đăng nhập trên thiết bị lạ. Nếu không phải bạn, truy cập vcb-xacthuc.com để hủy ngay."),
    (True, "Cơ quan BHXH thông báo: hồ sơ của bạn chưa được cập nhật định danh. Cài đặt ứng dụng VNeID-hotro để tránh bị phạt."),
    (True, "Bạn có một bưu phẩm bị giữ lại do sai địa chỉ. Vui lòng cập nhật tại ghn-express.top và thanh toán phí 15.000đ."),
    (True, "Em ơi, em nhận làm nhiệm vụ thả tim TikTok không, hoa hồng 30% mỗi đơn, rút tiền ngay trong ngày."),
    (True, "Chị ơi cho em xin mã OTP vừa gửi về máy chị với, em gửi nhầm số điện thoại ạ."),
    # normal messages
    (False, "Mẹ ơi tối nay con về muộn, mẹ cứ ăn cơm trước nhé."),
    (False, "Mã OTP của bạn là 482913. Không chia sẻ mã này với bất kỳ ai, kể cả nhân viên ngân hàng."),
    (False, "Đơn hàng #A123 của bạn đang được giao, shipper sẽ gọi trong hôm nay."),
    (False, "Anh ơi chiều nay họp lúc 3 giờ ở phòng 2 nhé, nhớ mang laptop."),
    (False, "Vietcombank: TK 0071xxx +5,000,000 VND luc 10:22. SD: 12,340,000 VND. ND: luong thang 9"),
    (False, "Cảm ơn chị đã mua hàng, shop gửi tặng mã giảm giá 10% cho lần sau ạ."),
    (False, "Tối nay đi ăn lẩu không mày? Tao đặt bàn 7h rồi."),
    (False, "Nhà mình tháng này tiền điện 850k nhé, em chuyển khoản cho chị trước thứ 6 nha."),
    (False, "Lịch khám của bạn tại Bệnh viện Bạch Mai: 8h30 ngày 12/10. Vui lòng đến trước 15 phút."),
    (False, "Chúc mừng sinh nhật bạn! Chúc bạn tuổi mới nhiều sức khỏe và niềm vui."),
    (False, "Thầy nhắc cả lớp nộp bài tập lớn trước 23h59 Chủ nhật qua hệ thống của trường."),
    (False, "Viettel thông báo: gói cước của quý khách sẽ gia hạn vào ngày 01/10. Soạn HUY gửi 191 để hủy."),
]

LABEL = {"danger": "NGUY HIỂM", "suspicious": "ĐÁNG NGỜ", "low": "an toàn?"}


def main():
    caught = false_alarms = 0
    scams = sum(is_scam for is_scam, _ in MESSAGES)
    normal = len(MESSAGES) - scams
    for is_scam, message in MESSAGES:
        result = scam.check(message)
        flagged = result["verdict"] != "low"
        caught += is_scam and flagged
        false_alarms += (not is_scam) and flagged
        ok = "✓" if flagged == is_scam else "✗"
        reasons = ", ".join(s["id"] for s in result["signals"]) or "-"
        print(f"{ok} {'scam  ' if is_scam else 'normal'} {LABEL[result['verdict']]:10} "
              f"risk={result['risk']:.2f} laya={result['laya_score']:.2f} [{reasons}]  {message[:50]}")

    print()
    print(f"Scams caught:   {caught}/{scams}")
    print(f"False alarms:   {false_alarms}/{normal}")
    print(f"Accuracy:       {(caught + normal - false_alarms) / len(MESSAGES):.0%}")


if __name__ == "__main__":
    main()
