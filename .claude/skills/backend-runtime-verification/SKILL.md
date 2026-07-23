---
name: backend-runtime-verification
description: doc-pipeline이 생성한 백엔드를 express → typescript 순으로 실제 npm install/npm start까지 기동시켜 CRUD 스모크 테스트로 검증한다. fastapi/spring은 이미 검증 완료 상태이므로 대상 아님. "express 백엔드 검증", "typescript 백엔드 검증", "백엔드 실사용 검증", "npm start로 기동 검증", "express/typescript 실제 기동", "백엔드 검증 다시" 같은 요청에 사용. 파일 파싱만 확인하거나 정적 코드 리뷰만 하는 요청에는 쓰지 않는다 — 이 스킬은 실제로 서버를 띄운다.
orchestrates: [backend-runtime-verifier]
---

## 왜 이 스킬이 있는가

`verify_backend.py`(자동 검증)는 fastapi 전용이다. spring/express/typescript는
파일이 파싱되는 것만 확인하고 통과 처리한다. spring을 실제로 띄워봤을 때 심각한
버그 3개가 나왔다(`CLAUDE.md` 현재 상태 참고) — 안 돌려본 스택엔 뭐가 있을지
모른다는 뜻이다. 이 스킬은 express·typescript에 대해 그 "실제로 띄워보기"를
`backend-runtime-verifier` 에이전트로 자동화한다.

## Phase 0: 컨텍스트 확인 (초기/후속 판별)

1. `generated/backend/`가 이미 존재하고 방금 이 스킬로 검증한 흔적(`_workspace/`
   또는 대화 맥락)이 있으면 → **부분 재실행**: 사용자가 지목한 스택만 다시 돈다.
2. 사용자가 "express만", "typescript만"처럼 스택을 하나만 지목하면 그 스택만 실행.
3. 그 외(처음 실행, 또는 "둘 다"/"express부터")면 → **초기 실행**: express → typescript
   순서로 순차 실행 (CLAUDE.md에 박힌 순서 — express가 먼저인 이유는 명시된 근거는
   없지만 이미 그렇게 정해졌으므로 따른다).

## 실행 모드

**서브 에이전트 패턴** (팀 아님). `backend-runtime-verifier`를 스택당 1회, **순차로**
호출한다 — `generated/backend/`가 스택 공용 출력 폴더라 동시 실행하면 서로 덮어쓴다.
병렬로 돌릴 이유도 없다(사람이 결과를 보고 다음 스택으로 넘어갈지 판단하는 게
더 안전 — 표준 이상 리스크 등급이면 특히).

## 절차

1. `express`에 대해 `Agent` 도구로 `backend-runtime-verifier` 1회 호출(입력: `stack: express`).
2. 반환된 요약을 그대로 사용자에게 보고. `passed: false`거나 미해결 이슈가 있으면
   여기서 멈추고 사용자 판단을 기다린다 — typescript로 자동으로 안 넘어간다
   (한쪽 스택 실패 상태에서 다음 스택까지 밀어붙이는 건 문제를 더 쌓는 것).
3. `passed: true`면 사용자에게 typescript로 넘어갈지 확인 후 진행(또는 사용자가
   먼저 "계속해" 등으로 승인 의사를 표시했으면 바로 진행).
4. `typescript`에 대해 같은 절차 반복(입력: `stack: typescript`).
5. 두 스택 다 끝나면 `CLAUDE.md`의 스택별 실사용 검증 현황 표를 갱신하고,
   발견된 버그가 있었다면 "현재 상태" 절에 spring 때와 같은 형식(무엇을 - 왜 -
   어떻게 고쳤는지)으로 기록한다. 이 스킬 자체의 변경 이력이 아니라 **프로젝트**
   CLAUDE.md 갱신이다 — 결과가 프로젝트 상태 문서에 남아야 다음 세션이 안다.

## 데이터 전달

파일 기반 + 반환값 기반. 에이전트가 프롬프트 파일(`src/nodes/backend_express.py`
등)을 직접 수정하므로 별도 `_workspace/` 중간 산출물은 없다 — 변경 자체가
git diff로 남는 영속 기록이다. 에이전트의 반환 요약만 이 스킬(오케스트레이터)이
받아 사람에게 전달한다.

## 에러 핸들링

- 에이전트가 환경 문제(npm/node 자체 실패)로 중단을 보고하면, 대신 다른 스택으로
  넘기지 않는다 — 환경 문제는 스택을 바꿔도 똑같이 나기 때문에 사람에게 먼저
  보고하고 판단을 구한다.
- 같은 버그가 반복돼 에이전트가 에스컬레이션한 경우, 그 상태를 그대로 사용자에게
  전달한다 — 오케스트레이터가 대신 판정하지 않는다.

## 리스크 등급

경량~표준 사이: 각 스택당 보통 1파일(생성 프롬프트) 수정, 가역적, 이 프로젝트
자체 테스트 스위트는 없음(파이프라인이 테스트 스위트를 아직 안 만듦 — CLAUDE.md
"아직 없음" 목록 참고). **외부 리뷰 게이트는 안 건다** — 이 저장소엔 러너 엔진
제외 외부 리뷰어가 연동되어 있지 않고, 변경 자체가 다음 실행에서 바로 검증되는
성격(프롬프트 고치고 재생성해서 재검증)이라 내부 QA(재검증 통과)로 충분하다.

## 테스트 시나리오

- **정상 흐름**: express 검증 → 버그 없음 → typescript 검증 → 버그 없음 → 완료 보고.
- **에러 흐름**: express 검증 중 CRUD 스모크에서 실패 → 원인이 프롬프트 규칙 누락 →
  `backend_express.py`에 규칙 추가 → 재실행 재검증 통과 → typescript로 진행할지
  사용자에게 확인.
