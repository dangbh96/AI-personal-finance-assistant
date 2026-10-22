"""API import sao kê CSV / Excel (Phase 14) — OpenAI giả, không cần key."""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.ai import classifier, openai_client
from app.ai.openai_client import ChatResult
from app.models import ClassificationFeedback, ClassificationPreference, Transaction

URL = "/api/v1/imports"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"
CSV = "text/csv"


def _fake_item(item: dict) -> dict:
    note = item["note"].lower()
    if item["direction"] == "income":
        slug = "salary" if ("luong" in note or "lương" in note) else "other_income"
        return {
            "row_index": item["row_index"],
            "category_slug": slug,
            "spending_type": None,
            "confidence": 0.9,
            "reason": "Theo nội dung",
        }
    if "grab" in note:
        # Model "không chắc" → user sửa hàng loạt sang Đi lại trong preview.
        slug, spending, confidence = "other", "non_essential", 0.3
    else:
        slug, spending, confidence = "food", "essential", 0.8
    return {
        "row_index": item["row_index"],
        "category_slug": slug,
        "spending_type": spending,
        "confidence": confidence,
        "reason": "Theo nội dung",
    }


@pytest.fixture
def ai(monkeypatch):
    """OpenAI giả cho phân loại hàng loạt: đọc các dòng trong prompt, trả item theo quy tắc."""
    state: dict = {"calls": [], "mode": "ok"}

    def _fake(**kwargs):
        user = kwargs["messages"][1]["content"]
        items = json.loads(user.split("\n", 1)[1])
        state["calls"].append({"items": items, "model": kwargs["model"], **kwargs})
        if state["mode"] == "invalid":
            content = json.dumps({"items": []})
        else:
            content = json.dumps({"items": [_fake_item(i) for i in items]})
        return ChatResult(
            content=content,
            refusal=None,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=50,
        )

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(openai_client, "_chat_json", _fake)
    return state


def _upload(client, name: str, content: bytes | None = None, content_type: str = "", **data):
    content = content if content is not None else (FIXTURES / name).read_bytes()
    return client.post(f"{URL}/preview", files={"file": (name, content, content_type)}, data=data)


def _preview(client, name: str = "vcb_statement.csv", **data) -> dict:
    resp = _upload(client, name, **data)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _row(body: dict, note: str) -> dict:
    return next(r for r in body["rows"] if r["note"] == note)


def _commit_all(body: dict, **overrides) -> list[dict]:
    """Chọn mọi dòng (kể cả trùng / lỗi), giữ đề xuất danh mục."""
    rows = []
    for r in body["rows"]:
        rows.append(
            {
                "row_index": r["row_index"],
                "category_id": r["suggested_category_id"] or overrides["fallback_category"],
                "spending_type": r["suggested_spending_type"],
                "selected": True,
            }
        )
    return rows


def _csv(lines: list[str]) -> bytes:
    return ("\n".join(["Ngày;Nội dung;Ghi nợ;Ghi có", *lines]) + "\n").encode("utf-8")


# ---------- preview: test case 1–6 ----------


def test_preview_vcb_counts_and_mapping(client, ai):
    body = _preview(client, bank_name="  Vietcombank ")
    assert body["summary"]["row_count"] == 25
    assert body["summary"]["valid_count"] == 22
    assert body["summary"]["duplicate_count"] == 2
    assert body["summary"]["bad_count"] == 1
    assert body["batch"]["status"] == "previewed"
    assert body["batch"]["bank_name"] == "Vietcombank"
    assert body["batch"]["valid_count"] == 22
    info = body["file_info"]
    assert (info["file_type"], info["encoding"], info["separator"]) == ("csv", "utf-8-sig", ";")
    assert info["header_row"] == 4
    mapping = body["mapping"]
    assert mapping["source"] == "guess"
    assert mapping["problems"] == []
    assert mapping["column_mapping"] == {
        "date": "Ngày giao dịch",
        "description": "Nội dung chi tiết",
        "amount": None,
        "debit": "Số tiền ghi nợ",
        "credit": "Số tiền ghi có",
    }
    assert mapping["date_format"] == "dd/mm/yyyy"
    assert mapping["decimal_style"] == "dot_thousands"
    # Không tạo giao dịch nào ở bước preview.
    assert client.get("/api/v1/transactions", params={"source": "import"}).json()["total"] == 0


