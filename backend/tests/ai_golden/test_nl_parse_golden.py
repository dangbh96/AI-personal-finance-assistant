"""Golden test NL parse (Phase 2) — gọi OpenAI thật: `pytest -m ai -s`.

Ngưỡng pass (phase-02 § 6): amount 100%, direction 100%, occurred_on >= 90%,
category_slug >= 80%, spending_type >= 80%, số giao dịch tách được 100%.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from app.ai import nl_transaction_parser, openai_client

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

CASES = json.loads((Path(__file__).parent / "nl_parse_cases.json").read_text(encoding="utf-8"))
FIELDS = ("amount", "direction", "occurred_on", "category_slug", "spending_type")
THRESHOLDS = {
    "count": 1.0,
    "amount": 1.0,
    "direction": 1.0,
    "occurred_on": 0.9,
    "category_slug": 0.8,
    "spending_type": 0.8,
}


def _report(text: str) -> None:
    """In báo cáo; console Windows (cp1252) không in được tiếng Việt → thay ký tự lỗi."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


def test_nl_parse_golden_set(db):
    hits = dict.fromkeys(THRESHOLDS, 0)
    totals = dict.fromkeys(THRESHOLDS, 0)
    failures: list[str] = []

    for case in CASES:
        result = nl_transaction_parser.parse_transactions(
            db, case["text"], today=date.fromisoformat(case["today"])
        )
        actual = [d.model_dump(mode="json") for d in result.drafts]
        expected = case["expected"]

        totals["count"] += 1
        if len(actual) == len(expected):
            hits["count"] += 1
        else:
            failures.append(f"{case['text']!r}: {len(actual)} draft, mong đợi {len(expected)}")

        for i, exp in enumerate(expected):
            got = actual[i] if i < len(actual) else {}
            for field in FIELDS:
                totals[field] += 1
                if got.get(field) == exp[field]:
                    hits[field] += 1
                else:
                    failures.append(
                        f"{case['text']!r} #{i + 1} {field}: {got.get(field)!r} ≠ {exp[field]!r}"
                    )
        _report(f"\n{case['text']!r} → {json.dumps(actual, ensure_ascii=False)}")
        if result.warnings:
            _report(f"   warnings: {result.warnings}")

    scores = {k: hits[k] / totals[k] for k in THRESHOLDS}
    report = "\n".join(
        f"  {k:<14} {hits[k]:>2}/{totals[k]:<2} = {scores[k]:.0%} (ngưỡng {THRESHOLDS[k]:.0%})"
        for k in THRESHOLDS
    )
    _report(f"\nModel: {openai_client.model_fast()}\n{report}")
    if failures:
        _report("Sai lệch:\n  " + "\n  ".join(failures))

    below = [k for k in THRESHOLDS if scores[k] < THRESHOLDS[k]]
    assert not below, f"Dưới ngưỡng: {below}\n{report}\n" + "\n".join(failures)
