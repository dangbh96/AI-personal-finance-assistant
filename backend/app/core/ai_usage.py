"""Token / chi phí / latency của các lời gọi AI (Phase 10).

Chi phí chỉ là **ước tính** để theo dõi (giá niêm yết USD / 1 triệu token × tỉ giá cố định), không
phải số liệu tài chính của user. Model không có trong bảng giá → `None`.
"""

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

USD_TO_VND = Decimal(26_000)
# (input, output) USD / 1 triệu token. Khớp theo tiền tố dài nhất ("gpt-4o-mini-2024-07-18").
PRICES_USD_PER_1M: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
}


def _price(model: str) -> tuple[Decimal, Decimal] | None:
    matches = [k for k in PRICES_USD_PER_1M if model == k or model.startswith(k + "-")]
    return PRICES_USD_PER_1M[max(matches, key=len)] if matches else None


def estimate_cost_vnd(model: str | None, input_tokens: int, output_tokens: int) -> int | None:
    """Chi phí ước tính (đồng, làm tròn nửa lên)."""
    price = _price(model) if model else None
    if price is None:
        return None
    usd = (input_tokens * price[0] + output_tokens * price[1]) / Decimal(1_000_000)
    return int((usd * USD_TO_VND).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class UsageTotals:
    """Cộng dồn usage của nhiều lời gọi trong một tác vụ (vd 1 lượt Coach)."""

    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    llm_latency_ms: int = 0

    def add(
        self, model: str, input_tokens: int | None, output_tokens: int | None, latency_ms: int
    ) -> None:
        self.model = model
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0
        self.calls += 1
        self.llm_latency_ms += latency_ms

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_vnd(self) -> int | None:
        return estimate_cost_vnd(self.model, self.input_tokens, self.output_tokens)


def log_usage(task: str, usage: UsageTotals, latency_ms: int, **extra: object) -> None:
    """Một dòng log cho cả tác vụ (không log nội dung prompt / API key)."""
    details = " ".join(f"{k}={v}" for k, v in extra.items())
    logger.info(
        "ai_usage task=%s model=%s calls=%d input_tokens=%d output_tokens=%d cost_vnd=%s "
        "latency_ms=%d %s",
        task,
        usage.model,
        usage.calls,
        usage.input_tokens,
        usage.output_tokens,
        usage.estimated_cost_vnd,
        latency_ms,
        details,
    )
