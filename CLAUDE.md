# CLAUDE.md

문서 기반 개발 파이프라인. 사람이 쓴 기획문서(.md)를 입력으로,
개발 문서를 생성하고 그에 맞춰 코드까지 생성·검증하는 멀티에이전트 파이프라인.

## 전체 흐름 (목표)

```
[사람] 기획문서.md (ground truth)
        │
   문서화 (요구사항 → {화면설계, ERD} → API 명세)
        │  ← API 명세 = 백엔드/프론트가 공유하는 계약(JSON)
   [검토 게이트: 사람 승인 / HITL]
        │
   백엔드 에이전트 ∥ 프론트엔드 에이전트  (같은 API 명세 소비)
        │
   통합·검증 (계약 일치 → 빌드 → 테스트 생성·실행)
        │  ← 실패 시 원인 분류해서 해당 노드로 조건부 루프백
   완료
```

## 현재 상태 (v13)

**목표 흐름이 한 바퀴 다 돈다** (2026-07-22 실측): 기획문서 → 문서 4종 → 사람 승인
→ 백엔드(sqlite) ∥ 프론트(react + 디자인 토큰) → 검증 3종(실행·계약·토큰) 전부 통과.
브라우저에서 CRUD와 디자인 적용까지 눈으로 확인했다.

**DB 축을 sqlite에서 Postgres로도 확장 완료 (2026-07-24). 4스택 전부 postgres에서 실검증.**
`schema_ddl`에 `DB_TARGET` 방언 분기를 넣어(PK만 `AUTOINCREMENT`↔`SERIAL`, 타입맵 공유)
같은 스키마를 두 방언으로 뽑고, 각 `backend_*.py`도 `_dialect()`+`_build_hint(dialect)`로
영속성 블록만 통짜 교체하는 패턴으로 통일했다. 드라이버: fastapi=psycopg[binary],
express·typescript=pg(node-postgres), spring=org.postgresql. 넷 다 단일 postgres DB(`doc`,
`docker-compose.yml`의 postgres:16, 호스트 포트 55432 — 5432·5433은 WinNAT 예약범위라 bind
막힘)를 공유하고, 한 DB에 4스택이 book/member/loan을 누적하며 서로 읽는 크로스스택 검증까지
했다(schema_ddl 단일 스키마를 진짜 공유함을 실증). 네 스택 모두 프롬프트 수정 0회로 첫 실행
통과 — sqlite에서 익힌 규칙(FK number, boolean 0/1, DDL 소비)이 이미 반영돼 있었고, 각 방언
함정만 미리 못박았다(psycopg3 다중문장 불가→`;` split·`%s`·`RETURNING`, pg 비동기·rows any[],
spring GeneratedKeyHolder는 `prepareStatement(sql, new String[]{"id"})`로 id컬럼 명시).
`verify_backend`(파이프라인 내장 자동검증기; 이 세션의 검사 보강 A로 4스택 전부 대상이 됐다,
아래 참고)도 postgres 대응 — 더미 거부 시 `.db` 파일
부재를 "메모리 구현"으로 오판하던 폴백을 postgres에선 생략하고 note로만 남긴다. **도커는
파이프라인이 자동 기동하지 않는다** — 사람이 `cd db && docker compose up -d`(compose는 `db/`
폴더, `db/README.md` 참고), 백엔드는 `DATABASE_URL`로
붙기만 한다(schemathesis·프론트 npm과 같은 판단). Postgres 전환은 국소 변경이 됐다:
schema_ddl 방언 분기 + 각 스택 커넥션 블록만.

이하 v12 (2026-07-23, sqlite 4스택 통일) 기록:

**DB 영속성 축을 4스택에 통일하기 시작했다 (2026-07-23). express 완료, typescript·spring
남음.** 목표: fastapi만 sqlite고 나머지 3스택은 in-memory라 재기동하면 데이터가 날아가던
걸, 스택 무관하게 파일 DB로 맞춘다. 지금까지:
- **`schema_ddl` 노드 신설** (`src/nodes/schema_ddl.py`): ERD(data_model dict)를 sqlite
  `CREATE TABLE` 문으로 **결정적 변환**한다 (LLM 미사용, `openapi_spec`과 같은 성격).
  스택마다 백엔드 LLM이 컬럼·타입을 제각각 해석하던 걸 막고 4스택이 같은 스키마를
  공유하게 하는 게 목적. 타입 매핑은 sqlite 어피니티 기준(string/date→TEXT,
  boolean/number→INTEGER — INTEGER 어피니티는 실수를 강제 변환하지 않아 가격 같은
  값도 손실 없음), `id INTEGER PRIMARY KEY AUTOINCREMENT` 자동 추가, required→NOT NULL.
  `write_backend`가 `generated/backend/schema.sql`로 저장하고, 백엔드가 앱 시작 시 그
  DDL을 실행한다. 관계(외래키)는 data_model에 정보가 없어 컬럼(INTEGER)으로만 만들고
  FK 제약은 안 건다 — 관계 규칙은 이미 api_spec의 `rules`로 앱 레벨에서 강제됨.
