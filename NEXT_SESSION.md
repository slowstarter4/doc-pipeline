# 다음 세션 이어가기 (핸드오프)

마지막 업데이트: 2026-07-24. 상세는 CLAUDE.md(설계 정본)와 git log 참고. 이 파일은
"지금 어디까지 왔고 다음에 뭘 할지"의 빠른 요약이다.

## 지금 상태 — 원래 기획 흐름 완주 + 디자인 축

```
기획문서 → 문서화(요구사항→{화면,ERD}→api_spec→openapi→schema_ddl)
        → 일관성체크 → 검토게이트(HITL interrupt)
        → [backend ∥ frontend ∥ test_gen]  (fan-out, 셋 다 api_spec만 소비)
             backend  → write → verify(4스택 자동) → 실패시 backend 루프백
             frontend → write → verify(경로+응답shape+토큰) → 실패시 frontend 루프백
             test_gen → write_tests → END (명세→pytest, 실행은 사람)
```

- **백엔드 4스택**: fastapi/spring/express/typescript. **DB**: sqlite 또는 postgres(`DB_TARGET`).
  postgres는 `cd db && docker compose up -d`(호스트 55432) 먼저, 백엔드는 DATABASE_URL로 붙음.
- **프론트 3스택**: vanilla/react/react-ts(`FRONTEND_TARGET`).
- **자동 검증**: verify_backend가 4스택 전부 실기동(LaunchSpec + `_launcher(target,db)`).
  verify_frontend는 경로+응답 wrapper key+디자인 토큰 색(LLM 미사용).
- **테스트**: test_gen이 api_spec+rules에서 pytest 생성(HTTP라 스택 무관). 실행은 사람.
- **디자인 축**: `design/design_system.md` 하나가 정본(토큰+컴포넌트 레시피). 프론트가 이것만 읽음.
  외부 디자인 수령: `design/sources/claude-design/`(DesignSync pull) + `sources/stitch/`(zip 드롭).
  실증됨: Nocturne(다크·보라, Claude Design) / Librarian's Ledger(크림·그린, Stitch).
  소스만 갈아끼우면 앱 톤 통째 전환, 레이아웃은 화면설계서라 불변.

## 코드 지도
- `src/graph.py` — 배선 정본(여기 하나뿐). `build_pipeline()`.
- `src/nodes/` — docs/ · backend/ · frontend/ 3개 하위 패키지. `__init__.py`가 재수출.
- `src/state.py` — PipelineState. `src/llm.py` — call_llm + 파일 캐시(`.cache/llm/`, `LLM_CACHE=0`으로 끔).
- `src/design_system.py` — 디자인 토큰 로더(노드 아님, 프론트 노드들이 공유).
- 검증 self-check: `python -m src.nodes.backend.schema_ddl` 등(일부는 .env 먼저 로드 필요, 파일 상단 주석).

## 다음 할 일 (우선순위)

### 티어 1 — 진짜 반쪽 (근거 있음)
1. **테스트 자동 실행** — 지금 test_gen은 생성만. verify_backend의 `LaunchSpec`으로 서버 띄우고
   pytest 돌려 pass/fail을 루프에 먹이기. 서버 기동 커플링(docker 등) 주의.
2. **크로스 스테이지 루프백** — 원래 그림 "실패 원인 분류해서 해당 노드로". 지금은 backend
   실패→backend만. 계약이 틀리면 api_spec으로, ERD면 data_model로 되돌리는 라우팅.

### 티어 2 — 견고성
3. **truncation 감지** — 출력 잘리면 루프백 재생성이 무의미(프론트에서 실측). 잘림 감지→
   max_tokens 상향/에스컬레이션. 지금 재시도 낭비.
4. **재시도 소진 시 사람 에스컬레이션**(interrupt) — 상한만 있고 로그로 끝. (상한 친 적 관측 0회)

### 티어 3 — 디자인 심화
5. **디자인 B방식** — 지금 레시피 변환(A). styles.css 그대로 실어 픽셀 충실도(color-mix·페이드 rule).
6. **역방향 동기** — Claude Design 편집→design_system.md(지금 로컬→Design 단방향).
7. **디자인 프리셋 스위처** — Nocturne/Ledger/light를 `.env`로 선택(지금 파일 교체). 스택 레지스트리처럼.

### 티어 4 — 보류 (실패 데이터 없음, "안 일어난 문제는 안 고친다")
- backend 에이전트 승격, schemathesis 자동 루프백, 단건 응답 필드명 불일치 검사.

**추천 시작 순서: 1 → 3 → 7.** (근거 명확·국소적. 2는 설계 커서 그 다음.)

## 주의점 (겪은 함정)
- 코드 생성물이 길면 `max_tokens=8192` truncation → 파싱 실패. spring/test/프론트는 16384.
- Windows: npm은 npm.cmd(build만 shell), gradlew.bat은 start_shell+stop_by_port(taskkill /F /T).
- WinNAT 예약 포트(5346-5445 등)라 5432/5433 bind 막힘 → postgres 호스트 55432.
- 프론트 노드는 화면설계서를 봄(레이아웃), 하지만 계약 준수는 verify_frontend가 결정적으로 검사.
- claude-in-chrome: 브라우저 2개 연결 시 select_browser 필요.
