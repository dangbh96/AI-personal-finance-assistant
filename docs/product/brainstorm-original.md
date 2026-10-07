# Brainstorm gốc

> Nguyên văn bản brainstorm ban đầu (2026-10-02), lưu làm nguồn tham chiếu. Không chỉnh sửa file này — mọi quyết định đã chốt nằm ở [vision.md](./vision.md) và [docs/architecture](../architecture/overview.md).

---

Ừ, cái tóm tắt này làm business **hay hơn khá nhiều**. Nó khiến app không còn là “AI ghi chép chi tiêu”, mà có một **financial management philosophy** rõ ràng: **Track → Classify → Review → Budget → Adjust → Build discipline**.

T sẽ tích hợp nguyên framework này vào concept **Personal CFO / AI Financial Assistant** như sau.

## 1. Core business mới
Thay vì:

> “AI giúp bạn quản lý chi tiêu”
ta định nghĩa sản phẩm là:

> **Một trợ lý tài chính cá nhân giúp người dùng hiểu tiền của mình đang đi đâu, lập kế hoạch sử dụng tiền, rồi định kỳ review để cải thiện hành vi tài chính.**
Có 2 vòng lặp chính:

```
                PERSONAL CFO
                     │
          ┌──────────┴──────────┐
          │                     │
    TRACKING LOOP          BUDGET LOOP
          │                     │
      Liệt kê                 Lập budget
          ↓                     ↓
      Phân loại              Phân bổ tiền
          ↓                     ↓
       Ghi chép             Theo dõi thực tế
          ↓                     ↓
        Review  ←───────────────┘
          ↓
    Insight / Action
          ↓
    Điều chỉnh tháng sau
```
Điểm quan trọng là **Review trở thành trung tâm**, chứ không phải dashboard.

Video nhấn mạnh Review là bước quan trọng nhất, vì ghi chép mà không xem lại thì gần như không tạo ra thay đổi hành vi. Vì vậy app nên thiết kế cả một **Review workflow**, thay vì chỉ hiển thị biểu đồ.

---

# 2. Transaction Management
Đây là nền móng.

### Thu nhập

```
Salary       +25,000,000
Freelance     +3,000,000
Bonus         +2,000,000
```

### Chi tiêu

```
Rent          -5,000,000
Food          -3,200,000
Transport     -800,000
Shopping      -1,500,000
```
AI hỗ trợ nhập:

> “Hôm nay ăn phở 55k”

> “Grab về nhà 45 nghìn”

> “Tháng này nhận lương 25 triệu”

> “Mua tai nghe 1tr5”

---

# 3. Đặc biệt: 3 nhóm chi tiêu
T sẽ **không dùng category đơn thuần**.

Ví dụ:

```
Category:
    Ăn uống
    Đi lại
    Nhà ở
    Mua sắm
    Giải trí
    ...

Type:
    Thiết yếu
    Không thiết yếu
    Bất thường
```
Như vậy:

```
Tiền thuê nhà
→ Nhà ở
→ Thiết yếu

Netflix
→ Giải trí
→ Không thiết yếu

Sửa laptop đột xuất
→ Điện tử
→ Bất thường
```
Đây là một distinction rất hữu ích.

AI có thể hỏi:

> “Khoản này thuộc loại nào?”
hoặc tự đề xuất:

> “Tôi đoán đây là chi tiêu **Không thiết yếu → Mua sắm**. Bạn có muốn thay đổi không?”

---

# 4. AI học cách phân loại của user
Ví dụ lần đầu:

> “Mua giày MLB 1.8 triệu”
AI:

```
Category: Mua sắm
Type: Không thiết yếu
```
M sửa:

> “Tao coi giày là thiết yếu.”
App lưu preference.

Lần sau AI hiểu context tốt hơn.

Đây là chỗ có thể dùng:

**LLM + structured output + memory**

chứ không hard-code toàn bộ classification.

---

# 5. Review Engine ⭐
Theo t đây nên là **feature đặc trưng nhất của business**.

Mỗi tuần:

> 📝 **Weekly Financial Review**
AI tự tổng hợp:

```
Tuần 3

Thu nhập:       0đ
Chi tiêu:    2.350.000đ

Thiết yếu:       1.420.000
Không thiết yếu:   780.000
Bất thường:       150.000
```
Sau đó:

### What happened?

> Tuần này chi tiêu tăng 18% so với tuần trước.

### Why?

> Mức tăng chủ yếu đến từ ăn uống bên ngoài và mua sắm.

