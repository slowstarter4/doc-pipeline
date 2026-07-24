"""
그래프 조립. 노드를 등록하고 엣지로 배선한다.

현재(v9): requirements → {screen_design, data_model} → api_spec
          → openapi_spec → consistency_check → review_gate
          → (조건부) fan-out:
               backend  → write_backend  → verify_backend  → (조건부 루프) | END
               frontend → write_frontend → verify_frontend → END
             | END (거부 시)

openapi_spec은 api_spec을 정식 OpenAPI 3.0 문서로 규칙 기반 변환한다.
consistency_check는 여전히 api_spec(내부 단순 포맷)을 보고 판단하며,
openapi_spec은 나중에 schemathesis 등 외부 도구가 실제 서버를 검사할 때
쓰는 산출물이다 (write_backend가 generated/backend/openapi.json으로 저장).

review_gate가 이 파이프라인의 첫 조건부 라우팅 지점이다:
  - consistency_report.passed == true  → 안 멈추고 바로 backend로
  - passed == false                    → interrupt()로 멈춤. 사람이 승인하면
                                          backend로, 거부하면 END로 (조건부 엣지)

build_pipeline(checkpointer)에 checkpointer를 반드시 넘겨야 interrupt/resume이
동작한다 (멈춘 지점의 상태를 기억해야 재개가 가능하므로). main.py에서
MemorySaver를 만들어 넘긴다.

review_gate 이후 새로 생긴 자기 수정 루프:
  backend → write_backend(디스크에 씀) → verify_backend(fastapi만 실제 실행·검증)
  → 조건부:
      - verify_report.passed == True           → END
      - passed == False AND retry_count < 최대  → backend로 루프백 (재시도, 실패 로그 포함)
      - passed == False AND retry_count >= 최대 → END (사람이 나중에 로그 보고 판단)

fastapi 이외의 스택은 verify_backend가 항상 passed=True로 통과시키므로 루프를
안 탄다 (자동 실행 검증은 fastapi 전용, 다른 스택은 여전히 사람이 수동 검증).

프론트 갈래는 백엔드와 나란히(fan-out) 돌고, backend와 대칭인 자기 수정 루프를 갖는다:
  frontend → write_frontend → verify_frontend(서버 없이 파일에서 fetch 경로·응답 wrapper
  key를 결정적으로 대조) → 조건부:
      - frontend_report.passed == True                   → END
      - passed == False AND frontend_retry_count < 최대   → frontend로 루프백 (실패 로그 포함)
      - passed == False AND frontend_retry_count >= 최대  → END
둘은 서로의 산출물을 안 보고 api_spec만 공유하므로 순서를 정할 이유가 없다. 진단이
성숙해진 뒤(경로 + 응답 모양 검사) 루프백을 붙였다("진단과 수정은 단계적으로").

구현체는 .env로 고른다: BACKEND_TARGET(fastapi/spring/express/typescript),
FRONTEND_TARGET(vanilla/react). 둘 다 레지스트리 딕셔너리 조회이므로 스택을
추가해도 이 파일의 배선은 안 바뀐다.

아직 없음: 재시도 소진 시 사람에게 interrupt()로 명시적 알림 (지금은 조용히
END로 빠지고 main.py가 리포트를 출력해서 사람이 보게 한다).
"""

import os

from langgraph.graph import StateGraph, END

from .state import PipelineState
from .nodes import (
    requirements_node,
    screen_design_node,
    data_model_node,
    schema_ddl_node,
    api_spec_node,
    openapi_spec_node,
    consistency_check_node,
    review_gate_node,
    write_backend_node,
    verify_backend_node,
    write_frontend_node,
    verify_frontend_node,
    BACKEND_NODES,
    FRONTEND_NODES,
)

MAX_BACKEND_RETRIES = 3
MAX_FRONTEND_RETRIES = 3


def _route_after_review(state: PipelineState) -> list[str]:
    """review_gate 이후 어디로 갈지 결정하는 조건부 엣지 함수.

    리스트를 반환하면 LangGraph가 그만큼 fan-out 시킨다. 승인되면 backend와
    frontend가 동시에 출발한다 - 둘 다 api_spec만 보고, 서로의 산출물을 안
    보므로 순서가 없다.
    """
    return ["backend", "frontend"] if state.get("approved") else ["end"]


def _route_after_verify(state: PipelineState) -> str:
    """verify_backend 이후: 통과/재시도/포기 판단."""
    report = state.get("verify_report") or {}
    if report.get("passed"):
        return "end"

    retry_count = state.get("retry_count", 0)
    if retry_count < MAX_BACKEND_RETRIES:
        return "retry"
    return "end"


def _increment_retry(state: PipelineState) -> dict:
    """재시도 카운터만 증가시키는 아주 작은 노드.
    (조건부 엣지 함수 자체는 상태를 못 바꾸므로, 카운트 증가는 별도 노드로 뺀다.)"""
    return {"retry_count": state.get("retry_count", 0) + 1}


