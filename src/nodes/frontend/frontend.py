"""
노드9: API 명세 + 화면설계서 → 프론트엔드 코드 (단일 index.html)

백엔드와 같은 api_spec(계약)을 소비하는 반대편 구현체다. 백엔드는 계약을
'구현'하고, 프론트는 같은 계약을 '호출'한다. 둘은 서로를 보지 않는다 -
계약만 공유하므로 병렬(fan-out)로 돌아도 안전하다.

스택을 빌드 도구 없는 단일 HTML 파일로 정한 이유: npm install / 번들러 빌드는
CLAUDE.md에 적힌 "여러 스택 자동 기동은 깨지기 쉽다"는 교훈에 그대로 걸린다.
index.html 하나면 생성 결과를 브라우저로 바로 열 수 있고, 검증도 파일을 읽어
fetch 경로를 뽑는 것으로 끝난다 (verify_frontend, LLM 미사용).

입력에 화면설계서를 포함한 이유: "코드 생성 노드는 명세만 근거로 삼는다"는
규칙의 취지는 계약(api_spec)을 우회한 구현을 막는 것인데, 프론트에서 화면설계서는
계약이 아니라 레이아웃 정보다. 그리고 계약 준수는 verify_frontend가 결정적으로
검사하므로 우회할 수단이 없다. 화면설계서를 안 주면 UI 구조를 LLM이 지어내게
되고 screen_design 노드의 산출물이 아무데도 안 쓰이는 죽은 문서가 된다.

출력 형식: {"files": [{"path": "index.html", "content": "..."}]}
"""

import json
import os

from ...design_system import design_prompt_block
from ...llm import call_llm, strip_json
from ...state import PipelineState
from ..backend.backend_registry import BACKEND_PORTS

_SCHEMA_HINT = (
    "너는 API 명세와 화면설계서를 보고 동작하는 프론트엔드를 작성하는 개발자다. "
    "다음 규칙을 반드시 지킨다:\n"
    "- 빌드 도구를 쓰지 않는다. index.html 파일 하나에 HTML/CSS/JS를 전부 인라인으로 "
    "넣는다. npm, 번들러, 프레임워크(React/Vue 등), CDN 스크립트 모두 금지. "
    "브라우저로 파일을 바로 열면 동작해야 한다.\n"
    "- API 명세에 있는 엔드포인트만 호출한다. 명세에 없는 경로를 부르지 않는다.\n"
    "- 백엔드 주소는 파일 맨 위에 상수 하나로 둔다: "
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
    "- 목록 조회는 페이지 로드 시 자동으로 한 번 호출하고, 생성/수정/삭제 후에도 "
    "다시 호출해서 화면을 갱신한다.\n"
    "- CSS는 인라인 <style>에 최소한으로 넣는다. 외부 폰트나 이미지를 불러오지 않는다.\n"
    "- 코드는 그대로 실행 가능해야 한다 (문법 오류·미완성 코드 금지).\n\n"
    "반드시 아래 JSON 스키마 '그대로', 다른 말/마크다운 없이 JSON만 출력한다.\n"
    "{\n"
    '  "files": [\n'
    '    {"path": "index.html", "content": "파일 전체 내용"}\n'
    "  ]\n"
    "}"
)


def frontend_node(state: PipelineState) -> dict:
    api_spec_json = json.dumps(state["api_spec"], ensure_ascii=False, indent=2)
    backend_target = os.getenv("BACKEND_TARGET", "fastapi").lower()
    backend_port = BACKEND_PORTS.get(backend_target, 8000)
    user = (
        f"[API 명세 - 이게 계약이다]\n{api_spec_json}\n\n"
        f"[화면설계서 - 레이아웃 참고용]\n{state.get('screen_design', '(없음)')}\n\n"
        f"[백엔드 포트]\n{backend_port}\n\n"
        f"{design_prompt_block()}"
        "위 API 명세를 호출하는 프론트엔드를 index.html 하나로 작성해줘."
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