### What should you notice?

> Bạn có 4 giao dịch ăn ngoài vào buổi tối, tổng 620.000đ.

### Reflection
AI có thể hỏi:

> “Có khoản nào trong tuần này bạn thấy không đáng tiền không?”
User:

> “Có, 2 lần đặt đồ ăn.”
App ghi nhận.

Đây mới thực sự là **behavior loop**.

---

# 6. Monthly Review
Cuối tháng app chủ động tạo:

> **Monthly Financial Review**
Ví dụ:

```
THÁNG 9

Income
25.000.000

Expenses
18.400.000

Saved
6.600.000
```

### Breakdown

```
Thiết yếu       9.200.000   50%
Không thiết yếu 6.100.000   33%
Bất thường      3.100.000   17%
```
Sau đó:

> Tháng này các khoản bất thường cao hơn bình thường do mua laptop.
Quan trọng: **không phán xét**.

Không phải:

> ❌ “Bạn tiêu quá nhiều.”
Mà:

> “Chi tiêu tháng này cao hơn tháng trước 12%. Phần lớn mức tăng đến từ khoản mua laptop 15 triệu.”

---

# 7. Budget Engine
Đây là nửa thứ hai của business.

User tạo budget:

```
Monthly income: 25m

Essential
  Housing       5m
  Food          4m
  Transport     1m

Non-essential
  Shopping      2m
  Entertainment 1m

Saving
  5m
```
Nhưng **không ép user vào một phương pháp duy nhất**.

---

# 8. Hỗ trợ 3 budgeting strategies

## A. Envelope / Jars

```
25m
│
├── 🏠 Essential       10m
├── 🎮 Fun              3m
├── 🛒 Shopping         2m
├── 💰 Saving           7m
└── 🆘 Unexpected       3m
```
App theo dõi từng “hũ”.

---

## B. 50/30/20
App có thể hiển thị:

```
50% Essential
30% Wants
20% Saving
```
Nhưng không nên hard-code thành “luật”.

Ví dụ AI nói:

> “Budget hiện tại của bạn không theo đúng tỷ lệ 50/30/20. Bạn có muốn xem thử ngân sách theo tỷ lệ này để tham khảo không?”

---

## C. Pay Yourself First ⭐
Đây có thể trở thành **một workflow riêng**.

Khi nhận lương:

```
Salary
25,000,000
       │
       ↓
Save first
5,000,000
       │
       ↓
Available spending
20,000,000
```
Thay vì:

```
Spend → spend → spend → còn bao nhiêu thì tiết kiệm
```
App có thể tự động tạo:

```
Income received
        ↓
Savings allocation
        ↓
Budget allocation
        ↓
Available spending
```

---

# 9. Budget vs Actual
Đây sẽ là màn hình cực quan trọng.

Ví dụ:

CategoryBudgetActualStatusNhà ở5m5m✓Ăn uống4m4.5m+500kĐi lại1m700k✓Mua sắm2m3.2m+1.2mGiải trí1m600k✓AI không chỉ nói:

> “Mua sắm vượt budget.”
Mà:

> “Bạn vượt budget mua sắm 1.2 triệu. Trong đó 900k đến từ một giao dịch duy nhất.”

---

# 10. Và đây là feature rất quan trọng: **Budget Adjustment**
Video có một điểm rất hay:

> Nếu actual > budget thì **không mặc định sửa budget**.
App phải phân tích:

```
Budget sai?
       │
       ├── Có → điều chỉnh budget
       │
       └── Không
             │
             ↓
       Behavior sai?
             │
             ↓
       Điều chỉnh hành vi
```
Ví dụ:

### Case 1
Budget ăn uống:

```
4m
```
Actual:

```
4.5m
```
Nhưng 3 tháng liên tục:

```
4.4m
4.6m
4.5m
```
AI có thể nhận xét:

> Mức 4 triệu có vẻ thấp hơn mức chi tiêu thực tế gần đây. Bạn có thể cân nhắc điều chỉnh budget hoặc xem lại thói quen ăn uống.

### Case 2
Budget:

```
2m shopping
```
Actual:

```
8m
```
nhưng có một lần mua laptop.

AI nhận diện:

> Khoản vượt ngân sách chủ yếu đến từ một giao dịch bất thường. Không nhất thiết phản ánh nhu cầu chi tiêu thường xuyên.
**Đây là chỗ AI có giá trị hơn một spreadsheet.**

---

# 11. Budget không được quá cứng
Có thể tạo concept:

### Flexible Budget
Thay vì:

