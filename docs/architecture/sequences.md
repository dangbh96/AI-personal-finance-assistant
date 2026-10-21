# Sequence Diagrams

## 1. Nhập giao dịch bằng câu tự nhiên (Phase 2, 3)

> Bước tra cứu `PREF` và lưu feedback/preference chỉ có từ **Phase 3**. Ở Phase 2 bỏ qua các bước này (classifier nhận danh sách preference rỗng).
> Phase 3: nếu câu đơn giản (1 khoản tiền, không nêu ngày) khớp exact một preference thì API trả draft deterministic **không gọi OpenAI**; ngược lại gọi OpenAI với top-5 preference liên quan rồi hậu kiểm draft theo preference. Parse không ghi DB; `hit_count` chỉ tăng khi user lưu draft dùng preference mà không sửa.

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant CLS as ai/classifier
    participant PREF as preference repo
    participant OAI as OpenAI
    participant TX as transaction_service

    U->>FE: "Hôm nay ăn phở 55k"
    FE->>API: POST /api/v1/transactions/parse {text}
    API->>PREF: preference còn dùng (danh mục chưa ẩn)
    PREF-->>API: preferences
    alt câu đơn giản + exact match preference
        API->>CLS: suggestion_from_preference
        CLS-->>API: draft deterministic (matched_preference_id)
    else
        API->>CLS: parse(text, categories, top-5 preference liên quan)
        CLS->>OAI: structured output (TransactionDraft)
        OAI-->>CLS: JSON
        CLS->>CLS: validate Pydantic + category_slug hợp lệ<br/>+ ghi đè phân loại cho draft exact-match preference
        CLS-->>API: TransactionDraft
    end
    API-->>FE: draft (chưa lưu)
    FE-->>U: hiển thị draft: 55.000đ, Ăn uống, Thiết yếu
    U->>FE: sửa spending_type nếu cần, bấm Lưu
    FE->>API: POST /api/v1/transactions {draft đã xác nhận, ai_suggestion}
    API->>TX: create()
    alt user đã sửa đề xuất AI
        TX->>PREF: lưu feedback + upsert preference
    else draft dùng preference, không sửa
        TX->>PREF: hit_count + 1
    end
    TX-->>API: Transaction (+ learned_preference)
    API-->>FE: 201 Created
```

## 2. Nhận lương → Pay Yourself First → Goal (Phase 11)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant GS as goal_service
    participant BR as budget_repository
    participant TX as transaction_service

    U->>FE: "Nhận lương 25 triệu" (quick add) hoặc form /transactions
    FE->>API: POST /transactions/parse (quick add)
    API-->>FE: draft income 25.000.000
    FE->>API: POST /transactions (income)
    API->>TX: create income (commit)
    API->>GS: proposal_for_new_income(income) — chỉ đọc
    GS->>BR: budget tháng của thu nhập (savings_target, strategy)
    GS-->>API: goal active theo priority: Laptop 4.400.000 → savings 5.000.000 → available 15.600.000
    API-->>FE: 201 + pyf_proposal (null nếu không có goal active và budget không phải pyf)
    FE-->>U: dialog "Nhận lương" (thu nhập · mục tiêu · tiết kiệm ngân sách · còn lại để chi tiêu)
    U->>FE: chỉnh số
    FE->>API: POST /goals/pyf-proposal {income_transaction_id, items, budget_savings_amount} (debounce)
    API->>GS: tính lại phần còn thiếu / available / cảnh báo — không ghi DB
    U->>FE: xác nhận
    FE->>API: POST /goals/allocations {income_transaction_id, items, budget_savings_amount}
    API->>GS: validate (thu nhập, chưa phân bổ, goal active, ≤ còn thiếu, tổng ≤ thu nhập) → create GoalContribution(s) (1 commit)
    API-->>FE: contributions + available_spending
    Note over FE,API: Đóng dialog chưa xác nhận → thu nhập vẫn còn, không có khoản góp;<br/>/goals liệt kê "Phân bổ từ thu nhập" (GET /goals/unallocated-incomes)
```

