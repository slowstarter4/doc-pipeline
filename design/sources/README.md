# design/sources — 외부 디자인 수령

사람이 디자인 도구(Claude Design / Google Stitch)에서 **기획 컨셉으로 디자인을 생성**하고,
그 결과물이 여기 착지한다. 파이프라인은 이 폴더를 **직접 읽지 않는다** - 여기 원본을
`design/design_system.md`(파이프라인이 프롬프트에 싣는 정본) 한 장으로 **변환**해서 쓴다.
두 소스 모두 종착지가 design_system.md라 대칭이다.

```
기획 컨셉 → [디자인 도구에서 사람이 생성] → design/sources/… → 변환 → design/design_system.md → 프론트 생성
```

## claude-design/
claude.ai/design 프로젝트를 `DesignSync` 도구(Claude Code)로 **직접 pull**한다. 사람이
웹에서 디자인을 만들면(예: Nocturne), Claude Code 세션에서:
1. `DesignSync list_projects`로 프로젝트 확인
2. `list_files` / `get_file`로 `theme.json`·`styles.css`를 읽어 여기 저장
3. 그 값을 `design/design_system.md`로 옮겨 적는다(변환).

예: `claude-design/nocturne/` (theme.json + styles.css). 다크·보라 Inter 디자인.

## stitch/
Google Stitch는 도구로 연결되지 않는다(DesignSync는 claude.ai/design 전용). 대신 Stitch의
**export/code 기능**으로 사람이 직접 받아 여기 드롭한다:
1. Stitch에서 디자인 생성 → **HTML/CSS 코드로 export**(스크린샷만 있으면 값 추출이 안 되니 코드로)
2. 받은 파일을 `stitch/<이름>/`에 저장
3. Claude Code가 그 파일을 로컬 Read로 읽어 `design/design_system.md`로 변환.

차이는 "가져오는 경로"뿐 — Claude Design은 pull 자동, Stitch는 export 드롭 한 단계 추가.

## 변환이란
소스의 토큰(색·타이포·간격·반경·그림자)과 컴포넌트 스펙을 `design_system.md`의
토큰 표 + 컴포넌트 레시피로 옮긴다. **레이아웃(페이지 배치)은 안 가져온다** - 그건
화면설계서가 정한다(복사 방지). 지금은 사람/Claude Code가 세션에서 변환한다(스키마가
소스마다 달라 고정 스크립트로 만들기 애매 - schemathesis를 밖에 둔 것과 같은 판단).