```
Food = exactly 4,000,000
```
app cho:

```
Target:       4m
Comfort zone: 3.5–4.5m
Warning:      >4.5m
```
Hoặc:

```
🟢 Normal
🟡 Attention
🔴 Review needed
```
Nhưng các mức này nên **do user cấu hình hoặc dựa trên dữ liệu của chính họ**, chứ không áp một chuẩn tài chính cứng nhắc.

---

# 12. Financial Coach
Đây là lớp AI phía trên toàn bộ hệ thống.

M có thể hỏi:

> “Tao nên giảm khoản nào?”
AI không tự quyết định thay m, mà đưa evidence:

```
3 tháng gần nhất:

Ăn uống       4.2m
Mua sắm       3.8m
Giải trí      1.1m
Đi lại        0.9m

Mua sắm có biến động lớn nhất.
```
Sau đó:

> “Bạn có thể xem xét đặt giới hạn cho mua sắm hoặc theo dõi riêng các khoản mua không thường xuyên.”

---

# 13. Goal + Pay Yourself First
Ghép hai concept này lại sẽ rất hay.

Ví dụ:

> “Tao muốn có 30 triệu vào tháng 3 để mua laptop.”
AI:

```
Goal
Laptop

Target             30m
Current             8m
Remaining          22m
Months remaining    5

Suggested saving   4.4m/month
```
Khi nhận lương:

```
25m income
   │
   ├── 4.4m → Laptop Goal
   │
   └── 20.6m → Spending
```

---

# 14. AI Financial Calendar
Một feature khá thú vị:

```
25 Sep
💰 Salary

26 Sep
🏠 Rent

01 Oct
💳 Credit card

05 Oct
📱 Internet

10 Oct
🎯 Goal saving
```
Agent có thể biết các khoản recurring và dự đoán cashflow.

---

# 15. “What happened?” → “What should I do?”
T sẽ thiết kế AI theo 3 tầng:

### Tầng 1 — Observation

> “Bạn đã chi 18.2 triệu.”

### Tầng 2 — Explanation

> “Mức tăng chủ yếu đến từ mua sắm và ăn uống.”

### Tầng 3 — Action

> “Nếu muốn đưa tổng chi tháng sau về khoảng 15 triệu, có thể xem xét giảm các khoản mua sắm không thiết yếu.”
**Không nhảy thẳng từ dữ liệu → lời khuyên.**

---

# 16. Và nếu map vào AI course của m
Cái project này có thể cover gần như toàn bộ curriculum:

FeatureCông nghệ/courseTransaction parserPythonNatural language inputOpenAI APICategorizationLLM / structured outputReceipt parsingVisionCSV/Excel importPythonSpending searchEmbeddingsFinancial knowledgeRAGPersonal finance docsPineconeChatbotLangChainBudget toolsFunction CallingFinancial agentLangGraphWeekly ReviewAgent workflowMonthly ReviewAgent workflowAnomaly detectionPython / MLWhat-if simulatorPython toolsLocal/private AILlama 3OCR/TTSHugging FaceRetry/validationOpenAI APIMultiple toolsAgentNhững mảng như embeddings/semantic search, Pinecone, LangChain và LangGraph/RAG đều nằm trực tiếp trong curriculum của m.

---

## 🔥 Nếu là t build project này
T sẽ đặt **core loop** như này:

```
                💰 INCOME
                   │
                   ▼
             PAY YOURSELF FIRST
                   │
                   ▼
              CREATE BUDGET
                   │
                   ▼
              TRACK SPENDING
                   │
                   ▼
                CLASSIFY
                   │
                   ▼
             ACTUAL vs BUDGET
                   │
                   ▼
             WEEKLY REVIEW
                   │
                   ▼
            MONTHLY REVIEW
                   │
          ┌────────┴────────┐
          ▼                 ▼
      BEHAVIOR           BUDGET
      CHANGE             CHANGE
          │                 │
          └────────┬────────┘
                   ▼
              NEXT MONTH
```
Và **AI Agent nằm xuyên suốt flow này**, chứ không phải chỉ là cái chatbot ở góc màn hình.

Điểm t thích nhất ở hướng này là: **business logic của app không phụ thuộc vào AI**. Database, transaction, budget, actual/forecast vẫn là deterministic; AI đứng trên đó để **hiểu input → phân tích → review → gọi tools → giải thích → hỗ trợ ra quyết định**. Như vậy vừa thực tế, vừa là một project rất đẹp để demonstrate kiến thức trong course.