## 3. Weekly Review (Phase 6)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant G as review_graph
    participant AN as analytics_service
    participant OAI as OpenAI
    participant DB as DB

    U->>FE: mở /reviews/weekly/2026-10-05
    FE->>API: GET /reviews/weekly/2026-10-05
    alt đã có review
        API-->>FE: WeeklyReview
    else chưa có (404)
        U->>FE: bấm "Tạo review tuần này"
        FE->>API: POST /reviews/weekly {week_start, today}
        API->>G: run(period=week)
        G->>AN: metrics tuần này + tuần trước
        AN-->>G: metrics
        G->>G: detect_highlights
        loop tối đa 3 lần (retry ≤ 2)
            G->>OAI: ReviewNarrative
            OAI-->>G: narrative
            G->>G: validate (số ⊆ metrics, cụm cấm, 3 tầng)
        end
        opt AI lỗi hoặc vẫn fail
            G->>G: fallback_template
        end
        G->>DB: lưu WeeklyReview
        API-->>FE: WeeklyReview
    end
    FE-->>U: What happened / Why / Notice / Reflection question
    U->>FE: "Có, 2 lần đặt đồ ăn" + tick giao dịch
    FE->>API: POST /reviews/weekly/{id}/reflections
    API->>DB: lưu ReflectionAnswer, status=completed
```

## 4. Financial Coach: "Tao nên giảm khoản nào?" (Phase 10)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant AG as coach_graph
    participant T as tools
    participant OAI as OpenAI

    U->>FE: "Tao nên giảm khoản nào?"
    FE->>API: POST /coach/sessions/{id}/messages
    API->>API: lưu user message (commit)
    API->>AG: invoke(history + message)
    AG->>AG: scope_check (ngoài phạm vi / yêu cầu ghi → template)
    AG->>OAI: messages + tool schemas
    OAI-->>AG: tool_call get_category_trend(months=3) + get_budget_status()
    AG->>T: get_category_trend(3)
    T-->>AG: Ăn uống 4.2tr, Mua sắm 3.8tr (biến động cao nhất)...
    AG->>T: get_budget_status
    T-->>AG: variance theo dòng ngân sách
    AG->>OAI: kết quả tool
    OAI-->>AG: câu trả lời: evidence + gợi ý có điều kiện
    AG->>AG: response_guard (số ⊆ output tool, giọng văn; sai → viết lại 1 lần)
    AG-->>API: message + tool trace + evidence + token/cost
    API->>API: lưu assistant message
    API-->>FE: JSON (plain, chưa stream ở Phase 10)
    FE-->>U: câu trả lời + bảng "Dữ liệu đã dùng" + tool trace
```

## 5. Đọc hoá đơn (Phase 13)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant V as ai/receipt_vision
    participant OAI as OpenAI

    U->>FE: upload ảnh hoá đơn
    FE->>API: POST /receipts (multipart)
    API->>API: validate mime/size, lưu file, Receipt(status=uploaded)
    API->>V: extract(image)
    V->>OAI: vision + structured output ReceiptExtraction
    OAI-->>V: merchant, date, total, items
    V-->>API: extraction + TransactionDraft
    API-->>FE: draft (status=extracted)
    U->>FE: sửa nếu sai, xác nhận
    FE->>API: POST /transactions {..., receipt_id}
    API-->>FE: 201, Receipt(status=confirmed)
```

## 6. Import sao kê CSV (Phase 14)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant IS as import_service
    participant CLS as ai/classifier

    U->>FE: upload file .csv / .xlsx
    FE->>API: POST /imports/preview
    API->>IS: đọc file (pandas), đoán column mapping, tính file_hash
    alt file_hash đã commit trước đó
        API-->>FE: 409 đã import
    end
    IS->>IS: chuẩn hoá dòng, tính dedup_hash, đánh dấu dòng trùng
    IS->>CLS: classify_batch(20 dòng / lần)
    CLS-->>IS: suggestions
    IS-->>API: ImportBatch(previewed) + rows
    API-->>FE: bảng preview
    U->>FE: sửa mapping / category hàng loạt, bỏ chọn dòng
    FE->>API: POST /imports/{id}/commit {rows}
    API->>IS: bulk insert (transaction, bỏ qua dedup_hash trùng)
    API-->>FE: số dòng đã tạo / bỏ qua
```

## 7. Tìm kiếm ngữ nghĩa (Phase 15)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant E as ai/embeddings
    participant DB as Postgres + pgvector

    U->>FE: "ăn ngoài tháng trước"
    FE->>API: GET /search/transactions?q=...&from=&to=
    API->>E: embed(q)
    E-->>API: vector
    API->>DB: ORDER BY embedding <=> :v, lọc ngày, LIMIT 20
    DB-->>API: giao dịch + distance
    API-->>FE: kết quả (kèm tổng tiền)
```