- **express를 in-memory → `node:sqlite`(Node 내장) 파일 DB로 전환** (`backend_express.py`).
  영속성 검증 통과(도서6/회원2/대출5 → 강제종료 → 재기동 → 전부 유지, `library.db` 생성).
  함정을 프롬프트에 못박음(fastapi sqlite 교훈의 node 번역): 동기 API라 async 금지, id는
  `lastInsertRowid`로(JS 카운터 금지), boolean은 0/1 저장이라 응답 시 `Boolean()` 변환 +
  바인딩은 1/0, 직접 CREATE TABLE 짓지 말고 주어진 schema.sql 실행.
  - **처음엔 better-sqlite3로 갔다가 Windows 네이티브 빌드(VS Build Tools 없음, node-gyp
    실패)로 막혀 `node:sqlite`로 갈아탔다.** prebuilt 의존은 Node 버전 바뀌면 또 깨지지만
    Node 내장은 그 리스크가 없다 — fastapi가 stdlib sqlite3만 쓰는 것과 대칭(npm 의존성 0,
    네이티브 빌드 0). 대가는 실험적 모듈이라 start 스크립트에 `--experimental-sqlite`
    플래그가 필요하고 stderr에 경고가 뜨는 것(동작엔 지장 없음).
  - **버그 1건을 프롬프트 규칙으로 승격:** LLM이 `lastInsertRowid`가 BigInt일까 봐 id·외래키를
    `String()`으로 감싸 응답이 문자열로 나갔다(명세는 number). 실측상 기본값은 이미 JS
    number라 불필요한 변환. "id·외래키는 String으로 감싸지 말고 number 그대로" 규칙 추가.
- **typescript도 `node:sqlite`로 전환** (`backend_express_ts.py`). 영속성·업무규칙 3개·
  `tsc` strict 0에러 전부 통과. express에서 배운 규칙을 미리 넣어 첫 실행에 대부분 맞췄고,
  두 버그만 프롬프트 규칙으로 승격:
  - **외래키 number 규칙이 조건부라 무력화됐다(중요).** 기존 규칙은 "명세에 number로
    정의된 필드"만 number로 내보내라고 했는데, ERD·api_spec 생성 단계가 memberId/bookId
    같은 식별자 필드를 전부 `"string"`으로 뭉뚱그려 적어서 조건이 항상 거짓 → FK가
    문자열로 나갔다. "이름이 엔티티명+Id 형태면 **명세 표기와 무관하게** 항상 number"로
    무조건 규칙으로 바꿨다. **같은 조건부 문구가 express에도 있어 함께 무조건 규칙으로
    정합을 맞췄고, express 재검증도 통과**(memberId/bookId가 숫자로 나가는 것 확인).
  - node:sqlite의 `.get()/.all()` 반환 타입(`Record<string, SQLOutputValue>`)이 도메인
    인터페이스와 구조가 안 겹쳐 `as Book[]` 직접 캐스팅이 TS2352로 컴파일 실패 → node
    특유의 `as unknown as Book[]` 이중 캐스팅 규칙 추가.
- **LLM 응답 캐시를 넣었다** (`src/llm.py`). backend 노드 하나만 바꿔 파이프라인을 여러 번
  재실행하는데 매번 문서 단계(requirements~openapi)를 새로 생성하던 게 토큰의 대부분이었다.
  `call_llm`에 `(모델+system+user+max_tokens)` 해시 키로 파일 캐시(`.cache/llm/`)를 달아,
  plan_doc이 같으면 문서 프롬프트가 전부 히트하고 프롬프트를 고친 backend 노드만 미스가 나
  재생성된다. 실측 500배 빠름(3.5s→0.007s), 히트 시 토큰 0. 캐시가 비결정성을 고정해
  디버깅 재현성도 좋아진다. `LLM_CACHE=0`으로 끈다. **주의: 이 캐시는 fastapi 자기수정
  루프와 상성이 나쁠 수 있다** — verify 실패 로그를 프롬프트에 실어 재생성할 때 로그가
  매번 다르면 키가 달라져 정상 미스지만, 로그가 같은데 재생성을 기대하는 경우엔 캐시가
  같은 답을 돌려줄 수 있다(그럴 땐 `LLM_CACHE=0`).
- **spring도 sqlite로 전환** (`backend_spring.py`). in-memory(ArrayList) → org.xerial:sqlite-jdbc
  + JdbcTemplate(JPA 없이). H2 대신 sqlite-jdbc를 고른 결정적 이유: schema_ddl이 뽑는 DDL이
  sqlite 문법(`AUTOINCREMENT`)이라 H2(`IDENTITY`)면 그 산출물이 안 먹는다 — sqlite-jdbc로
  가야 4스택이 진짜 같은 sqlite 파일·같은 DDL을 공유한다. sqlite-jdbc는 JAR에 네이티브가
  번들이라 빌드 문제 없다. DDL은 `src/main/resources/schema.sql`로 저장 →
  `spring.sql.init.mode=always`로 앱 시작 시 자동 실행. id는 GeneratedKeyHolder, date는
  TEXT(LocalDate.parse/toString), boolean은 0/1. 영속성·업무규칙 3개·직렬화 전부 통과.
  - **버그 1건 승격:** `BookService`가 `java.util.Map`을 import하는 대신 같은 이름의 빈
    내부 클래스 `Map`을 선언해 `queryForMap` 반환 타입과 충돌 → 컴파일 실패. "JDK 클래스명과
    겹치는 클래스 선언 금지, 필요하면 import" 규칙 추가.
  - **gradlew 래퍼는 파이프라인이 정적 자산에서 넣어준다** (`assets/gradle-wrapper/` 4파일 →
    `write_backend`가 build.gradle 있는 생성물에 복사, gradlew는 실행권한도 세팅). LLM은
    바이너리 `gradle-wrapper.jar`를 못 만들어 한때 `./gradlew bootRun`이 안 돌았다. 검증된
    wrapper(gradle 8.14, build.gradle의 spring-boot 3.3.4와 호환)를 자산으로 두고 복사하게
    해서 해결 — `gradlew.bat --version`이 Gradle 8.14를 부팅하는 것으로 실동작 확인.
    spring 프롬프트에는 "wrapper 파일은 만들지 마라(파이프라인이 넣는다)"를 명시.