def test_preview_cp1258_vietnamese(client, ai):
    body = _preview(client, "techcombank_statement.csv")
    assert body["file_info"]["encoding"] == "cp1258"
    assert body["file_info"]["separator"] == ","
    lunch = _row(body, "Ăn trưa quán bún bò")
    assert (lunch["amount"], lunch["direction"], lunch["status"]) == (65_000, "expense", "valid")
    assert body["summary"]["valid_count"] == 22


def test_preview_xlsx(client, ai):
    body = _preview(client, "statement.xlsx")
    assert body["file_info"]["file_type"] == "xlsx"
    assert body["file_info"]["sheet_name"] == "Sao ke"
    assert (body["summary"]["valid_count"], body["summary"]["duplicate_count"]) == (22, 2)
    assert body["summary"]["bad_count"] == 1


def test_debit_credit_amounts_and_salary_suggestion(client, ai, categories):
    body = _preview(client)
    electricity = _row(body, "THANH TOAN TIEN DIEN EVN THANG 8")
    assert (electricity["amount"], electricity["direction"]) == (1_500_000, "expense")
    assert electricity["raw"]["debit"] == "1.500.000"
    salary = _row(body, "Lương tháng 08/2026 công ty ABC")
    assert (salary["amount"], salary["direction"]) == (25_000_000, "income")
    assert salary["suggested_category_id"] == categories["salary"]["id"]
    assert salary["suggested_spending_type"] is None
    assert salary["suggestion_source"] == "ai"


def test_duplicates_share_hash(client, ai):
    body = _preview(client)
    coffee = [r for r in body["rows"] if r["note"] == "HIGHLANDS COFFEE VINCOM"]
    assert [r["status"] for r in coffee] == ["valid", "duplicate"]
    assert coffee[0]["dedup_hash"] == coffee[1]["dedup_hash"]
    assert coffee[1]["duplicate_of_row"] == coffee[0]["row_index"]
    assert coffee[1]["suggested_category_id"] is None


def test_bad_row_not_committed(client, ai, categories):
    body = _preview(client)
    bad = [r for r in body["rows"] if r["status"] == "bad"]
    assert len(bad) == 1
    assert "32/13/2026" in bad[0]["error"]
    rows = _commit_all(body, fallback_category=categories["other"]["id"])
    resp = client.post(f"{URL}/{body['batch']['id']}/commit", json={"rows": rows})
    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["created_count"] == 22
    assert result["bad_count"] == 1
    assert result["skipped_duplicate_count"] == 2
    listed = client.get(
        "/api/v1/transactions", params={"q": "SMS BANKING", "source": "import"}
    ).json()
    assert listed["total"] == 0


# ---------- commit: test case 7, 10 ----------


def test_commit_creates_transactions_then_reupload_409(client, ai, categories, db):
    body = _preview(client, bank_name="VCB")
    batch_id = body["batch"]["id"]
    valid = [r for r in body["rows"] if r["status"] == "valid"]
    rows = [
        {
            "row_index": r["row_index"],
            "category_id": r["suggested_category_id"],
            "spending_type": r["suggested_spending_type"],
        }
        for r in valid
    ]
    resp = client.post(f"{URL}/{batch_id}/commit", json={"rows": rows})
    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["created_count"] == 22
    assert result["not_selected_count"] == 0
    assert result["batch"]["status"] == "committed"
    assert result["batch"]["committed_count"] == 22
    assert result["batch"]["committed_at"] is not None

    listed = client.get(
        "/api/v1/transactions",
        params={"source": "import", "import_batch_id": batch_id, "page_size": 100},
    ).json()
    assert listed["total"] == 22
    assert all(
        t["source"] == "import" and t["import_batch_id"] == batch_id for t in listed["items"]
    )
    salary = next(t for t in listed["items"] if t["amount"] == 25_000_000)
    assert salary["direction"] == "income"
    assert salary["category"]["slug"] == "salary"
    assert salary["raw_input"].startswith("Sao kê vcb_statement.csv · dòng 5: ")
    hashes = db.scalars(select(Transaction.dedup_hash).where(Transaction.source == "import")).all()
    assert len(set(hashes)) == 22

    again = _upload(client, "vcb_statement.csv")
    assert again.status_code == 409
    assert again.json()["code"] == "IMPORT_ALREADY_COMMITTED"
    assert again.json()["import_batch_id"] == batch_id

    # Commit / đổi mapping lại cũng bị chặn.
    assert client.post(f"{URL}/{batch_id}/commit", json={"rows": rows}).status_code == 409
    patch = client.patch(
        f"{URL}/{batch_id}/mapping", json={"column_mapping": body["mapping"]["column_mapping"]}
    )
    assert patch.status_code == 409
    detail = client.get(f"{URL}/{batch_id}").json()
    assert detail["batch"]["status"] == "committed"
    assert len(detail["rows"]) == 25


