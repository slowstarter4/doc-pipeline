"""
노드6c: API 명세 + ERD → 백엔드 코드 (Node.js + Express, JavaScript)

backend.py(FastAPI)와 같은 입출력 스키마({"files": [...]})를 쓰는 대안 구현체.
"""

import json
import os

from ...llm import call_llm, strip_json
from ...state import PipelineState

# DATABASE_URL 규약은 docker-compose.yml과 한 쌍이다 (postgres:16, doc/doc/doc).
_DATABASE_URL = "postgresql://doc:doc@localhost:55432/doc"

# 3000, 8080 같은 흔한 기본 포트는 Windows 환경에서 예약돼 있거나 다른 스택과
# 충돌하는 경우가 많아서 피한 값이다. frontend 생성 노드가 BASE 상수를 맞추는 데도
# 이 값을 쓴다 (backend_registry.BACKEND_PORTS 경유) - 스택마다 포트가 다 달라서
# (8000/8080/5001/5002) 프론트 프롬프트에 숫자를 직접 박으면 스택 바꿀 때마다 어긋난다.
PORT = 5001

# 영속성 블록만 DB_TARGET로 갈린다. 나머지 규칙(엔드포인트·rules·검증·CORS·포트)은
# DB와 무관해 한 벌로 공유한다. sqlite=Node 내장 동기 API, postgres=pg 비동기 Pool로
# API 성격이 반대라 통짜로 교체한다(부분 편집하면 async 규칙이 섞여 깨진다).
_SQLITE_DB = (
    "- 데이터는 Node 내장 모듈 node:sqlite로 파일 DB(.db)에 저장한다. "
    "`const { DatabaseSync } = require('node:sqlite');`로 불러오고 "
    "`const db = new DatabaseSync('도메인명.db');`로 연다. 아래 [DB 스키마(DDL)]에 "
    "주어진 CREATE TABLE 문을 앱 시작 시 `db.exec(ddl)`로 그대로 실행해 테이블을 "
    "만든다 - 직접 CREATE TABLE을 새로 짓지 않는다(스택 간 스키마가 갈리는 걸 막으려고 "
    "DDL은 파이프라인이 결정적으로 생성한다). 외부 DB 서버나 ORM이나 서드파티 sqlite "
    "패키지(better-sqlite3, sqlite3 등)를 쓰지 않는다 - node:sqlite는 Node에 내장이라 "
    "npm 의존성이 필요 없고 네이티브 빌드도 없다(파이썬 fastapi가 stdlib sqlite3만 쓰는 "
    "것과 같은 이유). 서버를 껐다 켜도 데이터가 남아있어야 한다(메모리 배열에만 담아두면 "
    "안 된다).\n"
    "- node:sqlite는 아직 실험적 모듈이라 실행 시 `--experimental-sqlite` 플래그가 "
    "필요하다. package.json의 start 스크립트를 반드시 "
    "`node --experimental-sqlite server.js`로 쓴다(플래그 없이 `node server.js`로 쓰면 "
    "모듈 로드가 실패한다). 실행 시 ExperimentalWarning이 stderr로 뜨지만 정상이다.\n"
    "- node:sqlite의 DatabaseSync는 동기 API다. async/await나 콜백을 쓰지 않고 "
    "db.prepare(sql).run(...)/.get(...)/.all(...)로 직접 호출한다. 커넥션은 모듈 "
    "로드 시 한 번 열어 재사용한다(Node는 단일 스레드라 스레드 충돌이 없다).\n"
    "- id는 DDL의 INTEGER PRIMARY KEY AUTOINCREMENT로 DB가 매기게 하고, 삽입 결과의 "
    "lastInsertRowid로 새 id를 얻는다. JS 카운터 변수로 세지 않는다(재기동하면 "
    "카운터가 초기화되어 id가 겹친다).\n"
    "- boolean 필드는 sqlite에 0/1 정수로 저장된다. 삽입 시 true/false를 1/0으로 "
    "넣고, 응답으로 내보낼 때 Boolean(value)로 변환해 JSON에 true/false로 나가게 "
    "한다(0/1이 그대로 나가면 명세의 boolean 타입과 어긋난다). node:sqlite는 bind "
    "파라미터로 JS boolean을 직접 못 받으므로 반드시 1/0 정수로 바꿔 바인딩한다.\n"
    "- CommonJS(require/module.exports) 방식으로 작성한다. express, cors 패키지를 "
    "사용한다(sqlite는 node:sqlite 내장이라 의존성에 안 넣는다). start 스크립트는 "
    "`node --experimental-sqlite server.js`.\n"
)
_POSTGRES_DB = (
    "- 데이터는 Postgres에 저장한다. npm 패키지 `pg`(node-postgres)를 쓴다. "
    f"`const {{ Pool }} = require('pg');`로 불러오고 `new Pool({{ connectionString: "
    f"process.env.DATABASE_URL || '{_DATABASE_URL}' }})`로 커넥션 풀을 만든다 - "
    "DATABASE_URL이 없으면 이 기본값(로컬 docker-compose의 postgres)으로 붙는다. "
    "아래 [DB 스키마(DDL)]에 주어진 CREATE TABLE 문을 앱 시작 시 `await pool.query(ddl)`로 "
    "그대로 실행한다(DDL 전체 문자열을 한 번에 넘기면 여러 문장이 실행된다). 직접 "
    "CREATE TABLE을 새로 짓지 않는다(스택 간 스키마가 갈리는 걸 막으려고 DDL은 "
    "파이프라인이 결정적으로 생성한다). DDL은 IF NOT EXISTS라 재기동해도 안전하다. "
    "ORM(Sequelize, Prisma 등)을 쓰지 않고 pg로 직접 SQL을 실행한다. 서버를 껐다 켜도 "
    "데이터가 남아있어야 한다.\n"
    "- pg는 **비동기** API다. 모든 라우트 핸들러를 `async`로 만들고 pool.query(...)에 "
    "`await`를 붙인다. 앱 시작(테이블 생성)도 async 함수 안에서 await한 뒤 app.listen을 "
    "호출한다. 플레이스홀더는 `?`가 아니라 `$1, $2, ...`이고, 결과는 `result.rows` "
    "배열이다(단건은 `result.rows[0]`).\n"
    "- id는 DDL의 SERIAL PRIMARY KEY로 DB가 매긴다. INSERT 문 끝에 `RETURNING id`(또는 "
    "`RETURNING *`)를 붙여 새 행의 id를 result.rows[0]에서 얻는다. JS 카운터 변수로 "
    "세지 않는다. pg가 돌려주는 INTEGER/SERIAL 값은 이미 JS number다.\n"
    "- boolean 필드는 DDL상 INTEGER 컬럼이라 0/1 정수로 저장된다(postgres 네이티브 "
    "BOOLEAN이 아니다 - 스택 간 스키마 통일을 위해 INTEGER로 맞췄다). 삽입 시 "
    "true/false를 1/0으로 바인딩하고, 응답으로 내보낼 때 Boolean(value)로 변환해 "
    "true/false로 나가게 한다(0/1이 그대로 나가면 명세의 boolean 타입과 어긋난다).\n"
    "- CommonJS(require/module.exports) 방식으로 작성한다. express, cors, pg 패키지를 "
    "package.json 의존성에 넣는다. start 스크립트는 `node server.js`.\n"
)