- **DB 영속성 축을 4스택 전부 sqlite로 통일 완료** (fastapi=stdlib sqlite3, express·typescript=
  node:sqlite 내장, spring=sqlite-jdbc). 넷 다 재기동 후 데이터 유지 검증됨. **다음: Postgres+
  도커** → **완료됨 (2026-07-24, 위 v13 참고).** 예측대로 국소 변경이었다: schema_ddl 방언
  분기 + 각 스택 커넥션 블록만. 도커는 파이프라인이 자동 기동하지 말고(schemathesis·프론트
  npm처럼) 사람이 띄우고 검사만 자동화하는 게 이 repo의 반복된 결론 — 그대로 지켰다
  (`docker compose up -d`는 사람이, 백엔드는 `DATABASE_URL`로만).

**스택별 실사용 검증 현황 (2026-07-24 기준, sqlite·postgres 둘 다):**
| 스택 | 방식 | sqlite | postgres |
|---|---|---|---|
| fastapi | 자동 검증(verify_backend: 스모크+영속성) + 브라우저 | ✅ (stdlib sqlite3) | ✅ (psycopg[binary]) |
| spring | `backend-runtime-verifier` 에이전트로 gradle 빌드+기동 + CRUD/업무규칙 + 영속성 | ✅ (sqlite-jdbc) | ✅ (org.postgresql, keyholder id컬럼 함정 못박음) |
| express | `backend-runtime-verifier` 에이전트로 실제 기동 + CRUD/업무규칙 스모크 + 영속성 | ✅ (node:sqlite) | ✅ (pg) |
| typescript | `backend-runtime-verifier` 에이전트로 실제 기동(`tsc` 빌드 + `npm start`) + CRUD/업무규칙 + 영속성 | ✅ (node:sqlite) | ✅ (pg, rows any[]라 이중캐스팅 불필요) |

postgres 4스택은 프롬프트 수정 0회로 첫 실행 통과. gradlew 래퍼는 파이프라인이 자산에서 넣음.
초기 sqlite 시절 버그(spring 4개, express id문자열화 1개, ts FK문자열화·TS2352 2개)는 아래
서술과 프롬프트 규칙에 이미 반영됨.

**4개 스택 전부 실사용 검증 완료.** express·typescript는 `.claude/agents/backend-runtime-verifier.md` +
`.claude/skills/backend-runtime-verification/` 하네스로 자동화해서 spring 때 사람이 손으로 했던
절차(설치→기동→CRUD+업무규칙 스모크→재기동 영속성 확인)를 그대로 반복했다. 둘 다 프롬프트 수정
없이 첫 실행에서 통과 — spring 때와 달리 버그가 없었던 이유는, fastapi/spring에서 나온 교훈
(언어 일관성, `rules` 필드 구현 지시)이 이미 4개 스택 프롬프트에 전부 반영돼 있었기 때문으로
보인다. TS는 `strict: true` 컴파일도 타입 에러 없이 클린 통과했다.

**두 번째 기획문서(도서 대출 관리, 엔티티 3개+관계+업무 규칙)로 돌려서 검증기가
Todo 앱에 종속돼 있던 버그를 걷어냈다** (2026-07-22~23):
- `verify_backend`가 `GET /todos`·`POST /todos`를 하드코딩하고 있었다. api_spec에서
  path parameter 없는 GET을 전부 뽑아 조회를 검사하고, 첫 POST의 request 스키마로
  더미 body를 만들어 생성을 검사하는 방식으로 바꿨다. 더미 데이터가 도메인 규칙
  (enum·자릿수·외래키)에 막혀 4xx가 나면 실패로 안 친다 - 서버가 아니라 값이
  틀린 것이므로. 영속성 검사가 막히면 `.db` 파일 존재로 대체한다.
- `verify_frontend`가 `fetch(` 뒤 문자열만 찾다가, 도메인 3개짜리 앱에서 LLM이
  `safeFetch(url, options)` 래퍼를 쓰자 호출을 0건 잡았는데 **`passed=True`가
  나왔다** (`not unknown`이 위반 0건과 호출 0건을 구분 못 함). `${BASE}`가 들어간
  URL 리터럴을 찾는 방식으로 바꾸고, 호출 0건이면 실패로 친다.
- 그 다음 라운드에서 또 걸렸다: 쿼리스트링을 삼항연산자로 조립하면
  (`` `${BASE}/books${qs ? '?' + qs : ''}` ``) `${...}` 안에 홑따옴표가 들어와서
  따옴표 경계로 자르던 정규식이 반쪽만 잡았다. 백틱만 닫는 구분자로 보는 정규식으로
  바꾸고, `_normalize`에서 "/" 뒤에 오는 `${...}`만 path parameter로 인정하고 나머지는
  거기서부터 잘라내도록(쿼리스트링 조립으로 간주) 순서를 다시 짰다.
