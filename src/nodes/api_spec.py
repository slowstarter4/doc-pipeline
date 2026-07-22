"""
노드4: 요구사항 + 화면설계서 + ERD → API 명세(JSON)   [fan-in]

파이프라인의 심장. 백엔드/프론트가 공유할 '계약'을 여기서 뽑는다.
markdown이 아니라 dict(JSON)으로 뽑아야 다음 단계에서 프로그램으로 검사 가능.

fan-in 지점: 화면설계서('UI가 필요로 하는 것')와 ERD('실제로 존재하는 데이터')
둘 다를 근거로 삼아야, API가 존재하지 않는 필드를 지어내거나 화면이 필요로
하는 걸 빠뜨리는 걸 막을 수 있다.
"""

import json

from ..llm import call_llm, strip_json
from ..state import PipelineState

_SCHEMA_HINT = (
    "너는 화면설계서와 데이터 모델을 REST API 명세로 종합하는 설계자다. "
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "endpoints": [\n'
    '    {"method": "GET|POST|PUT|DELETE",\n'
    '     "path": "/resource",\n'
    '     "summary": "이 엔드포인트가 하는 일",\n'
    '     "request": {"필드명": "타입"},\n'
    '     "response": {"필드명": "타입"}}\n'
    "  ]\n"
    "}\n\n"
    "중요: 복수의 리소스를 반환하는 목록 조회 GET 엔드포인트(예: '~목록 조회')는 "
    "response를 반드시 배열로 감싼 형태로 정의한다. "
    '예: {"todos": [{"id": "number", "title": "string", ...}]}. '
    "단일 항목 하나만 반환하는 것처럼(배열 없이 필드를 바로 나열) 정의하지 않는다. "
    "단일 리소스를 반환하는 엔드포인트(생성/조회 1건/수정)만 배열 없이 필드를 바로 나열한다."
)


def api_spec_node(state: PipelineState) -> dict:
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    user = (
        f"[요구사항정의서]\n{state['requirements']}\n\n"
        f"[화면설계서]\n{state['screen_design']}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        "위 세 문서를 근거로 API 명세를 JSON으로 만들어줘. "
        "화면이 필요로 하는 데이터는 반드시 ERD에 실제로 존재하는 필드여야 하고, "
        "ERD에 없는 필드를 지어내지 않는다. 요구사항에 있는 기능만 엔드포인트로 만든다. "
        "path에 {id}처럼 경로 파라미터로 이미 받는 필드는 request body에 중복으로 넣지 않는다. "
        "목록 조회 엔드포인트의 response는 반드시 배열을 포함해야 한다."
    )
    raw = call_llm(_SCHEMA_HINT, user)
    try:
        spec = strip_json(raw)
    except json.JSONDecodeError:
        # 파싱 실패 시 원문을 남겨 어디서 깨졌는지 볼 수 있게
        spec = {"_parse_error": True, "_raw": raw}
    return {"api_spec": spec}
