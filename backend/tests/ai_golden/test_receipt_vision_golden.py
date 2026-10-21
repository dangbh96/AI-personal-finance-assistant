"""Golden test Receipt OCR (Phase 13) — gọi OpenAI vision thật: `pytest -m ai -s`.

5 ảnh hoá đơn **tổng hợp** trong `receipts/` (sinh bằng `receipts/generate_receipts.py`) + file
expected `*.yaml` cạnh ảnh. Ngưỡng pass (phase-13 § 4.3, § 6 test case 8):
- tổng tiền đúng ≥ 4/5 (ảnh `unreadable` tính đúng khi `total = null`);
- tên cửa hàng khớp (chuẩn hoá: bỏ dấu, chữ thường, chứa nhau) ≥ 3/5;
- ảnh `unreadable` không được bịa tổng tiền và phải ra receipt `failed` (không có draft).
"""

import re
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from app.ai import openai_client, receipt_vision
from app.core.text import strip_accents
from app.services import receipt_mapping, receipt_storage

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

SAMPLES_DIR = Path(__file__).parent / "receipts"
CASES = [
    yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(SAMPLES_DIR.glob("*.yaml"))
]
TODAY = date(2026, 10, 22)
MIN_TOTAL_CORRECT = 4
MIN_MERCHANT_MATCH = 3


def _report(text: str) -> None:
    """In báo cáo; console Windows (cp1252) không in được tiếng Việt → thay ký tự lỗi."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


def normalize_merchant(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", strip_accents(name or "").lower())


def merchant_matches(expected: str | None, actual: str | None) -> bool:
    if expected is None:
        return actual is None or not actual.strip()
    exp, act = normalize_merchant(expected), normalize_merchant(actual)
    return bool(act) and (exp in act or act in exp)


def test_golden_set_has_five_samples():
    names = sorted(case["file"] for case in CASES)
    assert names == [
        "blurry_photo.jpg",
        "coffee_shop.jpg",
        "handwritten.jpg",
        "restaurant.jpg",
        "supermarket.jpg",
    ]
    assert all((SAMPLES_DIR / name).is_file() for name in names)


def test_receipt_vision_golden_set(db):
    total_correct = merchant_match = merchant_total = 0
    class_hits = class_total = 0
    hallucinations: list[str] = []
    rows: list[str] = []

    for case in CASES:
        content = (SAMPLES_DIR / case["file"]).read_bytes()
        image = receipt_storage.validate_image(content, case["mime_type"], case["file"])
        payload, mime_type = receipt_storage.vision_payload(image.content, image.mime_type)
        analysis = receipt_vision.analyze(db, payload, mime_type, today=TODAY)
        assert analysis.output is not None, f"{case['file']}: AI lỗi {analysis.error_code}"
        out = analysis.output
        suggestion = analysis.suggestion
        assessment = receipt_mapping.assess_extraction(out)

        if case["unreadable"]:
            ok_total = out.total is None
            if out.total is not None or assessment.usable:
                hallucinations.append(
                    f"{case['file']}: total={out.total} usable={assessment.usable}"
                )
        else:
            ok_total = out.total == case["total"]
        total_correct += ok_total

        ok_merchant = None
        if case["merchant"] is not None:
            merchant_total += 1
            ok_merchant = merchant_matches(case["merchant"], out.merchant)
            merchant_match += ok_merchant
        ok_date = case["date"] is None or out.date == case["date"]
        if case["category_slug"] is not None and suggestion is not None:
            class_total += 1
            class_hits += (
                suggestion.category_slug == case["category_slug"]
                and suggestion.spending_type == case["spending_type"]
            )

        rows.append(
            f"{case['file']:<18} total={out.total!s:<9} exp={case['total']!s:<9} "
            f"{'OK ' if ok_total else 'SAI'} | merchant={out.merchant!r} "
            f"{'' if ok_merchant is None else ('OK' if ok_merchant else 'SAI')} | "
            f"date={out.date} {'OK' if ok_date else 'SAI'} | conf={out.confidence:.2f} | "
            f"category={suggestion.category_slug if suggestion else None}/"
            f"{suggestion.spending_type if suggestion else None} "
            f"(exp {case['category_slug']}/{case['spending_type']}) | "
            f"items={len(out.items)} | usable={assessment.usable} {assessment.error_code or ''} | "
            f"reason={out.unreadable_reason!r}"
        )

    _report("\n".join(["", "Receipt OCR golden set:", *rows]))
    _report(
        f"total đúng {total_correct}/{len(CASES)} (ngưỡng {MIN_TOTAL_CORRECT}) · "
        f"merchant khớp {merchant_match}/{merchant_total} (ngưỡng {MIN_MERCHANT_MATCH}) · "
        f"danh mục + loại chi tiêu {class_hits}/{class_total} (chỉ báo cáo)"
    )
    assert not hallucinations, f"Bịa tổng tiền cho ảnh không đọc được: {hallucinations}"
    assert total_correct >= MIN_TOTAL_CORRECT
    assert merchant_match >= MIN_MERCHANT_MATCH