- **`api_spec`에 `rules` 필드를 추가했다.** 실제로 도서 대출 3-6 제약(회원당 최대
  5권, 연체 회원 신규대출 차단, 중복대출 금지) 중 2개가 처음엔 구현이 안 됐다 -
  이유는 필드·타입만으로는 이런 업무 규칙을 계약에 담을 수 없었기 때문이다.
  요구사항정의서의 제약을 엔드포인트별 `rules: []`로 옮기게 하고, 백엔드 4종
  프롬프트가 전부 그걸 구현하게 했다. `openapi_spec`도 결정적으로 `description`에
  옮겨 실어서 openapi.json만 보는 도구도 제약을 알 수 있게 했다. 재검증 결과 3개
  제약 전부 통과.


- 구현됨: `requirements` → `{screen_design, data_model}` (fan-out) → `api_spec` (fan-in)
  → `openapi_spec` → `consistency_check` → `review_gate` → (조건부) fan-out:
  - `backend` → `write_backend` → `verify_backend` → (실패 시 루프백) `backend` | END
  - `frontend` → `write_frontend` → `verify_frontend` → END
- **백엔드와 프론트엔드가 나란히(fan-out) 돈다.** 둘은 서로의 산출물을 안 보고
  `api_spec`만 공유한다 - 그래서 순서를 정할 이유가 없고, 한쪽만 재생성해도
  다른 쪽이 안 깨진다. 협상하는 멀티에이전트가 아니라 **계약 공유형**이다.
- 2026-07-22 기준 실측: `fastapi` + `react` 조합으로 전 구간 통과했다 (백엔드
  재시도 0회, 스모크 + 영속성 통과, 프론트 경로 3개 일치, 디자인 토큰 8색 전부 반영,
  `npm run build` 성공, 브라우저에서 CRUD·CORS·한글 입력·디자인 확인 완료).
- **백엔드 포트도 스택별로 흩어져 있던 걸 한 곳으로 모았다** (2026-07-23).
  `fastapi(8000) / spring(8080) / express(5001) / typescript(5002)`처럼 스택마다
  다른데, 프론트 생성 프롬프트에 `8000`이 문자열로 박혀 있었다 - 인텔리제이로
  Spring(8080)을 띄웠더니 프론트가 8000을 불러서 연결이 안 되는 사고로 발견했다.
  각 `backend_*.py`가 자기 `PORT` 상수를 갖고(생성 프롬프트도 그 값으로 서버를
  띄우게 시킴), `backend_registry.py`가 그걸 모아 `BACKEND_PORTS` 딕셔너리로
  재수출한다. `frontend.py`/`frontend_react.py`는 `os.getenv("BACKEND_TARGET")`로
  현재 선택된 스택의 포트를 찾아 프롬프트의 `[백엔드 포트]`에 넣는다. **숫자는
  각 backend_*.py의 PORT 상수가 정본**이고, 다른 곳(RUN_INSTRUCTIONS, 프론트
  프롬프트)은 전부 거기서 읽어만 온다 - 두 곳에 같은 숫자를 따로 적어두면 하나만
  바뀌었을 때 어긋난다.
- **프론트 구현체도 레지스트리로 고른다** (`.env`의 `FRONTEND_TARGET`):
  `vanilla`(빌드 없는 단일 index.html) / `react`(React + Vite). 백엔드와 똑같은
  패턴이라 스택을 추가해도 `graph.py` 배선은 안 바뀐다.
- **어떤 프론트 스택이든 `npm install`/빌드는 파이프라인이 안 돌린다.** 사람이
  `cd generated/frontend && npm install && npm run dev`로 띄운다 - "여러 스택 자동
  기동은 깨지기 쉽다"는 교훈 그대로다. 검사(정적 대조)만 자동화한다.
- **`verify_frontend`는 LLM을 안 쓰는 두 번째 노드다.** 생성된 html/js에서 `fetch()`
  호출 경로를 정규식으로 뽑아 `api_spec`의 경로와 대조한다 (`${BASE}/todos/${id}`와
  `/todos/{id}`를 같은 형태로 정규화해서 비교). 서버를 안 띄우므로 빠르고 결정적이다.
  **지금은 진단만 하고 루프백은 안 붙였다** - "진단과 수정은 분리해서 단계적으로"
  규칙에 따라 리포트가 쓸만한지 먼저 본다. 파일 하단에 `__main__` self-check가 있다.
- **자기 수정 루프가 붙었다.** `backend`(생성) → `write_backend`(디스크 쓰기) →
  `verify_backend`(실제 기동 + CRUD 스모크) 순으로 돌고, 검증 실패면 실패 로그를
  프롬프트에 실어 `backend`로 되돌아가 재생성한다. 상한은 `graph.py`의
  `MAX_BACKEND_RETRIES = 3` (`retry_count`는 루프백 경로에만 있는 `bump_retry`
  노드가 올리므로 첫 생성은 0회).
- 파일 쓰기가 main.py에서 `write_backend` 노드로 옮겨졌다. 재생성마다 디스크에
  다시 써야 `verify_backend`가 최신 코드를 검증하므로 루프 안에 있어야 한다.
  main.py는 이제 결과 출력과 사람 승인만 맡는다.
- **생성되는 백엔드는 sqlite3 파일 DB(`todos.db`)를 쓴다** (fastapi 한정). 표준
  라이브러리라 `requirements.txt`는 여전히 `fastapi`/`uvicorn` 둘뿐이다.
