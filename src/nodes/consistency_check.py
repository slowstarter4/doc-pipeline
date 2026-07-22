"""
노드5: 일관성 체크 (요구사항 + 화면설계서 + ERD + API명세 → 진단 리포트)

지금까지 만든 문서들을 서로 대조해서 불일치·애매함을 찾아낸다.
코드를 고치지 않고 '진단'만 한다 - 자동 수정/루프백은 다음 단계(HITL)에서 붙인다.

체크 대상 예시:
- 화면이 표시/입력하는 필드가 ERD에 실제로 존재하는가
- API 요청/응답 필드가 ERD와 이름·타입이 일치하는가
- 요구사항이 애매해서(예: 필수 여부 불명) 뒷단이 임의로 판단한 지점이 있는가
- 모든 화면 액션이 API 엔드포인트로 커버되는가
"""

import json

from ..llm import call_llm, strip_json
from ..state import PipelineState

_SCHEMA_HINT = (
    "너는 개발 문서 간 일관성을 검토하는 QA 검토자다. "
    "요구사항정의서, 화면설계서, 데이터 모델(ERD), API 명세 네 문서를 서로 대조해서 "
    "불일치나 애매한 지점을 찾는다. 코드를 고치거나 문서를 수정하지 않고 진단만 한다.\n\n"
    "다음 관점으로 확인한다:\n"
    "1. 화면이 표시/입력하는 필드가 ERD에 실제로 존재하는가\n"
    "2. API 요청/응답 필드명·타입이 ERD와 일치하는가\n"
    "3. 요구사항이 애매해서 뒷단(화면설계/ERD/API)이 임의로 판단을 내린 지점이 있는가 "
    "(예: 필수 여부 불명, 기본값 불명)\n"
    "4. 화면의 모든 사용자 액션이 API 엔드포인트로 커버되는가\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "passed": true|false,\n'
    '  "issues": [\n'
    '    {"severity": "error|warning",\n'
    '     "location": "어느 문서/필드에 관한 것인지",\n'
    '     "description": "무엇이 문제인지, 왜 문제인지"}\n'
    "  ]\n"
    "}\n"
    "error는 실제 불일치(필드 없음, 타입 다름 등), warning은 애매함/암묵적 판단."
)


def consistency_check_node(state: PipelineState) -> dict:
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    user = (
        f"[요구사항정의서]\n{state['requirements']}\n\n"
        f"[화면설계서]\n{state['screen_design']}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        f"[API 명세]\n{api_spec_json}\n\n"
        "위 네 문서를 대조해서 일관성 리포트를 JSON으로 작성해줘."
    )
    raw = call_llm(_SCHEMA_HINT, user)
    try:
        report = strip_json(raw)
    except json.JSONDecodeError:
        report = {"_parse_error": True, "_raw": raw}
    return {"consistency_report": report}
