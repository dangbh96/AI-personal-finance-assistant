import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.ai import simulator_writer
from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.simulator import (
    ScenarioCreate,
    ScenarioList,
    ScenarioRead,
    SimulationOptions,
    SimulationRequest,
    SimulationResult,
)
from app.services import simulator_service

router = APIRouter(prefix="/simulator", tags=["simulator"])

Today = Annotated[
    date | None, Query(description="Hôm nay phía user (mặc định của server) — demo / test")
]


@router.post("/run", response_model=SimulationResult, responses={422: {"model": ErrorResponse}})
def run(db: DbSession, data: SimulationRequest, today: Today = None):
    """Chạy kịch bản what-if trên mức trung bình các tháng gần nhất — **không ghi** giao dịch,
    ngân sách hay mục tiêu. `with_narrative` → diễn giải 3 tầng (AI `OPENAI_MODEL_FAST`; AI lỗi →
    bản mẫu, không trả 503)."""
    options = SimulationOptions(
        params=data.params,
        baseline_months=data.baseline_months,
        include_irregular=data.include_irregular,
    )
    start = simulator_service.request_start(data, today or date.today())
    result = simulator_service.run_simulation(db, options, start_date=start)
    if data.with_narrative:
        narrative, source, model = simulator_writer.write_narrative(result)
        result = result.model_copy(
            update={"narrative": narrative, "narrative_source": source, "narrative_model": model}
        )
    return result


@router.get("/scenarios", response_model=ScenarioList)
def list_scenarios(db: DbSession):
    return simulator_service.list_scenarios(db)


@router.post(
    "/scenarios",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
def create_scenario(db: DbSession, data: ScenarioCreate, today: Today = None):
    """Lưu kịch bản (tên + tham số) kèm kết quả mô phỏng tại thời điểm lưu."""
    return simulator_service.create_scenario(db, data, today or date.today())


@router.delete(
    "/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={404: {"model": ErrorResponse}},
)
def delete_scenario(db: DbSession, scenario_id: uuid.UUID) -> Response:
    simulator_service.delete_scenario(db, scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