def test_overlapping_statement_marks_existing_duplicates(client, ai, categories):
    body = _preview(client)
    rows = [
        {"row_index": r["row_index"], "category_id": r["suggested_category_id"]}
        for r in body["rows"]
        if r["status"] == "valid"
    ]
    assert (
        client.post(f"{URL}/{body['batch']['id']}/commit", json={"rows": rows}).status_code == 201
    )
    # File khác (Techcombank) có cùng giao dịch → cùng dedup_hash → trùng với giao dịch đã import.
    second = _preview(client, "techcombank_statement.csv")
    assert second["summary"]["valid_count"] == 0
    assert second["summary"]["duplicate_count"] == 24
    assert sum(1 for r in second["rows"] if r["duplicate_existing"]) == 24
    resp = client.post(
        f"{URL}/{second['batch']['id']}/commit",
        json={
            "rows": [
                {"row_index": r["row_index"], "category_id": categories["food"]["id"]}
                for r in second["rows"]
            ]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "no_rows_selected"


def test_commit_bulk_edit_and_note_and_selection(client, ai, categories, db):
    body = _preview(client)
    grab = [r for r in body["rows"] if r["note"].startswith("GRAB")]
    assert len(grab) == 3
    assert all(r["suggested_category_id"] == categories["other"]["id"] for r in grab)
    transport = categories["transport"]["id"]
    rows = []
    for r in body["rows"]:
        if r["status"] != "valid":
            continue
        is_grab = r["note"].startswith("GRAB")
        rows.append(
            {
                "row_index": r["row_index"],
                "category_id": transport if is_grab else r["suggested_category_id"],
                "spending_type": "essential" if is_grab else r["suggested_spending_type"],
                "selected": r["note"] != "NETFLIX.COM",
                **({"note": "Đi Grab"} if r["note"] == "GRAB*TRIP 1234 HCM" else {}),
            }
        )
    resp = client.post(f"{URL}/{body['batch']['id']}/commit", json={"rows": rows})
    assert resp.status_code == 201, resp.text
    assert resp.json()["created_count"] == 21
    assert resp.json()["not_selected_count"] == 1
    listed = client.get(
        "/api/v1/transactions",
        params={"source": "import", "category_id": transport, "page_size": 50},
    ).json()
    assert listed["total"] == 3
    assert {t["spending_type"] for t in listed["items"]} == {"essential"}
    assert "Đi Grab" in {t["note"] for t in listed["items"]}
    # Sửa đề xuất → lưu feedback, không tự học sở thích mới từ sao kê.
    feedback = db.scalar(select(func.count()).select_from(ClassificationFeedback))
    assert feedback == 3
    assert db.scalar(select(func.count()).select_from(ClassificationPreference)) == 0


def test_commit_is_atomic(client, ai, categories, db):
    body = _preview(client)
    valid = [r for r in body["rows"] if r["status"] == "valid"]
    rows = [{"row_index": r["row_index"], "category_id": r["suggested_category_id"]} for r in valid]
    # Thu nhập lương gán nhầm danh mục chi → 422, không giao dịch nào được tạo.
    salary = next(
        r
        for r in rows
        if _row(body, "Lương tháng 08/2026 công ty ABC")["row_index"] == r["row_index"]
    )
    salary["category_id"] = categories["food"]["id"]
    resp = client.post(f"{URL}/{body['batch']['id']}/commit", json={"rows": rows})
    assert resp.status_code == 422
    assert resp.json()["code"] == "category_kind_mismatch"
    assert resp.json()["detail"].startswith("Dòng 5:")
    imported = select(func.count()).select_from(Transaction).where(Transaction.source == "import")
    assert db.scalar(imported) == 0
    assert client.get(f"{URL}/{body['batch']['id']}").json()["batch"]["status"] == "previewed"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"rows": [{"row_index": 999, "category_id": None}]}, "validation_error"),
        ({"rows": []}, "validation_error"),
        ({"rows": [{"row_index": 5, "category_id": "x", "extra": 1}]}, "validation_error"),
    ],
)
def test_commit_validation(client, ai, payload, code):
    body = _preview(client)
    resp = client.post(f"{URL}/{body['batch']['id']}/commit", json=payload)
    assert resp.status_code == 422
    assert resp.json()["code"] == code


