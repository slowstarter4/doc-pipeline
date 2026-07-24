"""
노드6b: API 명세 + ERD → 백엔드 코드 (Java Spring Boot)

backend.py(FastAPI)와 같은 입력·같은 출력 스키마({"files": [...]})를 쓰는
대안 구현체. .env의 BACKEND_TARGET으로 어느 쪽을 쓸지 고른다 (graph.py 참고).

Spring은 원래 여러 클래스 파일로 나뉘는 구조라, files 리스트 스키마의 진가가
여기서 드러난다 - Controller/Model/Application/build 설정이 각각 파일로 나온다.

범위를 FastAPI 버전과 맞추기 위해 JPA/MyBatis 없이 in-memory(ArrayList) 저장만
쓰게 한다. DB 연동은 별도 단계에서 다룬다.
"""

import json
import os

from ...llm import call_llm, strip_json
from ...state import PipelineState

# DATABASE_URL 규약은 docker-compose.yml과 한 쌍이다 (postgres:16, doc/doc/doc,
# 호스트 포트 55432). spring은 JDBC URL 형태로 쓴다.
_PG_HOST = "localhost:55432"
_PG_DB = "doc"
_PG_USER = "doc"
_PG_PW = "doc"

# Spring Boot 내장 톰캣의 기본 포트와 같은 값이지만, 기본값에 기대지 않고
# application.properties에 명시적으로 적게 한다 (아래 프롬프트 참고). frontend
# 생성 노드가 BASE 상수를 맞추는 데도 이 값을 쓴다 (backend_registry.BACKEND_PORTS
# 경유) - 스택마다 포트가 다 달라서(8000/8080/5001/5002) 프론트 프롬프트에 숫자를
# 직접 박으면 스택 바꿀 때마다 어긋난다.
PORT = 8080

# 인트로~한글필드명 경고까지는 DB와 무관해 공유한다.
_INTRO = (
    "너는 API 명세와 데이터 모델을 보고 실제로 동작하는 Java Spring Boot 백엔드를 "
    "작성하는 백엔드 개발자다. 다음 규칙을 반드시 지킨다:\n"
    "- API 명세에 정의된 엔드포인트만 구현한다. 명세에 없는 엔드포인트를 추가하지 않는다.\n"
    f"- 서버는 반드시 포트 {PORT}에서 리스닝한다. src/main/resources/application.properties에 "
    f"server.port={PORT}를 명시한다 (내장 톰캣의 기본값에 기대지 않는다 - 프론트엔드가 "
    "정확히 이 포트로 호출하도록 만들어졌으므로, 기본값이 바뀌면 연결이 끊긴다).\n"
    "- 각 엔드포인트의 rules에 적힌 업무 규칙을 빠짐없이 구현한다. rules는 필드나 "
    "타입으로 표현되지 않는 제약(거부 조건, 자동 계산·기록되는 값, 상태 전이 제한)이며 "
    "계약의 일부다. 규칙 위반으로 요청을 거부할 때는 400과 함께 어떤 규칙에 걸렸는지 "
    "알 수 있는 메시지를 JSON으로 반환한다. rules가 빈 배열이면 추가 제약이 없다는 뜻이다.\n"
    "- ERD에 정의된 필드만 사용한다.\n"
    "- **DTO/모델의 필드명·getter/setter명은 API 명세에 있는 영문 필드명을 그대로 "
    "쓴다** (예: title, isbn, memberId, loanDate). 요구사항정의서나 화면설계서의 "
    "한글 항목명('제목', '대출일' 등)을 필드명이나 @JsonProperty 값으로 옮기지 "
    "않는다 - 클라이언트는 API 명세의 영문 필드명으로 요청을 보내므로, 한글 필드명을 "
    "쓰면 역직렬화가 그 자리에서 전부 실패해 엔드포인트가 마비된다. 실제로 이 실수로 "
    'DTO 필드를 통째로 한글(예: "private boolean 대출중여부")로 짓거나, 영문 필드에 '
    '엉뚱하게 @JsonProperty("제목") 같은 한글 값을 붙여 API 전체가 깨진 사고가 있었다.\n'
)