- **자동 실행 검증(`verify_backend.py`)은 이제 4스택 전부 대상이다** (2026-07-24, 검사 보강
  A). 원래 fastapi 전용이었는데, 스모크·영속성 검사 엔진이 이미 스택 무관(순수 HTTP requests)
  이라 스택마다 다른 건 '어떻게 띄우나'뿐임을 확인하고, 그 기동부를 `LaunchSpec` + `_launcher
  (target, db)` 분기로 뺐다(backend_registry와 같은 레지스트리 패턴, graph.py 안 건드림).
  fastapi=uvicorn(전용포트 8010), express=npm install→node(실포트 5001), typescript=npm
  install→tsc→node dist(5002), spring=gradlew bootRun(8080). **여러 언어 자동 기동의 취약점을
  스펙 필드로 흡수했다:** ①포트 하드코딩(express/ts/spring은 코드가 포트를 박아 override 불가
  →실포트 그대로, 검증은 잠깐이라 충돌 위험 낮음) ②npm=.cmd(Windows)→build만 `shell=True`
  ③start는 shell 금지(shell로 띄우면 종료가 안 돼 포트 고아)—단 spring gradlew.bat은 배치라
  `start_shell` 필요, 대신 `stop_by_port`로 taskkill /F /T 트리킬(gradle 데몬·java 자식이
  포트를 쥠) ④DB별 start 분기(node:sqlite는 `--experimental-sqlite` 플래그) ⑤gradle 첫빌드
  느림→`timeout=180`. 스택별로 라이브 확인(전부 postgres, docker up). 미등록 스택이 생기면
  `_launcher`가 None을 줘 통과 처리하고 backend-runtime-verifier 에이전트로 넘긴다.
- **`openapi_spec`은 이 파이프라인에서 처음으로 LLM을 안 쓰는 노드다.** `api_spec`(내부
  단순 포맷)을 정식 OpenAPI 3.0 문서로 규칙 기반 변환한다 (`src/nodes/openapi_spec.py`).
  같은 입력 → 항상 같은 출력이 보장되어야 하므로 결정적으로 짰다.
  `write_backend` 노드가 백엔드 코드와 함께 `generated/backend/openapi.json`으로 저장한다.
- **자동 계약 검사(schemathesis)는 파이프라인 밖에서, 사람이 수동으로 돌린다.**
  4개 스택(Python/Java/Node/TS)을 파이썬으로 자동 기동시키는 건 오늘 겪은 이슈들
  (Gradle 버전, 포트 충돌, 인코딩)로 봤을 때 너무 깨지기 쉬워서, 지금까지처럼
  사람이 서버를 띄운 뒤 별도 명령으로 `schemathesis run openapi.json --url ...`을
  돌리는 방식을 택했다. `schemathesis`는 `requirements.txt`에 필수 의존성이 아니라
  주석으로 안내만 되어 있다 (별도 설치).
- `review_gate`가 조건부 라우팅 지점: `consistency_report.passed == false`면
  `interrupt()`로 멈추고 사람이 y/n으로 승인/거부 (`main.py`가 `Command(resume=...)`로 재개).
- 백엔드 구현체는 여전히 `.env`의 `BACKEND_TARGET`으로 레지스트리에서 선택
  (fastapi/spring/express/typescript, 4개 모두 CRUD 실사용 검증 완료).
- 아직 없음: fastapi 외 스택의 자동 실행 검증, 프론트엔드 노드, 테스트 생성·실행,
  schemathesis 결과를 파이프라인에 자동으로 피드백하는 루프(지금은 순수 진단 도구로만 씀),
  재시도 상한 도달 시 사람 에스컬레이션(지금은 로그 출력 + 수동 확인 안내로 끝)

## 아키텍처 규칙

- 각 노드는 필요한 state만 읽고, **자기 산출물 필드만** dict로 반환한다.
- API 명세는 markdown이 아니라 **dict(JSON)** 으로 뽑는다 → 기계가 검사 가능한 계약.
- 화면설계서는 markdown(사람이 읽는 문서), ERD는 dict(JSON, 기계가 검사)로 성격을 나눈다.
- **결정적으로 할 수 있는 변환(예: 내부 스펙 → 정식 OpenAPI)은 LLM을 쓰지 않는다.**
  순수 코드로 짜서 같은 입력에 항상 같은 출력을 보장한다.
- 코드 생성 노드(backend 등)는 **`{"files": [{"path", "content"}]}`** 형태로 뽑는다
  → 파일 개수·언어가 달라도 스키마가 안 바뀐다.
- **같은 역할(예: backend)에 구현체가 여럿이면 레지스트리 딕셔너리로 묶는다.**
  graph.py에 if/elif를 스택 개수만큼 쌓지 않는다.
- 코드 생성 노드는 **명세(API 명세·ERD)만 근거**로 삼는다. 화면설계서나 기획문서를
  직접 보지 않는다 - 계약을 우회해서 구현하는 걸 막기 위함.
  **예외: `frontend` 노드는 화면설계서도 받는다.** 이 규칙의 취지는 계약(api_spec)을
  우회한 구현을 막는 것인데, 프론트에서 화면설계서는 계약이 아니라 레이아웃 정보다.
  계약 준수는 `verify_frontend`가 결정적으로 검사하므로 우회할 수단이 없다. 안 주면
  UI 구조를 LLM이 지어내게 되고 `screen_design` 산출물이 아무데도 안 쓰이는 죽은
  문서가 된다. 프롬프트에는 "화면설계서에 있어도 대응 엔드포인트가 없으면 구현하지
  않는다"를 명시해서 계약이 상위임을 못박는다.
- **사람 개입이 필요한 지점(HITL)은 `interrupt()` + checkpointer + 조건부 엣지**로
  만든다. 노드 함수 안에서 `input()` 등으로 직접 막지 않는다 - 그래프 상태로
  남아야 재개·재시도·다른 클라이언트(웹 등)에서의 승인이 가능해진다.
