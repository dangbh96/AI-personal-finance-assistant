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
    participant BS as budget_service
    participant TX as transaction_service

    U->>FE: "Nhận lương 25 triệu"
    FE->>API: POST /transactions/parse
    API-->>FE: draft income 25.000.000
    FE->>API: POST /transactions (income)
    API->>TX: create income
    API->>GS: propose_pyf_allocation(income)
    GS->>BS: savings_target của budget tháng
    GS-->>API: đề xuất: Laptop goal 4.400.000, Saving 5.000.000, Available 15.600.000
    API-->>FE: 201 + pyf_proposal
    FE-->>U: màn hình xác nhận phân bổ
    U->>FE: chỉnh số / xác nhận
    FE->>API: POST /goals/allocations {income_transaction_id, items}
    API->>GS: create GoalContribution(s)
    API-->>FE: số dư available spending tháng
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
    else chưa có
        FE->>API: POST /reviews/weekly {week_start}
        API->>G: run(period=week)
        G->>AN: metrics tuần này + tuần trước
        AN-->>G: metrics
        G->>G: detect_highlights
        G->>OAI: ReviewNarrative
        OAI-->>G: narrative
        G->>G: validate (số liệu, giọng văn)
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
    API->>AG: invoke(history + message)
    AG->>OAI: messages + tool schemas
    OAI-->>AG: tool_call get_category_trend(months=3)
    AG->>T: get_category_trend(3)
    T-->>AG: Ăn uống 4.2tr, Mua sắm 3.8tr (biến động cao nhất)...
    AG->>OAI: kết quả tool
    OAI-->>AG: tool_call get_budget_status(current)
    AG->>T: get_budget_status
    T-->>AG: variance theo category
    AG->>OAI: kết quả tool
    OAI-->>AG: câu trả lời: evidence + gợi ý có điều kiện
    AG->>AG: response_guard
    AG-->>API: message + tool trace
    API-->>FE: stream / JSON
    FE-->>U: câu trả lời + bảng số liệu đã dùng
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