def test_commit_unknown_row_and_nothing_selected(client, ai, categories):
    body = _preview(client)
    url = f"{URL}/{body['batch']['id']}/commit"
    food = categories["food"]["id"]
    unknown = client.post(url, json={"rows": [{"row_index": 999, "category_id": food}]})
    assert unknown.status_code == 422 and unknown.json()["code"] == "import_row_not_found"
    first = body["rows"][0]["row_index"]
    none = client.post(
        url, json={"rows": [{"row_index": first, "category_id": food, "selected": False}]}
    )
    assert none.status_code == 422 and none.json()["code"] == "no_rows_selected"
    repeated = client.post(
        url,
        json={"rows": [{"row_index": first, "category_id": food}] * 2},
    )
    assert repeated.status_code == 422


# ---------- phân loại: test case 8, 9 ----------


def test_twenty_rows_one_request(client, ai):
    lines = [
        f"{d:02d}/09/2026;CUA HANG SO {chr(65 + d)} QUAN {d};{(d + 1) * 1000};"
        for d in range(1, 21)
    ]
    resp = _upload(client, "twenty.csv", _csv(lines), CSV)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["summary"]["valid_count"] == 20
    assert len(ai["calls"]) == 1
    assert len(ai["calls"][0]["items"]) == 20
    assert ai["calls"][0]["model"] == openai_client.model_fast()
    assert body["summary"]["ai_count"] == 20


def test_batches_of_twenty_and_same_note_sent_once(client, ai):
    lines = [f"01/09/2026;SHOP {i:02d} A;{1000 + i};" for i in range(45)]
    lines += [f"02/09/2026;SHOP 00 A;{5000 + i};" for i in range(5)]  # cùng nội dung → 1 lần
    body = _upload(client, "many.csv", _csv(lines), CSV).json()
    assert body["summary"]["valid_count"] == 50
    assert sorted(len(c["items"]) for c in ai["calls"]) == [5, 20, 20]
    assert body["summary"]["ai_count"] == 50