- **여러 언어/스택에 걸쳐 서버를 자동 기동시키는 자동화는 신중히 판단한다.** 오늘
  겪은 것처럼 환경별 변수(빌드 도구 버전, 포트 예약, 인코딩)가 많아 깨지기 쉬우면,
  사람이 수동으로 실행하는 단계로 남겨두고 검사만 자동화하는 게 더 견고할 수 있다.
- 테스트는 코드가 아니라 **요구사항·API 명세**에서 생성한다 (코드 버그를 정답으로 박제하지 않기 위해).
- 검증 루프에는 **재시도 상한 + 사람 에스컬레이션**을 반드시 둔다.
- 새 스테이지는 전부 `src/nodes/` 밑에 노드로 추가한다. **단 그래프 조립은
  `src/graph.py` 하나뿐이다** - `src/nodes/graph.py` 같은 자리에 두 번째 배선
  파일이 생기면 import도 안 되고 에러도 안 나서 조용히 무시된다. 실제로 write/
  verify 노드 배선이 `src/nodes/graph.py`에 들어가 있어서 검증이 0회로 돌던 적이
  있다. 노드 추가 후엔 `build_pipeline()`으로 컴파일해 엣지를 찍어보고 확인한다.
- **fan-in 지점 앞의 두 갈래는 진입점으로부터 홉 수(엣지 개수)가 같아야 한다.**
  LangGraph의 암묵적 join(여러 엣지가 한 노드로 모일 때)은 두 갈래가 같은 super-step에
  도착해야 그 노드를 한 번만 실행한다. 홉 수가 어긋나면 늦게 도착하는 갈래 때문에
  fan-in 노드가 **한 실행 안에서 두 번 돈다.** 실제로 `schema_ddl`을 `data_model`과
  `api_spec` 사이에 끼웠더니 data_model 갈래만 2홉(requirements→data_model→schema_ddl),
  screen_design 갈래는 1홉이 되어 `api_spec`(LLM 호출, 비결정적)이 두 번 돌며 서로 다른
  결과를 냈고, 그게 review_gate까지 두 번 이어져 두 번째 승인 직후 `verify_report`
  동시 쓰기 충돌(`InvalidUpdateError`)로 죽었다. 짧은 갈래에 아무 일도 안 하는 통과
  노드(`screen_design_sync`, `lambda state: {}`)를 하나 끼워 홉 수를 맞춰 해결했다.
  결정적 곁가지 노드를 fan-in 앞에 삽입할 땐 반대편 갈래 홉 수부터 확인한다.
- **루프 카운터(retry_count 등)는 루프백 경로 위의 전용 노드가 올린다**
  (`bump_retry`). 조건부 엣지 함수는 state를 읽기만 할 뿐 못 바꾼다. 생성 노드
  안에서 올리면 스택별 구현체마다 같은 코드를 넣어야 해서 하나만 빠뜨려도
  무한 루프가 된다.
- **루프를 한 바퀴 돌 때, 이전 회차의 판정 결과는 다음 판정 전에 지운다.**
  안 지우면 낡은 리포트를 보고 검사를 건너뛰는 침묵 실패가 생긴다
  (`write_backend`가 성공 시 `verify_report`를 None으로 되돌리는 이유).
- 진단(체크)과 수정(루프백)은 분리해서 단계적으로 붙인다 - 한 번에 합치면 디버깅이 어려워진다.
- 반복적으로 나타나는 일관성 이슈(예: path parameter 중복, Gradle 버전, Jackson 직렬화,
  필드 캡슐화)는 해당 생성 노드의 프롬프트 규칙으로 승격시켜 재발을 막는다.
- **계약(api_spec)에 안 적히지만 없으면 연동이 안 되는 것들은 프롬프트 규칙으로
  못박는다.** 대표가 CORS다 - 프론트가 브라우저에서 부르는 이상 백엔드가 CORS를
  안 열면 경로가 아무리 맞아도 데이터가 안 온다. 백엔드 4종 프롬프트에 전부
  넣었다. `verify_frontend`는 경로만 보므로 이런 건 잡아주지 못한다.
- LLM 기반 검토(consistency_check)는 매번 같은 기준으로 걸러내지 못할 수 있다 - 최종
  신뢰는 schemathesis 같은 결정적 도구가 맡는다. 실제로 스택별 DELETE 응답 형태가
  제각각(success/id/result)이었는데 리포트가 못 잡은 전례가 있다.
- **결과 출력에 이모지를 쓰려면 stdout을 utf-8로 고정한다** (`main.py` 상단의
  `sys.stdout.reconfigure`). 윈도우 콘솔 기본 인코딩은 cp949라 `✅` 하나에
  `UnicodeEncodeError`가 나고, 그래프가 다 돌고 난 뒤 출력 단계에서 죽어서
  원인을 찾기 어렵다. 파이프(`python main.py | tail`)로 연결해도 같은 문제가 난다.
- 백엔드 코드 생성 후 디스크에 쓰기 전, 이전 실행의 잔여 파일(특히 스택을 바꿔가며
  재실행할 때)이 안 섞이도록 출력 폴더를 비운다. 파일이 다른 프로세스(실행 중인 서버
  등)에 잠겨 삭제가 실패해도 파이프라인이 죽지 않고 경고 후 계속 진행한다.

## 다음에 할 것 (2026-07-22 확정 순서)

