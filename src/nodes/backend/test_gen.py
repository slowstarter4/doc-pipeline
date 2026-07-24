"""
노드: API 명세(+ERD, rules) → 계약 테스트 생성 (pytest, HTTP 기반)

원래 목표 흐름의 '테스트 생성·실행' 단계. **테스트는 코드가 아니라 명세에서 생성한다**
(CLAUDE.md 아키텍처 규칙) - 생성된 백엔드 코드를 보고 만들면 코드의 버그를 정답으로
박제하게 되므로, api_spec/rules/ERD만 근거로 삼는다. 코드 생성 노드(backend 등)와 같은
계약(api_spec)을 소비하지 다른 산출물을 안 본다.

테스트는 HTTP로 실행 중인 서버를 때린다 - 언어 무관이라 한 벌로 4스택(fastapi/spring/
express/typescript) 전부를 검증할 수 있다(verify_backend 스모크가 스택 무관인 것과 같다).
BASE_URL 환경변수로 대상 서버를 가리키고, 스택마다 포트가 다르므로 사람이 그 값을 맞춘다.

실행은 파이프라인이 자동으로 안 한다 - 사람이 서버를 띄운 뒤 `pytest`로 돌린다
(schemathesis·프론트 npm과 같은 판단: 여러 스택 자동 기동은 깨지기 쉽다. 지금은 생성만).

출력 형식: {"files": [{"path": "상대경로", "content": "파일 내용"}]}
"""

import json

from ...llm import call_llm, strip_json
from ...state import PipelineState

_SCHEMA_HINT = (
    "너는 API 명세와 데이터 모델을 근거로 계약 테스트(pytest)를 작성하는 QA 엔지니어다. "
    "실행 중인 백엔드 서버를 HTTP로 호출해 명세대로 동작하는지 검증한다. 다음 규칙을 "
    "반드시 지킨다:\n"
    "- **명세(API 명세·ERD·rules)만 근거로 테스트를 만든다.** 특정 구현·프레임워크를 "
    "가정하지 않는다 - 같은 테스트가 어느 스택(fastapi/spring/express/typescript)에 붙여도 "
    "돌아야 한다. 순수 requests HTTP 호출로만 검증한다.\n"
    "- 서버 주소는 `BASE = os.environ.get('BASE_URL', 'http://localhost:8000')`로 얻는다. "
    "스택마다 포트가 다르므로(fastapi 8000, spring 8080, express 5001, typescript 5002) "
    "사람이 BASE_URL로 맞춘다. 포트를 코드에 하드코딩하지 않는다.\n"
    "- 각 엔드포인트마다 테스트를 만든다: ①정상 흐름(생성 201 → 조회에 나타남 → 있으면 "
    "수정/삭제) ②존재하지 않는 id 조회·수정·삭제는 404 ③required 필드 누락·타입 불일치는 "
    "400(422가 아니라 400을 기대한다 - 명세가 그렇게 정했다).\n"
    "- **rules에 적힌 업무 규칙 하나하나를 검증하는 테스트를 반드시 만든다.** 이게 이 "
    "테스트의 핵심이다. 예: '회원당 최대 5권' → 5권까지 대출한 뒤 6번째 대출이 400인지, "
    "'이미 대출 중인 도서는 대출 불가' → 같은 도서를 두 번 대출하면 두 번째가 400인지, "
    "'대출일은 자동 기록' → 응답에 loanDate가 채워져 오는지. rules가 빈 배열인 엔드포인트는 "
    "업무 규칙 테스트를 안 만든다.\n"
    "- 생성 데이터는 rules·enum·자릿수 제약을 만족하는 **유효한 값**으로 만든다(예: ISBN은 "
    "13자리 숫자 문자열, category는 명세의 enum 중 하나, 외래키는 먼저 만든 리소스의 실제 "
    "id). 그래야 규칙 위반을 노린 테스트가 아닌 정상 흐름 테스트가 엉뚱한 제약에 막히지 "
    "않는다. 규칙 위반 테스트에서만 일부러 규칙을 어긴다.\n"
    "- 목록 조회 응답은 명세에 정의된 wrapper key로 감싸여 온다(예: {\"books\": [...]}). "
    "그 key로 배열을 꺼내 단언한다.\n"
    "- **각 테스트는 자기가 만든 리소스로만 단언한다.** DB에 이전 실행·다른 테스트가 남긴 "
    "데이터가 있을 수 있으므로, '목록 길이 == 1' 같은 전역 개수에 의존하지 말고 '내가 만든 "
    "id가 목록에 있다'처럼 자기 데이터의 존재/부재로 단언한다. 테스트 간 실행 순서에 "
    "의존하지 않는다.\n"
    "- id 및 외래키(memberId, bookId 등)는 숫자(int)로 다룬다. 명세가 \"string\"으로 적어놨어도 "
    "실제로는 자동증가 정수 PK다.\n"
    "- 파일 구성: `tests/test_contract.py`(테스트 본체), `requirements.txt`(pytest, requests), "
    "`README.md`(BASE_URL을 스택 포트에 맞춰 서버 띄운 뒤 `pip install -r requirements.txt && "
    "pytest`로 돌린다는 실행 안내). 테스트는 함수 이름을 test_로 시작하고, 무엇을 검증하는지 "
    "한국어 주석을 단다.\n"
    "- 코드는 그대로 실행 가능해야 한다 (문법 오류·미완성 코드 금지).\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "files": [\n'
    '    {"path": "상대경로 (예: tests/test_contract.py)", "content": "파일 전체 내용"}\n'
    "  ]\n"
    "}"
)


def test_gen_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    user = (
        f"[API 명세 - 이게 계약이다]\n{api_spec_json}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        "위 명세와 데이터 모델로 계약 테스트(pytest)를 작성해줘. rules에 적힌 업무 규칙을 "
        "빠짐없이 테스트로 옮기는 게 가장 중요하다."
    )
    # 엔드포인트마다 정상·404·400·업무규칙 테스트를 다 만들면 수트가 길어져 8192로는
    # JSON이 잘려 파싱 실패한다(spring 백엔드와 같은 이유). 넉넉히 16384로 둔다.
    raw = call_llm(_SCHEMA_HINT, user, max_tokens=16384)
    try:
        result = strip_json(raw)
    except json.JSONDecodeError:
        result = {"_parse_error": True, "_raw": raw}
    return {"test_code": result}
