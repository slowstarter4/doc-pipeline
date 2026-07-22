"""
노드11: 생성된 프론트엔드가 계약(api_spec)대로 호출하는지 검사한다. LLM 미사용.

백엔드 검증(verify_backend)은 서버를 실제로 띄워야 하지만, 프론트는 그럴 필요가
없다. 정적 파일이므로 파일을 읽어서 fetch() 호출 경로를 뽑고 api_spec의 경로와
대조하면 끝난다. 같은 입력에 항상 같은 결과가 나와야 하므로 openapi_spec처럼
규칙 기반 코드로만 짰다.

이 노드는 지금 진단만 한다 (실패해도 루프백하지 않는다). CLAUDE.md의 "진단과
수정은 분리해서 단계적으로 붙인다"에 따라, 리포트가 실제로 쓸만한지 먼저 보고
나서 루프백을 붙인다.

한계: fetch 호출의 첫 인자가 문자열/템플릿 리터럴일 때만 잡는다. URL을 변수에
담아 fetch(url) 하는 식이면 못 잡는다 - 그래서 frontend 노드 프롬프트에서
fetch(`${BASE}/경로`) 형태를 강제한다.
"""

import re
from pathlib import Path

from ..design_system import token_colors
from ..state import PipelineState

FRONTEND_OUT_DIR = Path("generated/frontend")

# vanilla는 index.html 하나지만, react는 src/App.jsx 같은 파일에 호출이 들어있다.
# .css는 fetch 호출이 없지만 디자인 토큰 검사 대상이라 포함한다.
SOURCE_SUFFIXES = {".html", ".js", ".jsx", ".ts", ".tsx", ".css"}

# 사람이 npm install / npm run build를 돌린 뒤라면 그 산출물까지 훑게 되는데,
# 거기엔 라이브러리 코드와 번들된 사본이 섞여 있어 없는 경로가 잔뜩 잡힌다.
IGNORED_DIRS = {"node_modules", "dist", "build", ".vite"}

# fetch(...)의 첫 인자가 문자열/템플릿 리터럴인 경우만 잡는다.
_FETCH_RE = re.compile(r"""fetch\(\s*[`'"]([^`'"]*)[`'"]""")


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def _normalize(path: str) -> str:
    """호출 경로와 명세 경로를 비교 가능한 하나의 형태로 맞춘다.

    `${BASE}/todos/${id}`  ->  /todos/{}
    /todos/{id}            ->  /todos/{}
    http://localhost:8000/todos?x=1 -> /todos
    """
    p = re.sub(r"\$\{[^}]*\}", "{}", path)  # 템플릿 치환자
    p = re.sub(r"^https?://[^/]*", "", p)  # 절대 URL의 호스트 부분
    p = re.split(r"[?#]", p)[0]  # 쿼리스트링/해시
    if p.startswith("{}"):
        p = p[2:]  # 맨 앞 ${BASE} 같은 베이스 URL 치환자
    p = re.sub(r"\{[^}]*\}", "{}", p)  # 명세의 {id} -> {}
    p = "/" + p.strip("/")
    return p


def _extract_calls(text: str) -> set[str]:
    return {_normalize(m) for m in _FETCH_RE.findall(text)}


def _check_design_tokens(sources_text: str) -> list[str]:
    """디자인 토큰의 색이 생성물에 실제로 쓰였는지 본다.

    계약 검사와 달리 이건 실패로 치지 않는다 (진단만). 토큰을 안 쓰는 게 항상 틀린
    건 아니고 - 예를 들어 danger 색은 삭제 버튼이 없는 화면엔 안 나온다 - 색이
    통째로 무시되고 있는지를 사람이 알아보라는 신호다.

    색만 보는 이유: 코드에 문자열 그대로 박히는 값이라 검사가 확실하다. 간격(12px)
    같은 값은 우연히도 등장해서 신호가 약하다.
    """
    colors = token_colors()
    if not colors:
        return []  # 토큰 문서가 없으면 검사할 게 없다

    lowered = sources_text.lower()
    missing = [c for c in colors if c not in lowered]
    used = len(colors) - len(missing)

    if used == 0:
        return [
            f"디자인 토큰의 색 {len(colors)}개가 하나도 안 쓰임 - 토큰을 무시하고 "
            f"색을 지어냈을 가능성이 높다: {', '.join(colors)}"
        ]
    if missing:
        return [
            f"디자인 토큰 색 {used}/{len(colors)}개 사용됨. 안 쓰인 색 (화면에 해당 "
            f"요소가 없어서일 수도 있다): {', '.join(missing)}"
        ]
    return [f"디자인 토큰 색 {len(colors)}개 전부 사용됨."]


