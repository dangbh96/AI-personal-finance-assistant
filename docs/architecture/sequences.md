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
    FE->>API: POST /receipts?today= (multipart, có tiến độ upload)
    API->>API: validate mime/đuôi/≤10MB/magic bytes, lưu file uuid, Receipt(status=uploaded)
    API->>V: analyze(ảnh — HEIC đổi sang JPEG)
    V->>OAI: vision + structured output ReceiptVisionOutput
    OAI-->>V: merchant, date, total, items, confidence, category
    V-->>API: extraction (+ phân loại theo sở thích đã học)
    alt total > 0, VND, confidence ≥ 0.6
        API-->>FE: 201 TransactionDraft (status=extracted)
    else mờ / thiếu tổng / AI lỗi
        API-->>FE: 201 manual_prefill (status=failed) — có thể POST /receipts/{id}/retry
    end
    U->>FE: sửa nếu sai, xác nhận
    FE->>API: POST /receipts/{id}/confirm {amount, occurred_on, category_id, ...}
    API-->>FE: 201 Transaction(source=receipt, receipt_id), Receipt(status=confirmed)
```

## 6. Import sao kê CSV (Phase 14)

> Preview / đổi mapping chỉ lưu bản xem trước trong `import_batches` (bảng thô + dòng preview), **không** tạo giao dịch. Giao dịch chỉ được tạo ở commit, trong 1 DB transaction.

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant IS as import_service
    participant CLS as ai/classifier
    participant OAI as OpenAI

    U->>FE: upload file .csv / .xlsx (+ tên ngân hàng)
    FE->>API: POST /imports/preview (multipart)
    API->>IS: file_hash
    alt file_hash đã commit trước đó
        API-->>FE: 409 IMPORT_ALREADY_COMMITTED (+ import_batch_id)
    end
    IS->>IS: đọc file (pandas: bảng mã, dấu phân cách / sheet), dòng tiêu đề,<br/>mapping theo profile đã lưu hoặc tự đoán
    IS->>IS: chuẩn hoá ngày / số tiền / chiều, dedup_hash,<br/>trùng trong file / đã import, cảnh báo chuyển khoản nội bộ
    IS->>CLS: classifier(dòng hợp lệ, nội dung đã che số dài)
    CLS->>CLS: exact-match sở thích đã học → không gửi model
    CLS->>OAI: 20 dòng / request (OPENAI_MODEL_FAST)
    OAI-->>CLS: category_slug + spending_type theo row_index
    CLS-->>IS: suggestions (AI lỗi → để "Khác", confidence 0)
    IS-->>API: ImportBatch(previewed) + rows (commit)
    API-->>FE: 201 preview
    opt user đổi mapping
        FE->>API: PATCH /imports/{id}/mapping
        API-->>FE: preview mới (giữ đề xuất cũ theo nội dung)
    end
    U->>FE: sửa danh mục từng dòng / hàng loạt, bỏ chọn dòng
    FE->>API: POST /imports/{id}/commit {rows}
    API->>IS: kiểm tra mọi dòng → tạo giao dịch source=import (bỏ dòng trùng / lỗi),<br/>batch committed, lưu mapping profile — 1 commit
    API-->>FE: 201 {created_count, skipped_duplicate_count, bad_count, not_selected_count}
```

## 7. Tìm kiếm ngữ nghĩa (Phase 15)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant E as ai/embeddings
    participant DB as Postgres + pgvector

    U->>FE: "ăn ngoài" + khoảng ngày
    FE->>API: GET /search/transactions?q=...&from=&to=&limit=
    API->>E: embed("Chi tiêu " + q) (OPENAI_EMBEDDING_MODEL)
    E-->>API: vector (lỗi / thiếu key → 503)
    API->>DB: top limit×5 ORDER BY embedding <=> :v (HNSW, lọc ngày)
    API->>DB: ∪ ghi chú / tên danh mục ILIKE từ khoá (lọc ngày)
    DB-->>API: giao dịch + distance
    API->>API: score = 0.75·(1−distance) + 0.25·keyword_boost,<br/>bỏ dòng chỉ khớp ngữ nghĩa < 0.3, tổng thu / chi bằng Python
    API-->>FE: kết quả + tổng tiền + số giao dịch chưa embed
```

Embed khi ghi giao dịch (best-effort): `POST/PATCH /transactions`, xác nhận hoá đơn, tạo từ khoản định kỳ, commit import → sau khi commit giao dịch, router gọi `embedding_service.embed_transactions_best_effort` (lỗi AI / chưa có key chỉ log, response vẫn 201/200). Bổ sung sau: `python -m app.scripts.backfill_embeddings` hoặc `POST /search/transactions/reindex`.

## 8. Coach trả lời kiến thức có nguồn (Phase 16)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as /coach
    participant G as coach_graph
    participant T as tools (read-only)
    participant KB as knowledge_service + pgvector
    participant GU as response_guard

    U->>FE: "50/30/20 là gì, có phù hợp với tao không?"
    FE->>G: POST /coach/sessions/{id}/messages
    G->>T: search_knowledge("50/30/20")
    T->>KB: embed câu hỏi → top-4 đoạn (cosine)
    KB-->>T: đoạn + citation "Quy tắc 50/30/20 — … (knowledge/50-30-20.md)"
    G->>T: get_spending_summary(tháng trước, spending_type)
    T-->>G: income_share_pct Thiết yếu / Không thiết yếu, net_income_pct
    G->>GU: câu trả lời (Quan sát → Vì sao → Gợi ý + **Nguồn:**)
    alt thiếu Nguồn / nguồn không có trong kết quả / chưa xem số liệu cá nhân
        GU-->>G: yêu cầu viết lại (tối đa 1 lần) → vẫn sai: fallback liệt kê nguồn thật
    end
    GU-->>FE: answer + citations (S1…) + tool trace "Đã tra kiến thức: …"
    U->>FE: bấm nguồn → GET /knowledge/chunks/{id} (drawer)
```

Ingest: `python -m app.scripts.ingest_knowledge knowledge/` → đọc `.md` / `.pdf` → chia đoạn → embed → `knowledge_documents` / `knowledge_chunks` (bỏ qua file không đổi `content_hash`).