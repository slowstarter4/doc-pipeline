"""
노드1: 기획문서 → 요구사항정의서

기획을 '가장 가깝게 읽은' 산출물. 나머지 문서(화면/ERD/API)의 근거가 된다.
기획에 없는 기능을 지어내지 않는 게 핵심.
"""

from ...llm import call_llm
from ...state import PipelineState


def requirements_node(state: PipelineState) -> dict:
    system = (
        "너는 기획문서를 읽고 요구사항정의서를 작성하는 분석가다. "
        "기획에 없는 기능을 지어내지 말고, 기획에 근거해 기능 요구사항을 "
        "번호가 매겨진 목록으로 정리한다. 각 항목은 '무엇을' 하는지 명확히 쓴다."
    )
    user = f"[기획문서]\n{state['plan_doc']}\n\n위 기획으로 요구사항정의서를 작성해줘."
    return {"requirements": call_llm(system, user)}
