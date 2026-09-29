import sys
import time

from laya import Router

router = Router(default="multilingual")

# Mock Vietnamese support tickets, each with the answers a human would give.
# expected: department (choice), urgency (score index 0-2), churn (True/False)
MOCK_TICKETS = [
    {
        "state": {
            "subject": "Bị trừ tiền hai lần",
            "body": "Tháng 3 công ty tôi bị tính phí hai lần. Vui lòng hoàn tiền ngay hôm nay, nếu không chúng tôi sẽ hủy dịch vụ.",
        },
        "expected": {"department": "billing", "urgency": 2, "churn": True},
    },
    {
        "state": {
            "subject": "Xin hóa đơn VAT",
            "body": "Chào anh chị, cho em xin hóa đơn VAT của tháng trước để gửi kế toán nhé. Không gấp ạ.",
        },
        "expected": {"department": "billing", "urgency": 0, "churn": False},
    },
    {
        "state": {
            "subject": "Thẻ tín dụng bị từ chối",
            "body": "Tôi không thanh toán được gói năm, thẻ Visa bị từ chối liên tục. Gói của tôi hết hạn vào thứ Sáu này.",
        },
        "expected": {"department": "billing", "urgency": 1, "churn": False},
    },
    {
        "state": {
            "subject": "Hệ thống sập toàn bộ",
            "body": "Từ 8 giờ sáng toàn bộ nhân viên không đăng nhập được, báo lỗi 500. Cả công ty đang ngừng làm việc!",
        },
        "expected": {"department": "technical", "urgency": 2, "churn": False},
    },
    {
        "state": {
            "subject": "Ứng dụng chạy chậm",
            "body": "Mấy hôm nay app trên điện thoại mở hơi chậm, khoảng 5-6 giây mới vào được. Mọi người xem giúp khi rảnh nhé.",
        },
        "expected": {"department": "technical", "urgency": 0, "churn": False},
    },
    {
        "state": {
            "subject": "Lỗi xuất báo cáo",
            "body": "Khi bấm xuất báo cáo Excel thì file bị trống. Chúng tôi cần nộp báo cáo này vào tuần sau.",
        },
        "expected": {"department": "technical", "urgency": 1, "churn": False},
    },
    {
        "state": {
            "subject": "Quá thất vọng",
            "body": "Lỗi đồng bộ dữ liệu lần thứ ba trong tháng rồi. Nếu tuần này không sửa xong, chúng tôi sẽ chuyển sang nhà cung cấp khác.",
        },
        "expected": {"department": "technical", "urgency": 2, "churn": True},
    },
    {
        "state": {
            "subject": "Hỏi về tính năng mới",
            "body": "Bên mình có kế hoạch hỗ trợ tiếng Việt cho phần giao diện quản trị không ạ? Chỉ hỏi để tham khảo thôi.",
        },
        "expected": {"department": "other", "urgency": 0, "churn": False},
    },
    {
        "state": {
            "subject": "Đổi người phụ trách tài khoản",
            "body": "Chị Lan đã nghỉ việc, nhờ bên bạn chuyển quyền quản trị tài khoản sang anh Minh giúp mình.",
        },
        "expected": {"department": "other", "urgency": 1, "churn": False},
    },
    {
        "state": {
            "subject": "Muốn hủy hợp đồng",
            "body": "Chúng tôi đã quyết định không gia hạn hợp đồng năm sau. Vui lòng hướng dẫn thủ tục hủy và xuất dữ liệu.",
        },
        "expected": {"department": "other", "urgency": 1, "churn": True},
    },
    {
        "state": {
            "subject": "cảm ơn team",
            "body": "cảm ơn các bạn đã hỗ trợ nhanh hôm qua nha, mọi thứ chạy ngon rồi :)",
        },
        "expected": {"department": "other", "urgency": 0, "churn": False},
    },
    {
        "state": {
            "subject": "gấp!!! ko thanh toan dc",
            "body": "khach hang cua minh ko thanh toan dc qua cong VNPay tu sang toi gio, mat don lien tuc, xu ly gap giup",
        },
        "expected": {"department": "technical", "urgency": 2, "churn": False},
    },
]