# 영속성 슬롯(드라이버 소개 + datasource + id 채번 + gradle 드라이버 의존성)만 DB_TARGET로
# 갈린다. schema.sql 초기화·FK Long·date/boolean·나머지 전부는 방언 무관해 공유한다
# (INTEGER/TEXT 스키마를 두 방언이 공유하므로 date TEXT·boolean 0/1 코드가 그대로다).
_SQLITE_DB = (
    "- 데이터는 sqlite 파일 DB에 저장한다. org.xerial:sqlite-jdbc 드라이버와 Spring의 "
    "JdbcTemplate(spring-boot-starter-jdbc)을 쓴다. JPA·MyBatis·Hibernate는 쓰지 않는다 "
    "(무거운 ORM 대신 얇은 JDBC). sqlite-jdbc는 JAR에 네이티브 라이브러리가 번들되어 별도 "
    "빌드가 필요 없다. 서버를 껐다 켜도 데이터가 남아있어야 한다(메모리 리스트에만 담아두면 "
    "안 된다).\n"
    "- application.properties에 spring.datasource.url=jdbc:sqlite:도메인명.db(도메인에 맞는 "
    "파일명, 확장자 .db)와 spring.datasource.driver-class-name=org.sqlite.JDBC를 둔다.\n"
    "- id는 DDL의 INTEGER PRIMARY KEY AUTOINCREMENT로 DB가 매기게 하고, 삽입 시 "
    "GeneratedKeyHolder로 생성된 id를 받는다. AtomicLong 등 자바 카운터로 채번하지 않는다 "
    "(재기동하면 초기화되어 id가 겹친다).\n"
    "- build.gradle의 dependencies에 반드시 org.springframework.boot:spring-boot-starter-jdbc와 "
    "org.xerial:sqlite-jdbc:3.46.1.3(sqlite JDBC 드라이버)을 추가한다. sqlite-jdbc는 버전을 "
    "명시해야 한다(스타터가 버전을 관리해주지 않는 서드파티라, 버전을 빼면 해석에 실패한다).\n"
)
_POSTGRES_DB = (
    "- 데이터는 Postgres에 저장한다. org.postgresql:postgresql 드라이버와 Spring의 "
    "JdbcTemplate(spring-boot-starter-jdbc)을 쓴다. JPA·MyBatis·Hibernate는 쓰지 않는다 "
    "(무거운 ORM 대신 얇은 JDBC). 서버를 껐다 켜도 데이터가 남아있어야 한다(메모리 리스트에만 "
    "담아두면 안 된다).\n"
    f"- application.properties에 spring.datasource.url=jdbc:postgresql://{_PG_HOST}/{_PG_DB}, "
    f"spring.datasource.username={_PG_USER}, spring.datasource.password={_PG_PW}, "
    "spring.datasource.driver-class-name=org.postgresql.Driver를 둔다(호스트 포트 55432·자격증명은 "
    "로컬 docker-compose와 맞춘 고정값). sqlite와 달리 도메인별 파일 DB가 아니라 단일 postgres DB에 "
    "붙는다.\n"
    "- id는 DDL의 SERIAL PRIMARY KEY로 DB가 매기게 하고, 삽입 시 GeneratedKeyHolder로 생성된 "
    "id를 받는다. **단 postgres에서는 PreparedStatement를 만들 때 생성키 컬럼을 반드시 "
    "명시해야 한다** - `connection.prepareStatement(sql, new String[]{\"id\"})`처럼 id 컬럼명을 "
    "넘긴다. `Statement.RETURN_GENERATED_KEYS`만 쓰면 postgres JDBC 드라이버가 RETURNING *로 "
    "전체 행을 돌려줘 keyHolder.getKey()가 'single value가 아니다'로 예외가 난다(sqlite에선 안 "
    "나던 함정). AtomicLong 등 자바 카운터로 채번하지 않는다.\n"
    "- build.gradle의 dependencies에 반드시 org.springframework.boot:spring-boot-starter-jdbc와 "
    "org.postgresql:postgresql(postgres JDBC 드라이버)을 추가한다. postgresql 드라이버는 Spring "
    "Boot 의존성 관리가 버전을 잡아주므로 버전을 명시하지 않는다(sqlite-jdbc와 반대).\n"
)

