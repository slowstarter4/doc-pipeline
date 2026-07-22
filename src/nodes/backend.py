"""
노드6: API 명세 + ERD → 백엔드 코드 (FastAPI)

지금까지는 문서만 만들었다. 여기서 처음으로 '검증 가능한 출력을 내는 책임 단위'가
문서에서 코드로 넘어간다. API 명세가 곧 계약이므로, 이 노드는 명세에 정의된
엔드포인트만 구현하고 그 이상을 지어내지 않는다.

출력 형식: {"files": [{"path": "상대경로", "content": "파일 내용"}]}
"""

import json

from ..llm import call_llm, strip_json
from ..state import PipelineState

_SCHEMA_HINT = (
    "너는 API 명세와 데이터 모델을 보고 실제로 동작하는 FastAPI 백엔드를 작성하는 "
    "백엔드 개발자다. 다음 규칙을 반드시 지킨다:\n"
    "- API 명세에 정의된 엔드포인트만 구현한다. 명세에 없는 엔드포인트를 추가하지 않는다.\n"
    "- ERD에 정의된 필드만 사용한다.\n"
    "- 데이터는 파이썬 표준 라이브러리 sqlite3로 파일 DB에 저장한다. DB 파일명은 "
    "도메인에 맞게 정하되 확장자는 .db로 한다(예: library.db). 앱 시작 시 "
    "CREATE TABLE IF NOT EXISTS로 필요한 테이블을 전부 만든다. "
    "외부 DB 서버나 ORM(SQLAlchemy 등)을 쓰지 않는다 - requirements.txt에 DB 관련 "
    "패키지를 추가하지 않는다. 서버를 껐다 켜도 데이터가 남아있어야 한다 "
    "(메모리 리스트에만 담아두면 안 된다).\n"
    "- sqlite3 연결은 요청마다 새로 열고 닫는다. FastAPI는 요청을 여러 스레드에서 "
    "처리하므로 전역 커넥션 하나를 공유하면 'SQLite objects created in a thread can "
    "only be used in that same thread' 오류가 난다. 전역 커넥션을 쓰려면 "
    "check_same_thread=False가 필요하지만, 요청마다 sqlite3.connect(...)로 열고 "
    "with 블록이나 try/finally로 닫는 쪽이 단순하고 안전하다.\n"
    "- id는 INTEGER PRIMARY KEY AUTOINCREMENT로 DB가 매기게 한다. 파이썬 쪽에서 "
    "카운터 변수로 세지 않는다 (재기동하면 카운터가 초기화되어 id가 겹친다).\n"
    "- boolean 필드는 sqlite에 0/1 정수로 저장되므로, 응답으로 내보낼 때 "
    "bool()로 변환해서 JSON에 true/false로 나가게 한다 (0/1이 그대로 나가면 "
    "명세의 boolean 타입과 어긋난다).\n"
    "- pydantic 모델로 request/response 스키마를 명세와 정확히 일치시킨다.\n"
    "- 존재하지 않는 id로 요청 시 404를 반환한다.\n"
    "- 리소스를 새로 만드는 POST 엔드포인트는 성공 시 기본값인 200이 아니라 "
    "201(Created)로 응답해야 한다. FastAPI 라우트 데코레이터에 "
    "status_code=status.HTTP_201_CREATED를 명시한다.\n"
    "- 처리되지 않은 예외가 500으로 그대로 클라이언트에 노출되지 않게 한다. "
    "요청 본문 검증·처리 과정에서 예상 못한 타입(예: dueDate에 객체나 배열이 옴)이 "
    "들어와도 서버가 죽지 않고 400을 반환하도록, 각 엔드포인트 핸들러를 try/except로 "
    "감싸거나 전역 예외 핸들러(@app.exception_handler(Exception))를 등록해서 "
    "예기치 못한 예외까지 400(또는 명백한 서버 버그일 때만 500)으로 변환한다.\n"
    "- request body의 유효성을 검증한다: ERD의 required 필드가 빠졌거나, 타입이 "
    "안 맞으면(예: title에 문자열 대신 숫자, dueDate가 유효한 날짜 형식이 아님) "
    "HTTP 400과 함께 에러 메시지를 JSON으로 반환한다. pydantic 모델의 타입을 "
    "정확히 지정해서(예: dueDate: date) 프레임워크가 자동으로 걸러내게 하고, "
    "FastAPI 기본 검증 실패 응답(422)이 아니라 400으로 나가도록 예외 핸들러를 "
    "등록한다 (RequestValidationError를 잡아 400으로 변환).\n"
    "- pydantic은 기본적으로 관대해서 숫자 0을 날짜로 타입 강제변환(coercion)해버릴 "
    "수 있다 (0을 1970-01-01로 해석하는 식). 이렇게 되면 잘못된 타입이 조용히 "
    "통과해버려 검증이 무력화된다. 다만 모델 전체에 strict=True를 걸면 JSON에서 "
    '항상 문자열로 오는 정상적인 ISO 날짜(예: "2000-01-01")까지 거부되어 버리므로 '
    "절대 그렇게 하지 않는다. 대신 date 타입 필드에는 "
    "@field_validator(필드명, mode='before')로 사전 검증기를 달아서, 들어온 원본 "
    "값이 str이 아니면(예: int, float, bool) ValueError를 던져 거부하고, str이면 "
    "그대로 통과시켜 pydantic의 기본 날짜 파싱이 정상 동작하게 한다.\n"
    "- required의 의미는 '필드가 존재해야 한다(누락/null이면 안 됨)'는 뜻이지, "
    "'값이 비어있으면 안 된다'는 뜻이 아니다. 예를 들어 title이 빈 문자열(\"\")로 "
    "와도 필드 자체는 존재하므로 유효한 요청으로 받아들인다. pydantic에서 "
    "Optional이 아닌 str 타입은 이 구분을 기본으로 올바르게 처리하니, 별도로 "
    "빈 문자열을 거부하는 추가 검증을 넣지 않는다.\n"
    "- 프론트엔드가 브라우저에서 이 API를 호출한다. CORS를 열지 않으면 브라우저가 "
    "요청을 막아 프론트가 아무 데이터도 못 받는다. fastapi.middleware.cors의 "
    "CORSMiddleware를 등록하고 allow_origins=['*'], allow_methods=['*'], "
    "allow_headers=['*']로 개발용 전체 허용을 설정한다.\n"
    "- 코드는 그대로 실행 가능해야 한다 (문법 오류·미완성 코드 금지).\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "files": [\n'
    '    {"path": "상대경로 (예: main.py)", "content": "파일 전체 내용"}\n'
    "  ]\n"
    "}"
)


def backend_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    user = (
        f"[API 명세]\n{api_spec_json}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        "위 API 명세와 데이터 모델로 FastAPI 백엔드를 작성해줘. "
        "단일 main.py 파일로 충분하다. requirements.txt도 함께 만들어줘 "
        "(fastapi, uvicorn 포함)."
    )

    # 재시도 루프: 이전 시도가 실패했다면 그 원인을 프롬프트에 포함해서
    # 같은 실수를 반복하지 않게 한다 (verify_backend_node가 채워준 verify_report).
    prev = state.get("verify_report")
    if prev and prev.get("passed") is False:
        user += (
            f"\n\n[이전 시도 실패 로그 - 이 문제를 반드시 고쳐서 다시 작성해줘]\n"
            f"{prev.get('logs', '')}"
        )

    raw = call_llm(_SCHEMA_HINT, user, max_tokens=8192)
    try:
        result = strip_json(raw)
    except json.JSONDecodeError:
        result = {"_parse_error": True, "_raw": raw}

    return {"backend_code": result}