def test_preferences_skip_llm(client, ai, categories):
    for pattern, slug in [("bun bo", "food"), ("netflix", "entertainment")]:
        resp = client.post(
            "/api/v1/classification-preferences",
            json={"pattern": pattern, "category_slug": slug, "spending_type": "non_essential"},
        )
        assert resp.status_code == 201, resp.text
    lines = [
        "01/09/2026;Ăn trưa quán bún bò;65.000;",
        "02/09/2026;BUN BO HUE CO BA;55.000;",
        "03/09/2026;Bún bò Nam Bộ;70.000;",
        "04/09/2026;NETFLIX.COM;260.000;",
        "05/09/2026;NETFLIX COM SUBSCRIPTION;260.000;",
    ]
    body = _upload(client, "pref.csv", _csv(lines), CSV).json()
    assert ai["calls"] == []
    assert body["summary"]["preference_count"] == 5
    for row in body["rows"]:
        assert row["suggestion_source"] == "preference"
        assert row["matched_preference_id"] is not None
        assert row["suggested_spending_type"] == "non_essential"
        assert row["confidence"] == classifier.PREFERENCE_CONFIDENCE
    assert _row(body, "NETFLIX.COM")["suggested_category_id"] == categories["entertainment"]["id"]
    assert _row(body, "Bún bò Nam Bộ")["suggested_category_id"] == categories["food"]["id"]

    # Lưu không sửa → hit_count tăng theo số dòng dùng sở thích.
    rows = [
        {
            "row_index": r["row_index"],
            "category_id": r["suggested_category_id"],
            "spending_type": r["suggested_spending_type"],
        }
        for r in body["rows"]
    ]
    assert (
        client.post(f"{URL}/{body['batch']['id']}/commit", json={"rows": rows}).status_code == 201
    )
    prefs = {
        p["pattern"]: p["hit_count"]
        for p in client.get("/api/v1/classification-preferences").json()["items"]
    }
    assert prefs == {"bun bo": 3, "netflix": 2}


def test_mixed_preference_and_ai(client, ai, categories):
    client.post(
        "/api/v1/classification-preferences",
        json={"pattern": "highlands", "category_slug": "food", "spending_type": "non_essential"},
    )
    body = _preview(client)
    highlands = _row(body, "HIGHLANDS COFFEE VINCOM")
    assert highlands["suggestion_source"] == "preference"
    sent = {i["row_index"] for c in ai["calls"] for i in c["items"]}
    assert highlands["row_index"] not in sent
    assert body["summary"]["preference_count"] == 1
    assert body["summary"]["ai_count"] == 21


def test_prompt_masks_account_numbers(client, ai):
    lines = ["01/09/2026;CK DEN TK 0001234567890 FT26245123456 TIEN NHA;5.000.000;"]
    _upload(client, "mask.csv", _csv(lines), CSV)
    sent = json.dumps(ai["calls"][0]["messages"], ensure_ascii=False)
    assert "0001234567890" not in sent
    assert "FT26245123456" not in sent
    assert "TIEN NHA" in sent


def test_ai_not_configured_falls_back(client, monkeypatch, categories):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    body = _preview(client)
    assert body["summary"]["fallback_count"] == 22
    assert body["batch"]["ai_error_code"] == "AI_NOT_CONFIGURED"
    salary = _row(body, "Lương tháng 08/2026 công ty ABC")
    assert salary["suggested_category_id"] == categories["other_income"]["id"]
    assert salary["confidence"] == 0
    lunch = _row(body, "Ăn trưa quán bún bò")
    assert lunch["suggested_category_id"] == categories["other"]["id"]
    assert lunch["suggested_spending_type"] == "non_essential"
    assert any("AI chưa phân loại được" in w for w in body["warnings"])


def test_ai_invalid_output_falls_back(client, ai):
    ai["mode"] = "invalid"
    body = _preview(client)
    assert body["batch"]["ai_error_code"] == "AI_INVALID_OUTPUT"
    # 21 nội dung khác nhau → 2 request, mỗi request 1 lần + 1 lần cho model sửa.
    assert len(ai["calls"]) == 4
    assert body["summary"]["fallback_count"] == 22
    assert body["summary"]["valid_count"] == 22


# ---------- mapping ----------


