# doc-pipeline

기획문서(.md) 한 장을 입력으로 개발 문서를 만들고, 그 명세에 맞춰 **백엔드와
프론트엔드 코드까지 생성·검증**하는 멀티에이전트 파이프라인. LangGraph 기반.

```
기획문서.md
    │
    ├─ 요구사항정의서 ─┬─ 화면설계서 ─┐
    │                  └─ ERD ────────┴─→ API 명세(JSON) ─→ OpenAPI 3.0
    │                                          │
    │                                     일관성 체크
    │                                          │
    │                                  [검토 게이트: 사람 승인]
    │                                          │
    │                         ┌────────────────┴────────────────┐
    │                    백엔드 생성                        프론트 생성
    │                         │                                 │
    │                    파일 쓰기                          파일 쓰기
    │                         │                                 │
    │                  실행 검증(서버 기동)              계약 검증(호출 경로)
    │                         │                                 │
    └─────────────────  실패 시 재생성 루프                     완료
```

**API 명세가 계약이다.** 백엔드와 프론트엔드는 서로의 코드를 보지 않고 같은 명세만
소비한다. 그래서 나란히 생성해도 안전하고, 한쪽만 다시 만들어도 다른 쪽이 안 깨진다.

## 나오는 것

`python main.py` 한 번에:

- 요구사항정의서, 화면설계서(markdown) / ERD, API 명세(JSON) / OpenAPI 3.0 문서
- `generated/backend/` — 실행 가능한 서버 (FastAPI + sqlite3, 표준 라이브러리만)
- `generated/frontend/` — 실행 가능한 화면 (React + Vite, 또는 빌드 없는 단일 HTML)

## 셋업

```bash
python -m venv .venv
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env           # macOS/Linux: cp .env.example .env
# .env에 OPENROUTER_API_KEY 채우기 (https://openrouter.ai)
```

## 실행

```bash
python main.py                          # examples/todo_plan.md (기본값)
python main.py examples/library_plan.md # 다른 기획문서
```

기획문서 경로를 인자로 받는다. 문서마다 `thread_id`가 갈리므로 승인 대기 상태가
섞이지 않는다.

일관성 체크에서 이슈가 나오면 터미널에 목록이 뜨고 `y`/`n`을 기다린다.
`y`면 코드 생성으로 진행, `n`이면 그 자리에서 멈춘다.

### 생성된 앱 돌려보기

```bash
# 터미널 1
cd generated/backend && pip install -r requirements.txt && uvicorn main:app --reload

# 터미널 2 (FRONTEND_TARGET=react인 경우)
cd generated/frontend && npm install && npm run dev
```

## 검증 3종

생성물을 믿지 않고 매번 확인한다. 셋 중 둘은 LLM을 안 쓴다.

| 검증 | 방법 | LLM |
|---|---|---|
| 실행 | api_spec에서 뽑은 GET/POST 경로를 실제로 호출, **껐다 켜서 데이터가 남는지**까지 확인 | ✗ |
| 계약 | 프론트 소스의 `${BASE}` URL 리터럴을 뽑아 API 명세와 대조 | ✗ |
| 디자인 | 디자인 토큰의 색이 생성물에 실제로 쓰였는지 확인 | ✗ |
| 일관성 | 네 문서를 서로 대조해 모순 찾기 | ✓ |

영속성 검사가 in-memory 구현과 DB 구현을 가르는 유일한 검사다 — 스모크 테스트는
서버가 떠 있는 동안만 보므로 메모리에만 담아둬도 전부 통과한다. 더미로 만든
요청 body가 도메인 규칙(enum·자릿수·외래키)에 막혀 거부되면 실패로 치지 않는다 —
서버가 아니라 검사기가 만든 값이 틀린 것이므로.

## 스택 선택

`.env`에서 고른다. 같은 API 명세를 소비하므로 스택을 바꿔도 계약은 그대로다.

```
BACKEND_TARGET=fastapi     # fastapi | spring | express | typescript
FRONTEND_TARGET=react      # react | vanilla
```

새 스택은 노드 파일 하나 만들고 레지스트리에 한 줄 등록하면 된다
(`backend_registry.py` / `frontend_registry.py`). 그래프 배선은 안 건드린다.

## 디자인 토큰

`design/design_system.md` 한 장이 외형의 근거다. 색·타이포·간격·모서리를 여기서
정하면 프론트 생성이 그걸 따르고, 검증이 실제 반영 여부를 확인한다. primary 색을
바꾸고 다시 돌리면 코드 수정 없이 결과물의 톤이 바뀐다.

레이아웃은 여기서 정하지 않는다. 완성된 HTML/CSS를 넣으면 LLM이 그 레이아웃을
그대로 베껴서, 기획문서를 바꿔도 같은 화면이 나온다.

## 설계 원칙

- 각 노드는 자기 산출물 필드만 되돌려준다 → 노드를 늘려도 안 깨진다.
- **결정적으로 가능한 변환에는 LLM을 안 쓴다.** 내부 명세 → OpenAPI 3.0 변환,
  계약 검사, 토큰 검사가 전부 순수 코드다. 같은 입력에 항상 같은 출력.
- 코드 생성 노드는 명세만 근거로 삼는다. 기획문서를 직접 보지 않는다 —
  계약을 우회한 구현을 막기 위함. 필드·타입으로 안 잡히는 업무 규칙(거부 조건,
  자동 계산·기록되는 값)은 API 명세의 `rules` 필드로 계약에 실어서, 기획문서를
  안 봐도 구현이 규칙을 지키게 한다.
- 사람 개입은 `interrupt()` + checkpointer로 만든다. 노드 안에서 `input()`으로
  막지 않는다 → 재개·재시도·다른 클라이언트에서의 승인이 가능해진다.
- 검증 루프에는 재시도 상한을 둔다.

## 현재 한계

- 두 번째 기획문서(엔티티 3개, 관계, enum, 외래키, 업무 규칙 3종)로 검증했다
  (`examples/library_plan.md`). 아직 못 본 건: 파일 업로드, 여러 화면에 걸친
  다단계 흐름, 인증/권한.
- 자동 실행 검증과 sqlite 규칙은 **FastAPI 전용**이다. 나머지 3개 스택은 생성은
  되지만 검증을 건너뛴다 (수동 확인 필요).
- 계약 검사는 **경로만** 본다. 경로는 같고 응답 모양만 다른 불일치는 못 잡는다.
- 프론트 계약 위반이 잡혀도 자동으로 고치지 않는다 (진단만).
- schemathesis 계약 검사는 파이프라인 밖에서 사람이 수동으로 돌린다.
