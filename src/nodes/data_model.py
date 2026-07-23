"""
노드3b: 요구사항 → 데이터 모델(ERD)

'실제로 존재하는 데이터'를 정의한다. JSON(dict)으로 뽑는다 - API 명세 노드가
기계적으로 파싱해서 필드 존재 여부를 검사할 수 있어야 하기 때문.
"""

import json

from ..llm import call_llm, strip_json
from ..state import PipelineState

_SCHEMA_HINT = (
    "너는 요구사항정의서를 읽고 데이터 모델(ERD)을 설계하는 설계자다. "
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "entities": [\n'
    '    {"name": "엔티티명",\n'
    '     "fields": [\n'
    '       {"name": "필드명", "type": "string|number|boolean|date", '
    '"required": true}\n'
    "     ]}\n"
    "  ]\n"
    "}\n\n"
    "entity.name과 field.name은 반드시 영문 camelCase 식별자로 짓는다 "
    "(예: title, dueDate, memberId). 요구사항정의서가 한글이어도 한글 항목명을 "
    "그대로 필드명으로 쓰지 않는다 - 이 ERD가 API 명세로, API 명세가 백엔드·프론트"
    "코드로 그대로 이어지는데, 필드명이 실행마다 한글/영문으로 갈리면 같은 파이프라인"
    "안에서도 백엔드와 프론트가 서로 다른 이름을 기대하게 되어 요청이 전부 거부된다."
)


def data_model_node(state: PipelineState) -> dict:
    user = (
        f"[요구사항정의서]\n{state['requirements']}\n\n"
        "위 요구사항을 근거로 필요한 엔티티와 필드를 JSON으로 설계해줘. "
        "요구사항에 나온 데이터만 포함한다."
    )
    raw = call_llm(_SCHEMA_HINT, user)
    try:
        model = strip_json(raw)
    except json.JSONDecodeError:
        model = {"_parse_error": True, "_raw": raw}
    return {"data_model": model}
