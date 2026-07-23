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
    '     "response": {"필드명": "타입"},\n'
    '     "rules": ["이 엔드포인트가 지켜야 할 업무 규칙", "..."]}\n'
    "  ]\n"
    "}\n\n"
    "request/response의 필드명은 ERD에 있는 영문 필드명을 그대로 쓴다. 한글로 "
    "번역하거나 요구사항정의서의 한글 항목명을 옮기지 않는다 - 이 필드명이 그대로 "
    "백엔드 구현과 프론트엔드 호출의 계약이 되는데, 실행마다 한글/영문으로 갈리면 "
    "같은 파이프라인 안에서 만든 백엔드와 프론트가 서로 다른 이름을 기대하게 되어 "
    "요청이 전부 거부된다 (실제로 프론트는 '제목'을, 백엔드는 title을 기대해서 "
    "회원 등록·대출 등록이 전부 400으로 막힌 사고가 있었다).\n\n"
    "rules는 요청을 거부해야 하는 조건과 자동으로 계산·기록되는 값을 적는 자리다. "
    "필드 이름이나 타입으로는 표현되지 않지만 구현이 반드시 지켜야 하는 제약이 "
    "여기 들어간다. 예: '한 회원이 동시에 빌릴 수 있는 책은 최대 5권. 초과 시 "
    "400과 함께 어떤 제약에 걸렸는지 알린다', '대출일은 입력받지 않고 처리 시점의 "
    "날짜로 자동 기록한다', '이미 대출 중인 도서는 대출할 수 없다'. "
    "요구사항정의서에 있는 제약을 빠짐없이 해당 엔드포인트의 rules로 옮긴다 - "
    "여기 안 적히면 구현에 반영되지 않는다. 코드를 만드는 노드는 이 명세만 보고 "
    "기획문서를 보지 않기 때문이다. 제약이 없는 엔드포인트는 빈 배열로 둔다.\n\n"
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
        "목록 조회 엔드포인트의 response는 반드시 배열을 포함해야 한다. "
        "요구사항정의서의 제약(거부 조건, 자동 계산·기록되는 값, 상태 전이 제한)을 "
        "빠짐없이 해당 엔드포인트의 rules에 옮긴다."
    )
    raw = call_llm(_SCHEMA_HINT, user)
    try:
        spec = strip_json(raw)
    except json.JSONDecodeError:
        # 파싱 실패 시 원문을 남겨 어디서 깨졌는지 볼 수 있게
        spec = {"_parse_error": True, "_raw": raw}
    return {"api_spec": spec}
