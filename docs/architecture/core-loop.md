# Core Business Loop

Sản phẩm xoay quanh **2 vòng lặp** gặp nhau ở **Review**.

## Hai vòng lặp

```mermaid
flowchart TB
    cfo(["PERSONAL CFO"])
    cfo --> T0
    cfo --> B0

    subgraph tracking ["TRACKING LOOP"]
        T0["Liệt kê<br/>(nhập giao dịch)"] --> T1["Phân loại<br/>category x spending_type"]
        T1 --> T2["Ghi chép<br/>(lưu DB)"]
    end

    subgraph budgetloop ["BUDGET LOOP"]
        B0["Lập budget"] --> B1["Phân bổ tiền<br/>(envelope / 50-30-20 / PYF)"]
        B1 --> B2["Theo dõi thực tế<br/>Budget vs Actual"]
    end

    T2 --> R["REVIEW<br/>(tuần / tháng)"]
    B2 --> R
    R --> I["Insight / Action"]
    I --> A["Điều chỉnh tháng sau"]
    A -.-> T0
    A -.-> B0
```

## Vòng đời một tháng

```mermaid
flowchart TB
    inc["Nhận thu nhập"] --> pyf["Pay Yourself First<br/>trích saving + goal trước"]
    pyf --> bud["Tạo / xác nhận budget tháng"]
    bud --> track["Ghi chép chi tiêu hằng ngày"]
    track --> cls["Phân loại (AI đề xuất, user xác nhận)"]
    cls --> bva["Budget vs Actual (real-time)"]
    bva --> wr["Weekly Review (mỗi Thứ Hai)"]
    wr --> track
    wr --> mr["Monthly Review (đầu tháng sau)"]
    mr --> adv{"Budget Adjustment Advisor"}
    adv -->|"budget không thực tế"| bc["Điều chỉnh BUDGET"]
    adv -->|"hành vi lệch kế hoạch"| hc["Điều chỉnh HÀNH VI"]
    adv -->|"khoản bất thường 1 lần"| ok["Giữ nguyên"]
    bc --> next["Tháng tiếp theo"]
    hc --> next
    ok --> next
    next --> inc
```

## Feature nào phục vụ bước nào

| Bước | Feature | Phase |
|---|---|---|
| Liệt kê | Nhập thủ công, NL entry, OCR hoá đơn, import CSV, recurring | 1, 2, 13, 14, 12 |
| Phân loại | Category × spending_type, AI classifier học preference | 1, 2, 3 |
| Lập budget / Phân bổ | Budget engine 3 chiến lược, PYF + Goals | 4, 11 |
| Theo dõi thực tế | Budget vs Actual, Flexible zones, Calendar/forecast | 5, 9, 12 |
| Review | Weekly / Monthly review, reflection | 6, 7 |
| Insight / Action | Budget Adjustment Advisor, Financial Coach, semantic search, RAG, What-if | 8, 10, 15, 16, 17 |