QUESTIONS_VI = {
    "department": {
        "type": "choice",
        "instructions": "Bộ phận nào nên xử lý yêu cầu này?",
        "criteria": {
            "billing": "hóa đơn, thanh toán, hoàn tiền",
            "technical": "lỗi, sự cố, gián đoạn dịch vụ",
            "other": "các vấn đề khác",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "Yêu cầu này khẩn cấp đến mức nào?",
        "criteria": ["bình thường", "sớm", "rất gấp, đang bị chặn"],
    },
    "churn": {
        "type": "noul",
        "instructions": "Khách hàng có ý định hủy dịch vụ hoặc chuyển sang nhà cung cấp khác không?",
    },
}

QUESTIONS_EN = {
    "department": {
        "type": "choice",
        "instructions": "Đội nào trong công ty sẽ xử ?",
        "criteria": {
            "billing": "invoices, payments, refunds",
            "technical": "bugs, outages, errors",
            "other": "everything else",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is the request?",
        "criteria": ["routine", "soon", "blocking"],
    },
    "churn": {
        "type": "noul",
        "instructions": "Does the customer intend to cancel or switch to another provider?",
    },
}

URGENCY_LABELS = ["routine", "soon", "blocking"]


def run(questions, label):
    print(f"\n=== Questions in {label} ===")
    print(f"{'#':>2}  {'dept (pred/exp)':<22} {'conf':>5}  {'urgency (pred/exp)':<20} {'churn P':>7}  {'ms':>5}")

    hits = {"department": 0, "urgency": 0, "churn": 0}
    latencies = []
    for i, ticket in enumerate(MOCK_TICKETS, 1):
        start = time.perf_counter()
        result = router.predict(ticket["state"], questions, model="multilingual")
        ms = (time.perf_counter() - start) * 1000
        latencies.append(ms)

        answers = result["answers"]
        expected = ticket["expected"]

        dept = answers["department"]["choice"]
        dept_conf = answers["department"]["answer_confidence"]
        urgency = round(answers["urgency"]["score"])
        churn_p = answers["churn"]["noul"]

        hits["department"] += dept == expected["department"]
        hits["urgency"] += urgency == expected["urgency"]
        hits["churn"] += (churn_p >= 0.5) == expected["churn"]

        mark = lambda ok: "✓" if ok else "✗"
        print(
            f"{i:>2}  {mark(dept == expected['department'])} {dept:<9}/{expected['department']:<9}"
            f" {dept_conf:>5.2f}"
            f"  {mark(urgency == expected['urgency'])} {URGENCY_LABELS[urgency]:<8}/{URGENCY_LABELS[expected['urgency']]:<8}"
            f"  {mark((churn_p >= 0.5) == expected['churn'])} {churn_p:>5.2f}"
            f"  {ms:>5.0f}"
        )

    n = len(MOCK_TICKETS)
    print(f"Routed to: {result['routing']['model']}  ({result['routing']['reason']})")
    print("Accuracy:  " + "  ".join(f"{k} {v}/{n} ({v / n:.0%})" for k, v in hits.items()))
    # The first call includes model loading, so report it separately.
    warm = sorted(latencies[1:])
    print(f"Latency:   first {latencies[0]:.0f} ms, median {warm[len(warm) // 2]:.0f} ms, max {warm[-1]:.0f} ms")


if __name__ == "__main__":
    # python main.py      -> Vietnamese and English instructions, side by side
    # python main.py vi   -> Vietnamese instructions only
    # python main.py en   -> English instructions only
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("vi", "both"):
        run(QUESTIONS_VI, "Vietnamese")
    if mode in ("en", "both"):
        run(QUESTIONS_EN, "English")