def verify_frontend_node(state: PipelineState) -> dict:
    # 파일 쓰기 단계에서 파싱 실패로 리포트가 이미 채워졌으면 그대로 둔다.
    prev = state.get("frontend_report")
    if prev and prev.get("logs", "").startswith("프론트엔드 코드 JSON 파싱"):
        return {}

    sources = [
        p
        for p in FRONTEND_OUT_DIR.glob("**/*")
        if p.suffix in SOURCE_SUFFIXES and not _is_ignored(p)
    ]
    if not sources:
        return {
            "frontend_report": {
                "passed": False,
                "logs": f"{FRONTEND_OUT_DIR}에 html/js 파일이 없음 - 생성이 제대로 안 됐을 수 있음.",
            }
        }

    called = set()
    texts = []
    for src in sources:
        text = src.read_text(encoding="utf-8")
        texts.append(text)
        called |= _extract_calls(text)

    spec_paths = {
        _normalize(ep["path"]) for ep in state["api_spec"].get("endpoints", [])
    }

    unknown = sorted(called - spec_paths)
    unused = sorted(spec_paths - called)

    logs = []
    if unknown:
        logs.append(
            "명세에 없는 경로를 호출함 (계약 위반):\n"
            + "\n".join(f"  - {p}" for p in unknown)
        )
    if unused:
        logs.append(
            "명세에 있지만 화면에서 안 쓰는 경로 (참고):\n"
            + "\n".join(f"  - {p}" for p in unused)
        )
    if not logs:
        logs.append(f"명세의 경로 {len(spec_paths)}개를 모두 정확히 호출함.")

    # 디자인 토큰은 계약이 아니므로 passed에 반영하지 않는다 (진단만).
    logs += _check_design_tokens("\n".join(texts))

    return {
        "frontend_report": {
            "passed": not unknown,  # 안 쓰는 경로는 실패로 치지 않는다
            "logs": "\n".join(logs),
        }
    }


if __name__ == "__main__":
    # 정규화·추출 규칙이 깨지면 바로 드러나게 하는 최소 self-check.
    # src.nodes 패키지 import가 llm.py를 거치므로 .env를 먼저 읽어야 한다:
    #   python -c "from dotenv import load_dotenv; load_dotenv(); import runpy; \
    #              runpy.run_module('src.nodes.verify_frontend', run_name='__main__')"
    assert _normalize("${BASE}/todos/${id}") == "/todos/{}"
    assert _normalize("/todos/{id}") == "/todos/{}"
    assert _normalize("http://localhost:8000/todos?done=1") == "/todos"
    assert _normalize("${BASE}/todos") == "/todos"
    assert _normalize("/todos/{id}/complete") == "/todos/{}/complete"

    html = """
      const BASE = "http://localhost:8000";
      fetch(`${BASE}/todos`);
      fetch(`${BASE}/todos/${id}/complete`, {method: "PUT"});
      fetch('/api/legacy');
    """
    assert _extract_calls(html) == {"/todos", "/todos/{}/complete", "/api/legacy"}

    assert _is_ignored(Path("generated/frontend/node_modules/react/index.js"))
    assert _is_ignored(Path("generated/frontend/dist/assets/index-abc123.js"))
    assert not _is_ignored(Path("generated/frontend/src/App.jsx"))

    # 토큰 검사는 대소문자를 안 가려야 한다 (#2563EB로 써도 통과).
    colors = token_colors()
    if colors:
        assert _check_design_tokens("")[0].startswith("디자인 토큰의 색")
        assert "전부 사용됨" in _check_design_tokens(
            " ".join(c.upper() for c in colors)
        )[0]
    print("verify_frontend self-check 통과")
