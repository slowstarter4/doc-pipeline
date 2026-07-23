"""
노드6c: API 명세 + ERD → 백엔드 코드 (Node.js + Express, JavaScript)

backend.py(FastAPI)와 같은 입출력 스키마({"files": [...]})를 쓰는 대안 구현체.
"""

import json

from ..llm import call_llm, strip_json
from ..state import PipelineState

# 3000, 8080 같은 흔한 기본 포트는 Windows 환경에서 예약돼 있거나 다른 스택과
# 충돌하는 경우가 많아서 피한 값이다. frontend 생성 노드가 BASE 상수를 맞추는 데도
# 이 값을 쓴다 (backend_registry.BACKEND_PORTS 경유) - 스택마다 포트가 다 달라서
# (8000/8080/5001/5002) 프론트 프롬프트에 숫자를 직접 박으면 스택 바꿀 때마다 어긋난다.
PORT = 5001

_SCHEMA_HINT = (
    "너는 API 명세와 데이터 모델을 보고 실제로 동작하는 Node.js + Express 백엔드를 "
    "작성하는 백엔드 개발자다. 다음 규칙을 반드시 지킨다:\n"
    "- API 명세에 정의된 엔드포인트만 구현한다. 명세에 없는 엔드포인트를 추가하지 않는다.\n"
    "- 각 엔드포인트의 rules에 적힌 업무 규칙을 빠짐없이 구현한다. rules는 필드나 "
    "타입으로 표현되지 않는 제약(거부 조건, 자동 계산·기록되는 값, 상태 전이 제한)이며 "
    "계약의 일부다. 규칙 위반으로 요청을 거부할 때는 400과 함께 어떤 규칙에 걸렸는지 "
    "알 수 있는 메시지를 JSON으로 반환한다. rules가 빈 배열이면 추가 제약이 없다는 뜻이다.\n"
    "- ERD에 정의된 필드만 사용한다.\n"
    "- 데이터는 in-memory 배열로 저장한다 (DB 연동 없음, 범위 밖).\n"
    "- CommonJS(require/module.exports) 방식으로 작성한다. express 패키지를 사용한다.\n"
    f"- 서버는 반드시 포트 {PORT}에서 리스닝한다 (app.listen({PORT}, ...)). 3000, 8080 "
    "같은 흔한 기본 포트는 Windows 환경에서 예약되어 있거나 다른 스택과 충돌하는 "
    "경우가 많으므로 쓰지 않는다.\n"
    "- 존재하지 않는 id로 요청 시 404를 반환한다.\n"
    "- 리소스를 새로 만드는 POST 엔드포인트는 성공 시 기본값인 200이 아니라 "
    "201(Created)로 응답해야 한다 (res.status(201).json(...)).\n"
    "- 처리되지 않은 예외가 500으로 그대로 클라이언트에 노출되지 않게 한다. "
    "각 라우트 핸들러를 try/catch로 감싸거나 Express의 에러 처리 미들웨어를 "
    "등록해서, 예상 못한 타입이 들어와 코드 중간에서 예외가 나도 500이 아니라 "
    '400과 {"message": "..."}로 응답하게 한다.\n'
    "- request body의 유효성을 직접 코드로 검증한다: ERD의 required 필드가 "
    "빠졌거나, typeof로 확인했을 때 타입이 안 맞으면(예: title이 string이 아님, "
    "dueDate가 YYYY-MM-DD 형식의 유효한 날짜가 아님) HTTP 400과 함께 "
    '{"message": "..."} 형태의 에러를 JSON으로 반환하고 그 자리에서 return한다. '
    "라이브러리 없이 순수 JS 조건문으로 검증해도 된다.\n"
    "- required 검증 시 `if (!value)` 같은 falsy 체크를 쓰지 않는다. 이렇게 하면 "
    "빈 문자열(\"\")이나 숫자 0처럼 '존재하지만 falsy인 값'까지 잘못 거부하게 된다. "
    "반드시 `value === undefined || value === null`처럼 존재 여부만 명시적으로 "
    "검사한다. required의 의미는 '필드가 존재해야 한다'는 뜻이지 '비어있으면 "
    "안 된다'는 뜻이 아니다 (예: title이 빈 문자열이어도 유효한 요청이다).\n"
    "- 프론트엔드가 브라우저에서 이 API를 호출한다. CORS를 열지 않으면 브라우저가 "
    "요청을 막아 프론트가 아무 데이터도 못 받는다. cors 패키지를 package.json "
    "의존성에 넣고 app.use(cors())로 개발용 전체 허용을 설정한다.\n"
    "- 코드는 그대로 실행 가능해야 한다 (문법 오류·미완성 코드 금지).\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "files": [\n'
    '    {"path": "상대경로 (예: server.js, package.json)", "content": "파일 전체 내용"}\n'
    "  ]\n"
    "}"
)


def backend_express_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    user = (
        f"[API 명세]\n{api_spec_json}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        "위 API 명세와 데이터 모델로 Node.js + Express 백엔드를 작성해줘. "
        "package.json도 함께 만들어줘 (express 의존성 포함, start 스크립트 포함)."
    )
    raw = call_llm(_SCHEMA_HINT, user, max_tokens=8192)
    try:
        result = strip_json(raw)
    except json.JSONDecodeError:
        result = {"_parse_error": True, "_raw": raw}
    return {"backend_code": result}
