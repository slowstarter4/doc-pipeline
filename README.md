# doc-pipeline

기획문서(.md) 한 장을 입력으로, 개발 문서를 생성하고 (앞으로) 코드까지
생성·검증하는 멀티에이전트 파이프라인. LangGraph 기반.

현재 v0은 문서화 파이프라인의 최소 조각만 구현되어 있다:
**기획문서 → 요구사항정의서 → API 명세(JSON)**.

## 셋업

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # Windows: copy .env.example .env
# .env 에 ANTHROPIC_API_KEY 채우기
```

## 실행

```bash
python main.py
```

`examples/todo_plan.md`를 읽어서 요구사항정의서와 API 명세를 출력한다.
다른 기획을 넣고 싶으면 그 파일을 바꾸거나 `main.py`에서 경로를 바꾸면 된다.

## 구조

```
main.py            진입점
src/state.py       공유 상태 (노드 사이로 흐르는 문서들)
src/llm.py         LLM 호출 헬퍼 + JSON 파싱
src/graph.py       노드 등록 + 엣지 배선
src/nodes/
  requirements.py  기획 → 요구사항정의서
  api_spec.py      기획+요구사항 → API 명세(JSON)
examples/
  todo_plan.md     샘플 기획문서
```

## 설계 원칙

- 각 노드는 자기 산출물만 state에 되돌려준다 → 노드를 늘려도 안 깨진다.
- API 명세는 JSON(dict)으로 뽑는다 → 백엔드/프론트가 공유하는 "기계가 읽는 계약".
- 최소 조각을 먼저 완주시키고, 그 다음에 붙인다.

## 로드맵

1. ~~화면설계서 + ERD 노드 (fan-out)~~ ✅
2. ~~일관성 체크 노드~~ ✅
3. ~~검토 게이트 (HITL)~~ ✅ - `consistency_report.passed`가 false면 사람이 y/n으로 승인
4. ~~백엔드 노드 + 계약 검사(schemathesis) + 테스트 생성·실행 + 조건부 루프백~~ (백엔드까지 완료,
   schemathesis/루프백은 진행 중)
5. 프론트엔드 노드 + 백엔드/프론트 fan-out

> 참고: LangGraph 버전에 따라 `set_entry_point` 등 일부 API 이름이 다를 수 있다.
> 설치된 버전 문서를 확인할 것.

## HITL 게이트 사용법

`python main.py` 실행 중 일관성 체크에서 issue가 발견되면(`passed: false`), 터미널에
이슈 목록이 뜨고 `y`/`n` 입력을 기다린다. `y`(승인)면 백엔드 코드 생성으로 진행하고,
`n`(거부)이면 그 자리에서 파이프라인이 멈춘다.
