"""
프론트엔드 구현체: React + Vite + TypeScript

frontend_react.py(JSX)와 같은 계약(api_spec)을 소비하는 TypeScript 변형이다.
백엔드가 express(JS)/typescript(TS)로 갈리듯, 프론트도 react(JSX)/react-ts(TSX)로
대칭을 이룬다. FRONTEND_TARGET으로 골라 쓴다 (frontend_registry.py).

react(JSX)와 다른 점: .tsx + tsconfig + 타입 정의가 붙는다. verify_frontend는
이미 .tsx/.ts를 검사 대상(SOURCE_SUFFIXES)에 넣어 두어 그대로 먹는다 - 소스에서
fetch 경로·응답 wrapper key를 뽑아 대조하는 방식은 언어와 무관하다. tsc 빌드까지
파이프라인이 자동으로 돌리진 않는다(react와 같은 이유: 사람이 npm run dev).

출력 형식: {"files": [{"path": "상대경로", "content": "파일 내용"}]}
"""

import json
import os

from ...design_system import design_prompt_block
from ...llm import call_llm, strip_json
from ...state import PipelineState
from ..backend.backend_registry import BACKEND_PORTS

_SCHEMA_HINT = (
    "너는 API 명세와 화면설계서를 보고 동작하는 React + TypeScript 프론트엔드를 "
    "작성하는 개발자다. 다음 규칙을 반드시 지킨다:\n"
    "- Vite + React + TypeScript 최소 구성으로 만든다. 다음 파일들을 전부 포함한다: "
    "package.json, tsconfig.json, tsconfig.node.json, vite.config.ts, index.html, "
    "src/main.tsx, src/App.tsx, src/index.css\n"
    "- 의존성은 react, react-dom(dependencies)과 vite, @vitejs/plugin-react, "
    "typescript, @types/react, @types/react-dom(devDependencies)만 쓴다. UI 라이브러리·"
    "상태관리 라이브러리·라우터·axios를 추가하지 않는다. 데이터 요청은 브라우저 내장 "
    "fetch로 한다.\n"
    "- package.json의 scripts에 dev/build/preview를 넣고(build는 `tsc && vite build`), "
    '"type": "module"을 명시한다. tsconfig.json은 strict: true로 둔다 - 타입을 대충 '
    "any로 두지 말고 실제 타입을 붙인다.\n"
    "- ERD/API 명세의 엔티티(book, member, loan 등)마다 interface를 정의하고, 응답을 "
    "그 타입으로 다룬다. 필드명·타입은 명세에 있는 그대로 쓴다(id·외래키는 number). "
    "명세에 없는 필드를 지어내지 않는다.\n"
    "- 목록 조회 응답은 명세에 정의된 wrapper key로 감싸여 온다(예: {\"books\": Book[]}). "
    "응답 타입도 그 모양으로 정의하고(예: `{ books: Book[] }`), 그 key로 배열을 꺼낸다 - "
    "다른 key로 읽으면 배열을 못 푼다. 계약 검사가 이 wrapper key를 대조한다.\n"
    "- 상태는 useState/useEffect만으로 관리한다. useState에는 제네릭으로 타입을 준다"
    "(예: useState<Book[]>([])).\n"
    "- API 명세에 있는 엔드포인트만 호출한다. 명세에 없는 경로를 부르지 않는다.\n"
    "- 백엔드 주소는 src/App.tsx 맨 위에 상수 하나로 둔다: "
    'const BASE = "http://localhost:포트번호";  '
    "포트번호는 아래 사용자 메시지의 [백엔드 포트]에 적힌 값을 그대로 쓴다 - "
    "스택마다 다르므로(예: fastapi 8000, spring 8080) 절대 다른 값을 지어내지 않는다.\n"
    "URL은 항상 백틱 템플릿 리터럴 `${BASE}/경로` 형태로 쓴다. path parameter가 "
    "있으면 `${BASE}/books/${id}`처럼 쓴다. fetch를 감싸는 헬퍼 함수를 만들어 써도 "
    "되지만, URL만은 이 리터럴 형태를 유지한다 - 계약 검사가 소스에서 이 리터럴을 "
    "찾아 API 명세와 대조하기 때문이다. 경로 조각을 변수로 조립하지 않는다.\n"
    "- 요청 body와 응답 필드는 API 명세에 정의된 필드명을 그대로 쓴다. "
    "명세에 없는 필드를 지어내지 않는다.\n"
    "- 화면설계서는 레이아웃과 사용자 흐름의 근거로만 쓴다. 화면설계서에 언급된 "
    "기능이라도 API 명세에 대응하는 엔드포인트가 없으면 구현하지 않는다.\n"
    "- 모든 fetch 응답의 status를 확인한다. 실패(400/404/500) 시 응답 body의 "
    "메시지를 화면에 사람이 읽을 수 있게 표시한다. 조용히 무시하지 않는다.\n"
    "- 백엔드가 안 떠 있어서 fetch 자체가 실패하는 경우(네트워크 에러)도 잡아서 "
    "'백엔드에 연결할 수 없습니다' 같은 안내를 화면에 띄운다. 콘솔에만 찍고 끝내지 않는다.\n"
    "- 목록 조회는 첫 렌더 시 useEffect로 한 번 호출하고, 생성/수정/삭제 후에도 "
    "다시 호출해서 화면을 갱신한다.\n"
    "- CSS는 src/index.css 하나에 최소한으로 넣는다. 외부 폰트나 이미지를 "
    "불러오지 않는다.\n"
    "- 코드는 그대로 tsc 빌드·실행 가능해야 한다 (타입 오류·문법 오류·미완성 코드 금지).\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "files": [\n'
    '    {"path": "상대경로 (예: src/App.tsx)", "content": "파일 전체 내용"}\n'
    "  ]\n"
    "}"
)


def frontend_react_ts_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    backend_target = os.getenv("BACKEND_TARGET", "fastapi").lower()
    backend_port = BACKEND_PORTS.get(backend_target, 8000)
    user = (
        f"[API 명세 - 이게 계약이다]\n{api_spec_json}\n\n"
        f"[화면설계서 - 레이아웃 참고용]\n{state.get('screen_design', '(없음)')}\n\n"
        f"[백엔드 포트]\n{backend_port}\n\n"
        f"{design_prompt_block()}"
        "위 API 명세를 호출하는 React + Vite + TypeScript 프론트엔드를 작성해줘."
    )

    # 재시도 루프: 이전 시도가 계약 검사(verify_frontend)에 걸렸다면 그 로그를 실어
    # 같은 실수를 반복하지 않게 한다 (backend 루프와 같은 방식).
    prev = state.get("frontend_report")
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
    return {"frontend_code": result}