# schema.sql 초기화는 두 방언 공통(DDL을 결정적으로 받아 그대로 실행).
_SCHEMA_INIT = (
    "- 아래 [DB 스키마(DDL)]에 주어진 CREATE TABLE 문을 앱 시작 시 그대로 실행해 테이블을 "
    "만든다 - 직접 CREATE TABLE을 새로 짓지 않는다(스택 간 스키마가 갈리는 걸 막으려고 DDL은 "
    "파이프라인이 결정적으로 생성한다). 이 DDL을 src/main/resources/schema.sql로 저장하고, "
    "application.properties에 spring.sql.init.mode=always를 두면 Spring Boot가 시작 시 "
    "자동 실행한다(CREATE TABLE IF NOT EXISTS라 재기동에도 안전).\n"
)

# FK Long·date/boolean은 방언 무관(INTEGER/TEXT 스키마 공유).
_FK_DATE_BOOL = (
    "- id 및 외래키(memberId, bookId 등 이름이 엔티티명+Id 형태)는 Long 타입으로 다루고 "
    "JSON에도 숫자로 내보낸다. **명세/ERD가 이 필드를 \"string\"으로 적어놨어도 예외가 "
    "아니다** - 명세 생성 단계가 식별자 필드를 전부 \"string\"으로 뭉뚱그려 적는 경우가 흔한데, "
    "실제로는 자동증가 정수 PK를 참조하므로 Long(숫자)이 맞다.\n"
    "- date 컬럼은 TEXT라 date 값을 ISO 'YYYY-MM-DD' 문자열로 저장한다. "
    "LocalDate는 저장 시 toString()으로 문자열화하고 읽을 때 LocalDate.parse(...)로 되돌린다. "
    "boolean은 0/1 정수로 저장하고 읽을 때 (getInt(...) != 0)으로 되돌린다(응답 JSON에는 "
    "true/false로 나가야 한다).\n"
)