def _route_after_frontend_verify(state: PipelineState) -> str:
    """verify_frontend 이후: 통과/재시도/포기 판단 (backend 루프와 같은 방식).

    verify_frontend는 서버를 안 띄우고 파일에서 fetch 경로·응답 wrapper key를 대조하는
    결정적 검사다. passed=False면(경로 계약 위반 또는 응답 모양 불일치) 실패 로그를
    프롬프트에 실어 frontend를 재생성한다. 호출 0건·안 쓰는 경로 같은 진단은 passed에
    안 들어가므로(verify_frontend 참고) 루프를 안 태운다."""
    report = state.get("frontend_report") or {}
    if report.get("passed"):
        return "end"

    retry_count = state.get("frontend_retry_count", 0)
    if retry_count < MAX_FRONTEND_RETRIES:
        return "retry"
    return "end"


def _increment_frontend_retry(state: PipelineState) -> dict:
    return {"frontend_retry_count": state.get("frontend_retry_count", 0) + 1}


def build_pipeline(checkpointer=None):
    g = StateGraph(PipelineState)

    g.add_node("requirements", requirements_node)
    g.add_node("screen_design", screen_design_node)
    g.add_node("data_model", data_model_node)
    g.add_node("schema_ddl", schema_ddl_node)
    g.add_node("api_spec", api_spec_node)
    g.add_node("openapi_spec", openapi_spec_node)
    g.add_node("consistency_check", consistency_check_node)
    g.add_node("review_gate", review_gate_node)

    target = os.getenv("BACKEND_TARGET", "fastapi").lower()
    if target not in BACKEND_NODES:
        options = ", ".join(BACKEND_NODES.keys())
        raise ValueError(
            f"알 수 없는 BACKEND_TARGET='{target}'. 사용 가능한 값: {options}"
        )
    g.add_node("backend", BACKEND_NODES[target])
    g.add_node("write_backend", write_backend_node)
    g.add_node("verify_backend", verify_backend_node)
    g.add_node("bump_retry", _increment_retry)

    fe_target = os.getenv("FRONTEND_TARGET", "vanilla").lower()
    if fe_target not in FRONTEND_NODES:
        options = ", ".join(FRONTEND_NODES.keys())
        raise ValueError(
            f"알 수 없는 FRONTEND_TARGET='{fe_target}'. 사용 가능한 값: {options}"
        )
    g.add_node("frontend", FRONTEND_NODES[fe_target])
    g.add_node("write_frontend", write_frontend_node)
    g.add_node("verify_frontend", verify_frontend_node)
    g.add_node("bump_frontend_retry", _increment_frontend_retry)

    g.set_entry_point("requirements")

    # fan-out
    g.add_edge("requirements", "screen_design")
    g.add_edge("requirements", "data_model")

    # data_model은 결정적 DDL 변환(schema_ddl)을 거쳐 api_spec으로 간다. schema_ddl은
    # openapi_spec과 같은 곁가지 성격(LLM 없는 결정적 변환)이라 직렬로 끼워도 지연이
    # 없다. data_model 결과는 state에 남으므로 api_spec은 여전히 ERD를 읽는다.
    g.add_edge("data_model", "schema_ddl")

    # fan-in: api_spec은 screen_design(병렬)과 schema_ddl(data_model 경유) 둘 다 기다린다.
    # LangGraph의 암묵적 join은 두 갈래가 requirements로부터 같은 홉 수로 도착해야
    # api_spec을 한 번만 실행한다. schema_ddl이 끼면서 data_model 쪽만 2홉(requirements
    # → data_model → schema_ddl)이 되고 screen_design은 1홉이라 어긋난다 - 실제로 이
    # 상태에서 api_spec(LLM 호출, 비결정적)이 한 실행 안에서 두 번 돌아 서로 다른 결과를
    # 냈고, 그게 review_gate까지 두 번 이어져 두 번째 승인 직후 verify_report 동시 쓰기
    # 충돌(InvalidUpdateError)로 죽었다. screen_design 쪽에 아무 일도 안 하는 통과 노드를
    # 하나 끼워 넣어 홉 수를 맞춘다.
    g.add_node("screen_design_sync", lambda state: {})
    g.add_edge("screen_design", "screen_design_sync")
    g.add_edge("screen_design_sync", "api_spec")
    g.add_edge("schema_ddl", "api_spec")

    g.add_edge("api_spec", "openapi_spec")
    g.add_edge("openapi_spec", "consistency_check")
    g.add_edge("consistency_check", "review_gate")

    # 승인되면 backend / frontend 두 갈래로 fan-out (같은 api_spec을 소비)
    g.add_conditional_edges(
        "review_gate",
        _route_after_review,
        {"backend": "backend", "frontend": "frontend", "end": END},
    )

    # 프론트 갈래: 생성 → 쓰기 → 계약 대조(결정적) → 조건부 루프백 (backend와 대칭)
    g.add_edge("frontend", "write_frontend")
    g.add_edge("write_frontend", "verify_frontend")
    g.add_conditional_edges(
        "verify_frontend",
        _route_after_frontend_verify,
        {"end": END, "retry": "bump_frontend_retry"},
    )
    g.add_edge("bump_frontend_retry", "frontend")  # 재시도: frontend로 루프백

    g.add_edge("backend", "write_backend")
    g.add_edge("write_backend", "verify_backend")

    g.add_conditional_edges(
        "verify_backend",
        _route_after_verify,
        {"end": END, "retry": "bump_retry"},
    )
    g.add_edge("bump_retry", "backend")  # 재시도: backend로 루프백

    return g.compile(checkpointer=checkpointer)
