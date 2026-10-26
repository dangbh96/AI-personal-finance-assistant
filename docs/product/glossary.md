# Glossary — Thuật ngữ thống nhất

Mọi code, API, DB, prompt và tài liệu **phải** dùng đúng tên trong cột "Tên trong code".

## Phân loại giao dịch

| Tiếng Việt (UI) | English | Tên trong code | Ghi chú |
|---|---|---|---|
| Thu nhập | Income | `direction = "income"` | |
| Chi tiêu | Expense | `direction = "expense"` | |
| Danh mục | Category | `Category`, `category_id` | Ăn uống, Đi lại, Nhà ở... |
| Loại chi tiêu | Spending type | `spending_type` | Chỉ áp dụng cho expense; income = `null` |
| Thiết yếu | Essential | `essential` | Tiền nhà, điện nước, đi làm... |
| Không thiết yếu | Non-essential | `non_essential` | Netflix, mua sắm, ăn ngoài... |
| Bất thường | Irregular | `irregular` | Sửa laptop đột xuất, viện phí, mua đồ lớn 1 lần |
| Nguồn nhập | Source | `source` | `manual`, `nl`, `receipt`, `import`, `recurring` |

## Danh mục mặc định (seed ở Phase 1)

| Tên UI | slug | `default_spending_type` |
|---|---|---|
| Nhà ở | `housing` | essential |
| Ăn uống | `food` | essential |
| Đi lại | `transport` | essential |
| Hoá đơn & tiện ích | `utilities` | essential |
| Sức khoẻ | `health` | essential |
| Giáo dục | `education` | essential |
| Mua sắm | `shopping` | non_essential |
| Giải trí | `entertainment` | non_essential |
| Điện tử | `electronics` | non_essential |
| Quà tặng & hiếu hỉ | `gifts` | non_essential |
| Khác | `other` | non_essential |
| Lương | `salary` | — (income) |
| Freelance | `freelance` | — (income) |
| Thưởng | `bonus` | — (income) |
| Thu nhập khác | `other_income` | — (income) |

`default_spending_type` chỉ là gợi ý ban đầu; user/AI có thể chọn khác cho từng giao dịch.

## Budget

| Tiếng Việt | English | Tên trong code |
|---|---|---|
| Ngân sách | Budget | `Budget` (1 budget / tháng, `period_month` = ngày 1 của tháng) |
| Phân bổ | Allocation | `BudgetAllocation` |
| Chiến lược ngân sách | Budget strategy | `strategy` |
| Phương pháp hũ / phong bì | Envelope / Jars | `strategy = "envelope"`, `jar_name` (preset: `Essential` Thiết yếu, `Fun` Vui chơi, `Shopping` Mua sắm, `Saving` Tiết kiệm, `Unexpected` Dự phòng) |
| 50/30/20 | 50/30/20 rule | `strategy = "fifty_thirty_twenty"` |
| Trả cho mình trước | Pay Yourself First | `strategy = "pyf"` |
| Nhóm ngân sách | Allocation group | `group`: `essential` (Thiết yếu), `wants` (Mong muốn), `savings` (Tiết kiệm), `irregular` (Bất thường) |
| Thực tế | Actual | `actual` |
| Chênh lệch | Variance | `variance = actual - planned` (dương = vượt) |
| Vùng an toàn | Comfort zone | `comfort_low`, `comfort_high` |
| Ngưỡng cảnh báo | Warning threshold | `warning_threshold` |
| Trạng thái vùng | Zone status | `zone`: `normal` 🟢, `attention` 🟡, `review_needed` 🔴 |

## Review & AI

| Tiếng Việt | English | Tên trong code |
|---|---|---|
| Review tuần | Weekly review | `WeeklyReview`, tuần bắt đầu Thứ Hai (`week_start`) |
| Review tháng | Monthly review | `MonthlyReview` (`month`) |
| Nhìn lại / Chia sẻ | Reflection | `ReflectionAnswer` | UI dùng “Nhìn lại” cho thao tác, “Chia sẻ” cho câu trả lời |
| Quan sát / Giải thích / Hành động | Observation / Explanation / Action | `observation`, `explanation`, `action` (3 tầng AI) |
| Tư vấn điều chỉnh ngân sách | Budget advice | `BudgetAdvice`, `verdict` |
| Kết luận tư vấn | Verdict | `adjust_budget`, `adjust_behavior`, `one_off`, `on_track` |
| Sở thích phân loại | Classification preference | `ClassificationPreference` |
| Trợ lý tài chính | Financial Coach | `coach` (LangGraph agent) |

## Goal, lịch, nhập liệu

| Tiếng Việt | English | Tên trong code |
|---|---|---|
| Mục tiêu tiết kiệm | Goal | `Goal` |
| Khoản góp mục tiêu | Goal contribution | `GoalContribution` |
| Khoản định kỳ | Recurring transaction | `RecurringTransaction`, `frequency`: `weekly`, `monthly`, `yearly`; kỳ tới `next_due_on` |
| Đề xuất định kỳ | Recurring suggestion | `RecurringSuggestion` (phát hiện từ lịch sử, user xác nhận mới tạo) |
| Dự báo dòng tiền | Cashflow forecast | `forecast` (`projected_balance` theo ngày) |
| Số dư đầu (user nhập) | Starting balance | `starting_balance`, `starting_balance_on` |
| Ngưỡng cảnh báo số dư thấp | Low-balance threshold | `low_balance_threshold`, `low_balance_warning_day` |
| Hoá đơn (ảnh) | Receipt | `Receipt` |
| Lô import | Import batch | `ImportBatch` |
| Kịch bản giả định | What-if scenario | `Scenario` |

## Tiền tệ

- Tiền lưu dạng **số nguyên đồng (BIGINT)**, không dùng float. Xem [ADR-007](../architecture/decisions/ADR-007-money-as-integer-vnd.md).
- Cách viết tắt user hay dùng và AI phải hiểu: `55k` = 55,000; `1tr5` / `1.5tr` / `1 triệu rưỡi` = 1,500,000; `25 triệu` = 25,000,000; `2 lít` (slang) = 200,000; `1 củ` = 1,000,000.
- Hiển thị: `1.500.000 ₫` (locale `vi-VN`).
