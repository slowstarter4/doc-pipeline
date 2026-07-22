"""
노드3a: 요구사항 → 화면설계서

'UI가 필요로 하는 것'을 정의한다. markdown으로 뽑는다 - 사람이 읽고
리뷰하는 문서 성격이 강해서, 억지로 JSON 구조화하면 표현력이 죽는다.
"""

from ..llm import call_llm
from ..state import PipelineState


def screen_design_node(state: PipelineState) -> dict:
    system = (
        "너는 요구사항정의서를 읽고 화면설계서를 작성하는 UI 설계자다. "
        "요구사항에 있는 기능을 수행하는 데 필요한 화면만 정의한다. "
        "각 화면마다 목적, 화면에 표시되는 데이터 항목, 사용자가 취할 수 있는 "
        "액션(버튼/입력 등)을 명시한다. 요구사항에 없는 화면이나 기능을 추가하지 않는다."
    )
    user = (
        f"[요구사항정의서]\n{state['requirements']}\n\n"
        "위 요구사항으로 화면설계서를 작성해줘. 화면 단위로 나눠서 정리해."
    )
    return {"screen_design": call_llm(system, user)}