_COMMON_RULES = (
    "- Spring Boot 3.x + @RestController 기반의 표준 레이어드 구조로 작성한다 "
    "(Controller / Service / Model(DTO+Entity) / Application 진입점을 각각 별도 파일로 분리).\n"
    "- 모델/DTO 클래스의 필드는 반드시 private로 캡슐화하고, public getter/setter를 "
    "제공한다 (또는 Lombok @Getter/@Setter/@Data 사용). 필드를 public으로 노출하지 않는다.\n"
    "- build.gradle의 플러그인 버전은 반드시 다음으로 고정한다 (최신 Gradle과의 "
    "호환성이 검증된 조합): org.springframework.boot version '3.3.4', "
    "io.spring.dependency-management version '1.1.6'. 다른 버전을 임의로 쓰지 않는다.\n"
    "- gradle wrapper 파일(gradlew, gradlew.bat, gradle/wrapper/gradle-wrapper.jar·"
    ".properties)은 만들지 않는다 - 파이프라인이 검증된 wrapper를 넣어준다(특히 "
    "gradle-wrapper.jar는 바이너리라 텍스트로 만들면 깨진다). build.gradle, settings.gradle, "
    "application.properties, schema.sql, 자바 소스만 만든다.\n"
    "- 패키지명은 com.example.todo 로 통일한다.\n"
    "- 존재하지 않는 id로 요청 시 404(ResponseStatusException 등)를 반환한다.\n"
    "- 리소스를 새로 만드는 POST 엔드포인트는 성공 시 기본값인 200이 아니라 "
    "201(Created)로 응답해야 한다. @ResponseStatus(HttpStatus.CREATED) 또는 "
    "ResponseEntity.status(HttpStatus.CREATED)를 사용한다.\n"
    "- 처리되지 않은 예외가 500으로 그대로 클라이언트에 노출되지 않게 한다. "
    "요청 본문에 예상 못한 타입이 들어와도 서버가 죽지 않고 400을 반환하도록, "
    "@ExceptionHandler(Exception.class)를 추가로 등록해서 예기치 못한 예외까지 "
    "400(또는 명백한 서버 버그일 때만 500)으로 변환한다.\n"
    "- request body의 유효성을 검증한다: ERD의 required 필드가 빠졌거나, 타입이 "
    "안 맞으면(예: title에 문자열 대신 숫자, dueDate가 유효한 날짜 형식이 아님) "
    "HTTP 400과 함께 에러 메시지를 JSON으로 반환한다. jakarta.validation 어노테이션"
    "(@NotNull, @NotBlank 등)을 DTO에 붙이고, MethodArgumentNotValidException을 "
    "@ExceptionHandler로 잡아 400 응답으로 변환하는 핸들러를 둔다.\n"
    "- required의 의미는 '필드가 존재해야 한다(누락/null이면 안 됨)'는 뜻이지, "
    "'값이 비어있으면 안 된다'는 뜻이 아니다. 예를 들어 title이 빈 문자열(\"\")로 "
    "와도 필드 자체는 존재하므로 유효한 요청으로 받아들여야 한다. 그래서 문자열 "
    "필드에는 빈 문자열까지 거부하는 @NotBlank가 아니라, 존재 여부만 검사하는 "
    "@NotNull을 사용한다.\n"
    "- boolean 필드는 Jackson이 getter의 'is' 접두사를 자동으로 떼고 직렬화한다 "
    "(예: isCompleted 필드의 getter isCompleted() → JSON에서는 completed로 나감). "
    "ERD/API 명세에 정의된 필드명을 JSON에서 그대로 유지해야 하므로, **is로 시작하는 "
    "boolean 필드에 한해서만** com.fasterxml.jackson.annotation.JsonProperty를 "
    'import해서 필드(또는 getter) 위에 @JsonProperty("isCompleted")처럼 붙인다. '
    "@JsonProperty의 값은 반드시 API 명세에 있는 필드명 그대로 쓴다(예: isCompleted, "
    "isOverdue) - 요구사항정의서의 한글 항목명(예: '완료 여부', '연체 여부')을 절대 "
    "넣지 않는다.\n"
    "- **is로 시작하지 않는 필드(String, Long, LocalDate 등 대부분)에는 "
    "@JsonProperty를 붙이지 않는다.** 필드명을 API 명세와 똑같은 camelCase로 "
    "지으면(title, isbn, memberId 등) Jackson이 자동으로 맞는 JSON 키를 쓰므로 "
    "애초에 애너테이션이 필요 없다. 실제로 이 규칙을 모든 필드에 확대 적용해서 "
    '@JsonProperty("제목")처럼 요구사항정의서의 한글 라벨을 넣는 바람에, 클라이언트가 '
    '보낸 title이 "인식할 수 없는 필드"로 거부되어 API 전체가 마비된 사고가 있었다. '
    "@JsonProperty는 오직 is-접두사 boolean 하나만을 위한 예외적 장치임을 명심한다.\n"
    '- Jackson은 기본적으로 관대해서 boolean 값 false를 문자열 "false"로, 숫자를 '
    "문자열로 타입 강제변환(coercion)해버릴 수 있다. 이렇게 되면 잘못된 타입이 "
    "조용히 통과해버려 검증이 무력화된다. 이를 막기 위해 TodoApplication의 "
    "main 메서드나 별도 @Configuration 클래스에서 ObjectMapper를 커스터마이징해 "
    "스칼라 타입 강제변환을 금지한다: "
    "objectMapper.coercionConfigFor(LogicalType.Boolean)"
    ".setCoercion(CoercionInputShape.String, CoercionAction.Fail) 및 "
    "objectMapper.coercionConfigFor(LogicalType.Textual)"
    ".setCoercion(CoercionInputShape.Boolean, CoercionAction.Fail)처럼 문자열 "
    "필드에 대해서도 Boolean/Integer 입력을 거부하도록 설정한다 (주의: Jackson의 "
    "LogicalType enum에서 문자열 타입을 가리키는 정확한 이름은 String이 아니라 "
    "Textual이다. String이라는 상수는 존재하지 않으므로 컴파일 에러가 난다). "
    "이 설정이 없으면 잘못된 타입도 문자열로 조용히 변환되어 유효성 검증을 "
    "우회하게 된다.\n"
    "- 위 ObjectMapper @Bean을 new ObjectMapper()로 처음부터 새로 만들면 "
    "Spring Boot가 자동 등록해주는 JavaTimeModule(java.time.LocalDate 등을 "
    "다루는 모듈)이 빠지게 되어 dueDate 같은 date 필드 역직렬화 자체가 깨진다 "
    '(정상적인 "2000-01-01" 같은 값도 파싱 실패한다). 이를 막기 위해 반드시 '
    "objectMapper.registerModule(new com.fasterxml.jackson.datatype.jsr310"
    ".JavaTimeModule())을 coercion 설정과 함께 호출해서 LocalDate 처리 능력을 "
    "유지한다. 또한 JavaTimeModule을 등록해도 기본 설정(WRITE_DATES_AS_TIMESTAMPS)이 "
    '켜져 있으면 LocalDate가 "2000-01-01" 문자열이 아니라 [2000,1,1] 같은 배열로 '
    "직렬화되어 API 명세와 어긋난다. 반드시 "
    "objectMapper.disable(com.fasterxml.jackson.databind.SerializationFeature"
    '.WRITE_DATES_AS_TIMESTAMPS)도 함께 호출해서 ISO-8601 문자열("YYYY-MM-DD")로 '
    "직렬화되게 한다.\n"
    "- 프론트엔드가 브라우저에서 이 API를 호출한다. CORS를 열지 않으면 브라우저가 "
    "요청을 막아 프론트가 아무 데이터도 못 받는다. 컨트롤러에 "
    '@CrossOrigin(origins = "*")를 붙여 개발용 전체 허용을 설정한다.\n'
    "- java.util.Map, List, Set 등 JDK 클래스가 필요하면 반드시 import로 가져와 쓴다. "
    "**JDK 클래스와 같은 이름(Map, List 등)의 클래스를 직접 정의하지 않는다** - 같은 "
    "파일 안에 이름이 겹치는 클래스를 새로 선언하면 그 이름을 쓰는 모든 자리가 JDK "
    "클래스 대신 그 선언을 가리키게 되어(shadowing) 타입 불일치로 컴파일이 깨진다. "
    "실제로 존재 여부만 확인하면 되는 상황에서 java.util.Map을 import하는 대신 "
    "`private static class Map<K, V> extends HashMap<K, V> {}`를 자기 파일에 새로 "
    "선언해, 같은 파일의 `Map<String, Object> row = jdbcTemplate.queryForMap(...)`이 "
    "그 커스텀 클래스로 해석되어 컴파일이 실패한 사고가 있었다.\n"
    "- 코드는 그대로 컴파일·실행 가능해야 한다 (문법 오류·미완성 코드 금지).\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "files": [\n'
    '    {"path": "상대경로 (예: build.gradle, '
    'src/main/java/com/example/todo/TodoApplication.java)", "content": "파일 전체 내용"}\n'
    "  ]\n"
    "}"
)