**원칙: 아직 안 일어난 문제는 안 고친다.** 2026-07-21 실행에서 백엔드 재시도 0회,
프론트 계약 위반 0건이었다 - 루프백·에이전트 승격은 필요성이 데이터로 아직 없다.
문제가 실제로 나면 그때 붙인다.

1. ~~브라우저에서 실제 연동 확인~~ **완료 (2026-07-22).** 백엔드 8000 + 프론트 5173을
   띄워 목록/추가/완료/삭제 전부 통과, 한글 제목도 정상, 콘솔에 CORS 에러 없음.
   프리플라이트(OPTIONS)와 `access-control-allow-origin`도 확인했다.
   - 이번에 우연히 맞았지만 위험한 축이 하나 드러났다: 백엔드가 `{"todos":[...]}`
     래퍼로 주고 프론트가 `data.todos`로 읽어서 맞았는데, **경로는 같고 응답 모양만
     다른 불일치는 `verify_frontend`가 못 잡는다.** 계약 검사의 다음 확장 지점.
2. ~~DB 연결 (`sqlite3`)~~ **완료 (2026-07-22).** `backend.py` 프롬프트에 sqlite3 규칙을
   넣고, `verify_backend`에 영속성 검사를 붙였다. 첫 생성에 바로 통과 (재시도 0회).
   - 생성물: `todos.db`, `INTEGER PRIMARY KEY AUTOINCREMENT`, `requirements.txt`는
     여전히 `fastapi`/`uvicorn` 둘뿐 (ORM·외부 DB 안 끌어옴).
   - **영속성 검사가 in-memory와 DB를 가르는 유일한 검사다.** 스모크 테스트는 서버가
     떠 있는 동안만 보므로 메모리에만 담아둬도 전부 통과한다. 그래서 POST → 서버
     종료 → 재기동 → 그 항목이 남아있나 순으로 실제로 껐다 켠다.
   - 검사 전에 이전 실행의 `todos.db`를 지운다. 안 지우면 "재기동 후에도 항목이 있다"가
     이번 코드의 성과인지 지난번 잔여물인지 구분이 안 된다.
   - 프롬프트에 못박은 sqlite 함정 4개: 요청마다 커넥션(스레드 오류), id는 DB가 매김
     (파이썬 카운터는 재기동 시 초기화되어 겹침), boolean은 0/1로 저장되니 `bool()`로
     변환해 내보내기, ORM 금지.
   - **fastapi에만 넣었다.** 다른 3개 스택은 DB 접근 방식이 제각각이라 그 스택을 실제로
     쓸 때 같이 붙인다.
3. **에이전트 승격 판단** (아래 "에이전트 승격" 절). 2번을 돌려보고 결정하기로 했는데,
   **재시도가 0회였다** - 프롬프트에 함정을 미리 못박으니 sqlite 전환을 한 번에
   맞췄다. 승격의 근거로 삼을 실패 로그가 아직 없다는 뜻이고, 이건 "좋은 프롬프트를
   가진 워크플로우가 자율성보다 낫다"는 쪽 증거다. 재시도가 실제로 쌓이기 시작할 때
   다시 본다.
4. ~~디자인 축~~ **완료 (2026-07-22, 아래 "디자인 시스템 연결" 절).** 토큰 8색 전부
   생성물에 반영됐고 `verify_frontend`가 그걸 결정적으로 확인한다. 폰트·최대 너비·
   모서리 반경·버튼 높이까지 토큰대로 나왔다.

대기 (필요가 증명되면 착수):
- 프론트 계약 위반 시 `frontend` 노드로 루프백 (진단은 붙었고 3/3 통과 중)
- 자동 실행 검증을 fastapi 외 스택으로 확장 (기동 명령·타임아웃을 레지스트리에
  같이 넣는 방식이면 스택마다 if/elif를 안 쌓아도 된다)
- schemathesis 실패 리포트를 파싱해 backend로 자동 루프백 (지금은 진단 도구로만 사용)
- 재시도 상한 도달 시 사람 에스컬레이션 (상한은 붙었고, 지금은 로그 출력 후 종료)
- (선택) Spring 쪽에 MyBatis/JPA 연동 노드 - 인턴 업무 스택과 맞추고 싶을 때
- (선택) review_gate의 checkpointer를 MemorySaver 대신 영속 저장소(SQLite 등)로
  바꿔서, 프로세스 재시작 후에도 승인 대기 상태를 유지

## 에이전트 승격 (검토 결론, 2026-07-21)

"이걸 멀티에이전트라 부를 수 있나"를 따져본 결과: **"멀티"는 맞고 "에이전트"가 약하다.**
역할 6개가 분담되어 계약(api_spec)을 공유하며 병렬로 도는 건 멀티에이전트가 맞지만,
각 노드는 프롬프트 1회 던지고 JSON 받는 게 전부다 - 도구도 없고, 다음에 뭘 할지도
`graph.py`의 엣지와 라우터 함수가 정한다. 자율성이 없다.

**승격 대상은 `backend`와 `frontend` 둘뿐이다.** 이 둘만 성공/실패 신호가 즉시
있기 때문이다 (서버가 뜨나? CRUD가 도나?). 신호 없는 노드에 자율 루프를 주면
비용과 불확실성만 는다. `requirements`/`screen_design`/`data_model`/`api_spec`/
`openapi_spec`은 순서가 정해진 변환이라 워크플로우가 정답이고, 그대로 둔다.