_FK_RULE = (
    "- id 및 다른 엔티티의 id를 참조하는 필드(예: memberId, bookId - 이름이 어떤 "
    "엔티티명 + Id 형태면 그 엔티티의 PK를 참조하는 외래키다)는 항상 number로 응답 "
    "JSON에 내보낸다. **명세/ERD가 이 필드를 \"string\" 타입으로 적어놨어도 예외가 "
    "아니다** - 명세 생성 단계가 식별자 필드를 전부 \"string\"으로 뭉뚱그려 적는 경우가 "
    "흔한데, 실제로는 자동증가 정수 PK를 참조하므로 number가 맞다. 요청 body로 받은 "
    "memberId/bookId도 String()으로 저장·조회하지 말고 Number(...)로 변환해 DB 바인딩과 "
    "응답에 number로 일관되게 쓴다. DB가 돌려주는 id는 이미 JS number이므로 BigInt "
    "직렬화를 피하려고 String으로 바꿀 필요가 없다 - 바꾸면 프론트가 숫자 비교·연산을 "
    "할 때 깨진다.\n"
)

_COMMON_RULES = (
    "- API 명세에 정의된 엔드포인트만 구현한다. 명세에 없는 엔드포인트를 추가하지 않는다.\n"
    "- 각 엔드포인트의 rules에 적힌 업무 규칙을 빠짐없이 구현한다. rules는 필드나 "
    "타입으로 표현되지 않는 제약(거부 조건, 자동 계산·기록되는 값, 상태 전이 제한)이며 "
    "계약의 일부다. 규칙 위반으로 요청을 거부할 때는 400과 함께 어떤 규칙에 걸렸는지 "
    "알 수 있는 메시지를 JSON으로 반환한다. rules가 빈 배열이면 추가 제약이 없다는 뜻이다.\n"
    "- ERD에 정의된 필드만 사용한다.\n"
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


def _dialect() -> str:
    """DB_TARGET env로 DB 방언 선택 (schema_ddl과 같은 축). 기본 sqlite."""
    return os.getenv("DB_TARGET", "sqlite").lower()


def _build_hint(dialect: str) -> str:
    db_block = _POSTGRES_DB if dialect == "postgres" else _SQLITE_DB
    return (
        "너는 API 명세와 데이터 모델을 보고 실제로 동작하는 Node.js + Express 백엔드를 "
        "작성하는 백엔드 개발자다. 다음 규칙을 반드시 지킨다:\n"
        + db_block
        + _FK_RULE
        + _COMMON_RULES
    )


def backend_express_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    ddl = state.get("schema_ddl") or ""
    dialect = _dialect()
    if dialect == "postgres":
        pkg_hint = "(express, cors, pg 의존성 포함, start 스크립트는 `node server.js`)"
    else:
        pkg_hint = (
            "(express, cors 의존성 포함, start 스크립트는 "
            "`node --experimental-sqlite server.js`)"
        )
    user = (
        f"[API 명세]\n{api_spec_json}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        f"[DB 스키마(DDL) - 이 CREATE TABLE 문을 앱 시작 시 그대로 실행한다]\n{ddl}\n\n"
        "위 API 명세와 데이터 모델로 Node.js + Express 백엔드를 작성해줘. "
        f"package.json도 함께 만들어줘 {pkg_hint}."
    )

    # 재시도 루프: 이전 시도 실패 로그를 프롬프트에 실어 같은 실수를 반복하지 않게 한다.
    prev = state.get("verify_report")
    if prev and prev.get("passed") is False:
        user += (
            f"\n\n[이전 시도 실패 로그 - 이 문제를 반드시 고쳐서 다시 작성해줘]\n"
            f"{prev.get('logs', '')}"
        )

    raw = call_llm(_build_hint(dialect), user, max_tokens=8192)
    try:
        result = strip_json(raw)
    except json.JSONDecodeError:
        result = {"_parse_error": True, "_raw": raw}
    return {"backend_code": result}