def _dialect() -> str:
    """DB_TARGET env로 DB 방언 선택 (schema_ddl과 같은 축). 기본 sqlite."""
    return os.getenv("DB_TARGET", "sqlite").lower()


def _build_hint(dialect: str) -> str:
    db_block = _POSTGRES_DB if dialect == "postgres" else _SQLITE_DB
    return _INTRO + db_block + _SCHEMA_INIT + _FK_DATE_BOOL + _COMMON_RULES


def backend_spring_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    data_model_json = json.dumps(state["data_model"], ensure_ascii=False, indent=2)
    ddl = state.get("schema_ddl") or ""
    user = (
        f"[API 명세]\n{api_spec_json}\n\n"
        f"[데이터 모델(ERD)]\n{data_model_json}\n\n"
        f"[DB 스키마(DDL) - src/main/resources/schema.sql로 저장하고 앱 시작 시 자동 실행]\n"
        f"{ddl}\n\n"
        "위 API 명세와 데이터 모델로 Spring Boot 백엔드를 작성해줘. "
        "패키지 구조에 맞게 여러 파일로 나눠서 만들어줘."
    )

    # 재시도 루프: 이전 시도 실패 로그를 프롬프트에 실어 같은 실수를 반복하지 않게 한다.
    prev = state.get("verify_report")
    if prev and prev.get("passed") is False:
        user += (
            f"\n\n[이전 시도 실패 로그 - 이 문제를 반드시 고쳐서 다시 작성해줘]\n"
            f"{prev.get('logs', '')}"
        )
    # Spring은 Controller/Service/Model/DTO를 파일별로 분리하는 구조라 다른
    # 스택보다 산출물이 훨씬 길다. 엔티티가 여럿인 기획서(도서 대출 관리 등)에서
    # 8192로는 JSON이 파일을 다 못 쓰고 잘려 파싱 실패가 났다.
    raw = call_llm(_build_hint(_dialect()), user, max_tokens=16384)
    try:
        result = strip_json(raw)
    except json.JSONDecodeError:
        result = {"_parse_error": True, "_raw": raw}
    return {"backend_code": result}
