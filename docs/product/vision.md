# Product Vision — Personal CFO

## Định nghĩa sản phẩm

> **Một trợ lý tài chính cá nhân giúp người dùng hiểu tiền của mình đang đi đâu, lập kế hoạch sử dụng tiền, rồi định kỳ review để cải thiện hành vi tài chính.**

Không phải "AI ghi chép chi tiêu". Triết lý quản lý tài chính xuyên suốt:
**Track → Classify → Review → Budget → Adjust → Build discipline.**

## Người dùng mục tiêu

Người đi làm có thu nhập ổn định (lương tháng, có thể thêm freelance/bonus), muốn kiểm soát chi tiêu và tiết kiệm cho mục tiêu cụ thể, nhưng ngại ghi chép thủ công và không biết bắt đầu lập ngân sách từ đâu.

## Nguyên tắc sản phẩm

1. **Review là trung tâm, không phải dashboard.** Ghi chép mà không xem lại thì không thay đổi hành vi.
2. **Phân loại 2 chiều:** Category (ăn uống, đi lại...) × Spending type (Thiết yếu / Không thiết yếu / Bất thường).
3. **AI học cách user phân loại**, không áp đặt ("Tao coi giày là thiết yếu" → nhớ).
4. **Không ép một phương pháp budget:** hỗ trợ Envelope/Jars, 50/30/20 (tham khảo, không phải luật), Pay Yourself First.
5. **Actual > Budget không có nghĩa là sửa budget.** Phân biệt budget sai / hành vi sai / khoản bất thường 1 lần.
6. **Budget linh hoạt:** vùng 🟢 / 🟡 / 🔴 dựa trên dữ liệu của chính user.
7. **AI 3 tầng:** Observation → Explanation → Action. Không nhảy thẳng từ dữ liệu tới lời khuyên.
8. **Không phán xét.** ❌ "Bạn tiêu quá nhiều." ✅ "Chi tiêu tháng này cao hơn tháng trước 12%. Phần lớn mức tăng đến từ khoản mua laptop 15 triệu."
9. **AI không quyết định thay user** — đưa evidence, gợi ý, user quyết.
10. **Business logic không phụ thuộc AI.** DB, transaction, budget, actual/forecast là deterministic; AI đứng trên để hiểu input, phân tích, review, gọi tools, giải thích.

## Core loop

Xem sơ đồ chi tiết ở [core-loop.md](../architecture/core-loop.md).

```
INCOME → PAY YOURSELF FIRST → CREATE BUDGET → TRACK SPENDING → CLASSIFY
→ ACTUAL vs BUDGET → WEEKLY REVIEW → MONTHLY REVIEW
→ BEHAVIOR CHANGE | BUDGET CHANGE → NEXT MONTH
```

## Các khối tính năng

| Khối | Mô tả ngắn | Phase |
|---|---|---|
| Transaction Management | Thu/chi, nhập tay + câu tự nhiên ("ăn phở 55k", "Grab về nhà 45 nghìn", "nhận lương 25 triệu", "mua tai nghe 1tr5") | 1, 2 |
| Classification learning | AI đề xuất category/type, học từ chỉnh sửa của user | 3 |
| Budget Engine | 3 chiến lược, phân bổ theo nhóm/hũ | 4 |
| Budget vs Actual | Bảng so sánh, chỉ ra giao dịch gây vượt ("vượt 1.2tr, trong đó 900k từ 1 giao dịch") | 5 |
| Weekly Review ⭐ | What happened / Why / What to notice / Reflection | 6 |
| Monthly Review | Thu – Chi – Tiết kiệm, breakdown % theo spending type, so sánh tháng trước | 7 |
| Budget Adjustment | Budget sai hay hành vi sai? | 8 |
| Flexible Budget | Target / Comfort zone / Warning | 9 |
| Financial Coach | "Tao nên giảm khoản nào?" → evidence + gợi ý | 10 |
| Goals + PYF | "30 triệu vào tháng 3 để mua laptop" → 4.4tr/tháng, trích ngay khi nhận lương | 11 |
| Financial Calendar | Lương, tiền nhà, thẻ tín dụng, internet, goal saving theo ngày; dự báo dòng tiền | 12 |
| Receipt OCR, CSV import | Giảm công nhập liệu | 13, 14 |
| Semantic search, RAG | Tìm giao dịch theo nghĩa; kiến thức tài chính có trích nguồn | 15, 16 |
| What-if simulator | "Nếu giảm ăn ngoài 20% thì sao?" | 17 |

## Ví dụ Budget vs Actual mong muốn

| Category | Budget | Actual | Status |
|---|---|---|---|
| Nhà ở | 5.000.000 | 5.000.000 | ✓ |
| Ăn uống | 4.000.000 | 4.500.000 | +500.000 |
| Đi lại | 1.000.000 | 700.000 | ✓ |
| Mua sắm | 2.000.000 | 3.200.000 | +1.200.000 |
| Giải trí | 1.000.000 | 600.000 | ✓ |

AI không chỉ nói "Mua sắm vượt budget" mà: "Bạn vượt budget mua sắm 1.2 triệu. Trong đó 900k đến từ một giao dịch duy nhất."

## Ngoài phạm vi (hiện tại)

- Kết nối trực tiếp API ngân hàng / ví điện tử.
- Đầu tư, chứng khoán, crypto, thuế.
- Multi-user, chia sẻ ví gia đình (có thể xem xét sau Phase 18).
- Mobile app native (web responsive là đủ).
- Đa tiền tệ.