승격의 실질적 이득: 지금은 검증 실패 시 **전체 재생성**이라 이미 고쳐진 부분까지
날아간다. 에이전트가 되면 스스로 파일을 쓰고 돌려보고 traceback을 읽어 **틀린
부분만** 고친다.

```
지금:  graph → backend(생성만) → write_backend → verify_backend → 라우터 판단 → 루프백
승격:  graph → backend_agent(도구: write_file, run_cmd, read_log)
                 자기 안에서: 쓴다 → 돌린다 → 에러 읽는다 → 그 줄 고친다 → 반복
                 "됐다" 판단도 자기가. 그래프는 호출과 상한만 담당.
```

주의: 승격해도 재시도 상한과 사람 에스컬레이션은 그래프 쪽에 남긴다 - 에이전트가
자기 루프를 무한히 돌지 않게 하는 건 바깥에서 걸어야 한다.

## 디자인 시스템 연결 (2026-07-22 구현)

지금 파이프라인에는 **외형의 근거가 되는 축이 없다**:

```
기획문서.md      → 뭘 하는지 (동작)
api_spec         → 뭘 부르는지 (계약)
디자인 시스템     → 어떻게 생겼는지 (외형)   ← 없음
```

그래서 `screen_design`이 LLM이 지어낸 markdown이고, 색·간격·컴포넌트 생김새가
실행할 때마다 달라진다.

**제약: `DesignSync`는 Claude Code 안에서 도는 도구라 `python main.py`가 못 부른다.**
사람의 claude.ai 로그인으로 claude.ai/design 프로젝트를 읽고 쓴다. 그래서 노드로는
못 붙이고, **파일 경유**로 연결한다 - schemathesis를 파이프라인 밖에 둔 것과 같은
판단이다. 파이프라인은 로컬 파일만 보므로 자기 완결적이고, 동기화는 사람이 가끔 돈다.

```
design/
├── design_system.md    토큰만 (색·타이포·간격·라운드 등). 이것만 프롬프트에 실린다
└── reference/          Claude Design에서 내려받은 원본. 사람이 볼 용도, 프롬프트엔 안 실림
```

**토큰만 싣고 원본은 안 싣는 이유:** 완성된 HTML/CSS를 주고 "참고만 해라"고 하면
LLM이 그 레이아웃을 거의 확실히 베낀다. 기획문서를 쇼핑몰로 바꿔도 Todo 앱 레이아웃이
나온다. 토큰만 주면 레이아웃은 화면설계서를 보고 매번 새로 짜면서 톤앤매너만 고정된다.
원본을 폴더에 남기는 건 출처 추적과 토큰 재추출의 근거로 쓰기 위함이다.

**로더는 `frontend.py`(vanilla)와 `frontend_react.py`(react)가 공유한다.** 한쪽만
읽게 하면 `FRONTEND_TARGET`을 바꿀 때마다 디자인이 달라진다.

**Claude Design 프로젝트를 기다리지 않았다.** `list_projects`가 빈 배열이었고
(쓰기 가능한 디자인 시스템 프로젝트 0개), 그때 분명해진 것: **파이프라인이 필요한
건 `design/design_system.md` 한 장이고 Claude Design은 그 파일을 채우는 여러 방법 중
하나일 뿐이다.** 그래서 토큰을 직접 써서 축을 먼저 세웠다. 나중에 디자인 시스템이
생기면 이 파일만 갱신하면 되고 파이프라인 코드는 안 바뀐다.

구현:
- `src/design_system.py` - 노드가 아니라 헬퍼다. 그래프의 단계가 아니라 프론트 생성
  노드들이 공유하는 입력이기 때문. `load_design_system()`은 파일이 없으면 빈 문자열을
  주고, 그러면 디자인 축 없이 예전처럼 돈다.
- `frontend.py`와 `frontend_react.py`가 같은 `design_prompt_block()`을 쓴다.
- `verify_frontend`가 토큰의 색 hex가 생성물에 실제로 등장하는지 검사한다.
  **`passed`에는 반영하지 않는다** - 디자인은 계약이 아니고, 안 쓰인 색이 항상
  틀린 것도 아니다 (danger 색은 삭제 버튼 없는 화면엔 안 나온다). 색을 검사 대상으로
  고른 이유는 코드에 문자열 그대로 박히는 값이라 신호가 확실해서다. 간격(12px) 같은
  값은 우연히도 등장해서 신호가 약하다. `.css`를 검사 대상 확장자에 넣은 것도 이 때문
  (react는 색이 `src/index.css`에 있다).

## 하네스: 백엔드 실사용 검증

**목표:** fastapi 외 스택(spring/express/typescript)은 자동 검증(`verify_backend.py`)
대상이 아니라서 "파일이 파싱된다"만 확인하고 통과 처리된다. 이 하네스는 spring 때
사람이 손으로 했던 "진짜 띄워서 CRUD 확인" 과정을 express·typescript에 대해
`backend-runtime-verifier` 에이전트로 대신한다.

**트리거:** "express/typescript 백엔드 검증", "백엔드 실사용 검증", "npm start로
기동 검증" 같은 요청 시 `backend-runtime-verification` 스킬을 사용하라. 단순 질문은
직접 응답 가능.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-07-23 | 초기 구성 | `.claude/agents/backend-runtime-verifier.md`, `.claude/skills/backend-runtime-verification/` | fastapi 외 스택 실사용 검증이 전부 수동이라, spring에서 했던 절차(설치→기동→CRUD 스모크→버그를 프롬프트 규칙으로 승격)를 express·typescript에도 반복 가능하게 자동화 |