def test_patch_mapping_reparses_and_reuses_suggestions(client, ai):
    content = "\n".join(
        [
            "Ngày,Ngày hiệu lực,Mô tả,Số tiền",
            "01/09/2026,02/09/2026,CAFE SANG,-45.000",
            "03/09/2026,04/09/2026,LUONG T8,25.000.000",
        ]
    ).encode()
    body = _upload(client, "map.csv", content, CSV).json()
    assert body["mapping"]["column_mapping"]["date"] == "Ngày"
    assert len(ai["calls"]) == 1
    batch_id = body["batch"]["id"]

    mapping = {**body["mapping"]["column_mapping"], "date": "Ngày hiệu lực"}
    resp = client.patch(
        f"{URL}/{batch_id}/mapping", json={"column_mapping": mapping, "date_format": "dd/mm/yyyy"}
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["mapping"]["source"] == "user"
    assert [r["occurred_on"] for r in updated["rows"]] == ["2026-09-02", "2026-09-04"]
    assert len(ai["calls"]) == 1  # cùng nội dung → giữ đề xuất cũ
    assert updated["rows"][1]["suggestion_source"] == "ai"

    # mm/dd → 02/09 thành 9 tháng 2 → ngày 04/09 → 9/4.
    us = client.patch(
        f"{URL}/{batch_id}/mapping", json={"column_mapping": mapping, "date_format": "mm/dd/yyyy"}
    ).json()
    assert [r["occurred_on"] for r in us["rows"]] == ["2026-02-09", "2026-04-09"]


@pytest.mark.parametrize(
    "mapping",
    [
        {"date": "Ngày", "amount": "Số tiền"},
        {"date": "Ngày", "description": "Không có", "amount": "Số tiền"},
        {"date": "Ngày", "description": "Mô tả", "amount": "Số tiền", "debit": "Số tiền"},
    ],
)
def test_patch_mapping_invalid(client, ai, mapping):
    content = "Ngày,Mô tả,Số tiền\n01/09/2026,CAFE,-45.000\n".encode()
    batch_id = _upload(client, "m.csv", content, CSV).json()["batch"]["id"]
    resp = client.patch(f"{URL}/{batch_id}/mapping", json={"column_mapping": mapping})
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_mapping"


def test_unknown_columns_need_mapping(client, ai):
    content = b"A;B;C\n01/09/2026;CAFE;-45.000\n"
    body = _upload(client, "unknown.csv", content, CSV).json()
    assert body["mapping"]["problems"]
    assert body["summary"]["bad_count"] == 1
    assert ai["calls"] == []
    resp = client.patch(
        f"{URL}/{body['batch']['id']}/mapping",
        json={"column_mapping": {"date": "A", "description": "B", "amount": "C"}},
    )
    assert resp.status_code == 200
    assert resp.json()["summary"]["valid_count"] == 1
    assert resp.json()["mapping"]["problems"] == []


def test_patch_mapping_reguesses_formats_for_new_columns(client, ai):
    """Cột chưa map lúc upload → định dạng mặc định; chọn cột sau đó mà UI gửi lại định dạng cũ
    → backend đoán lại theo cột mới (không đọc 150,000 thành 150, 09/13 không bị đảo)."""
    content = b'A,B,C\n09/13/2026,CAFE,"-150,000"\n09/14/2026,SALARY,"25,000,000"\n'
    body = _upload(client, "us.csv", content, CSV).json()
    assert body["mapping"]["date_format"] == "dd/mm/yyyy"
    assert body["mapping"]["decimal_style"] == "dot_thousands"
    url = f"{URL}/{body['batch']['id']}/mapping"
    columns = {"date": "A", "description": "B", "amount": "C"}
    resp = client.patch(
        url,
        json={
            "column_mapping": columns,
            "date_format": "dd/mm/yyyy",
            "decimal_style": "dot_thousands",
        },
    ).json()
    assert resp["mapping"]["date_format"] == "mm/dd/yyyy"
    assert resp["mapping"]["decimal_style"] == "comma_thousands"
    assert [(r["occurred_on"], r["amount"], r["direction"]) for r in resp["rows"]] == [
        ("2026-09-13", 150_000, "expense"),
        ("2026-09-14", 25_000_000, "income"),
    ]
    # Cột không đổi, user chủ động chọn định dạng khác → dùng lựa chọn của user.
    explicit = client.patch(
        url,
        json={
            "column_mapping": columns,
            "date_format": "dd/mm/yyyy",
            "decimal_style": "comma_thousands",
        },
    ).json()
    assert explicit["mapping"]["date_format"] == "dd/mm/yyyy"
    assert explicit["summary"]["bad_count"] == 2


def test_mapping_profile_saved_and_reused(client, ai, categories):
    content = "\n".join(
        ["Cột 1;Cột 2;Cột 3", "01/09/2026;CAFE;-45.000", "02/09/2026;TRA SUA;-50.000"]
    ).encode()
    body = _upload(client, "a.csv", content, CSV, bank_name="MB Bank").json()
    batch_id = body["batch"]["id"]
    mapping = {"date": "Cột 1", "description": "Cột 2", "amount": "Cột 3"}
    client.patch(f"{URL}/{batch_id}/mapping", json={"column_mapping": mapping})
    rows = [{"row_index": 2, "category_id": categories["food"]["id"]}]
    assert client.post(f"{URL}/{batch_id}/commit", json={"rows": rows}).status_code == 201

    profiles = client.get(f"{URL}/mapping-profiles", params={"bank_name": "mb bank"}).json()
    assert len(profiles["items"]) == 1
    profile = profiles["items"][0]
    assert profile["bank_name"] == "MB Bank"
    assert profile["column_mapping"]["description"] == "Cột 2"
    assert profile["last_used_at"] is not None

    other = "\n".join(["Cột 1;Cột 2;Cột 3", "05/09/2026;BANH MI;-20.000"]).encode()
    reused = _upload(client, "b.csv", other, CSV, bank_name="MB BANK").json()
    assert reused["mapping"]["source"] == "profile"
    assert reused["mapping"]["profile_id"] == profile["id"]
    assert reused["summary"]["valid_count"] == 1
    # Không nhập tên ngân hàng → dùng profile gần nhất của bộ cột này.
    anonymous = _upload(client, "c.csv", other.replace(b"BANH MI", b"PHO"), CSV).json()
    assert anonymous["mapping"]["source"] == "profile"


# ---------- cảnh báo ----------


def test_transfer_and_possible_manual_duplicate(client, ai, categories):
    manual = client.post(
        "/api/v1/transactions",
        json={
            "direction": "expense",
            "amount": 59_000,
            "occurred_on": "2026-09-05",
            "category_id": categories["food"]["id"],
            "note": "Highlands",
        },
    )
    assert manual.status_code == 201
    body = _preview(client)
    coffee = _row(body, "HIGHLANDS COFFEE VINCOM")
    assert coffee["possible_duplicate_transaction_id"] == manual.json()["id"]
    assert body["summary"]["possible_duplicate_count"] == 1

    lines = ["10/09/2026;THANH TOAN THE TIN DUNG VISA 1234;3.000.000;"]
    transfer = _upload(client, "t.csv", _csv(lines), CSV).json()
    assert transfer["rows"][0]["transfer_hint"] is True
    assert transfer["summary"]["transfer_hint_count"] == 1
    assert any("chuyển khoản nội bộ" in w for w in transfer["warnings"])


# ---------- khác ----------


def test_reupload_preview_reuses_batch(client, ai):
    first = _preview(client)
    second = _preview(client, bank_name="VCB")
    assert first["batch"]["id"] == second["batch"]["id"]
    assert second["batch"]["bank_name"] == "VCB"


@pytest.mark.parametrize(
    ("name", "content", "content_type", "status", "code"),
    [
        ("sao-ke.pdf", b"%PDF-1.4", "application/pdf", 415, "unsupported_file_type"),
        (
            "sao-ke.xls",
            b"\xd0\xcf\x11\xe0",
            "application/vnd.ms-excel",
            415,
            "unsupported_file_type",
        ),
        ("anh.png", b"\x89PNG", "image/png", 415, "unsupported_file_type"),
        ("sao-ke.csv", b"", CSV, 422, "empty_file"),
    ],
)
def test_upload_errors(client, ai, name, content, content_type, status, code):
    resp = _upload(client, name, content, content_type)
    assert resp.status_code == status
    assert resp.json()["code"] == code


def test_upload_too_large(client, ai):
    resp = _upload(client, "big.csv", b"a" * (10 * 1024 * 1024 + 1), CSV)
    assert resp.status_code == 413
    assert "10MB" in resp.json()["detail"]


def test_get_unknown_batch(client):
    resp = client.get(f"{URL}/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["code"] == "import_batch_not_found"


def test_get_batch_returns_rows(client, ai):
    body = _preview(client)
    detail = client.get(f"{URL}/{body['batch']['id']}").json()
    assert detail["rows"] == body["rows"]
    assert detail["summary"] == body["summary"]
