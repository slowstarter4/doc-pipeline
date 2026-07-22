"""
노드7: 검토 게이트 (HITL - Human In The Loop)

consistency_check 리포트가 passed=false이면, 여기서 그래프 실행을 멈추고
사람의 승인을 기다린다. LangGraph의 interrupt()가 이 '멈춤'을 담당한다.

동작:
- passed=true  → 멈추지 않고 바로 통과 (approved=True)
- passed=false → interrupt()로 멈춤. 사람이 이슈를 보고 승인/거부를 결정하면
                  그 값이 interrupt() 호출의 반환값으로 들어온다.

주의: interrupt()가 동작하려면 그래프가 checkpointer와 함께 컴파일되어 있어야
하고, invoke 시 thread_id가 지정된 config가 있어야 한다 (main.py 참고).
checkpointer가 없으면 '멈춘 지점'을 기억할 수 없어서 재개가 불가능하다.
"""

from langgraph.types import interrupt

from ..state import PipelineState


def review_gate_node(state: PipelineState) -> dict:
    report = state["consistency_report"]

    if report.get("passed") is True:
        return {"approved": True}

    # passed가 false(또는 파싱 실패 등으로 없음) → 사람에게 판단을 넘긴다.
    # interrupt()에 넘긴 dict는 사람(main.py)이 볼 수 있는 '질문 페이로드'다.
    decision = interrupt({
        "question": "일관성 체크에서 문제가 발견되었습니다. 그래도 백엔드 코드 생성을 진행할까요?",
        "issues": report.get("issues", []),
    })

    return {"approved": decision == "approve"}
