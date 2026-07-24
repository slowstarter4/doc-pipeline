"""
노드11: 생성된 프론트엔드가 계약(api_spec)대로 호출하는지 검사한다. LLM 미사용.

백엔드 검증(verify_backend)은 서버를 실제로 띄워야 하지만, 프론트는 그럴 필요가
없다. 정적 파일이므로 파일을 읽어서 fetch() 호출 경로를 뽑고 api_spec의 경로와
대조하면 끝난다. 같은 입력에 항상 같은 결과가 나와야 하므로 openapi_spec처럼
규칙 기반 코드로만 짰다.

검사 3종: ①호출 경로 ↔ api_spec 경로 ②응답 모양(목록 wrapper key를 프론트가 푸는지 -
경로는 맞아도 {"books":[...]}를 data.items로 읽는 불일치를 잡는다) ③디자인 토큰 색.
①②는 계약이라 passed에 반영, ③은 진단만.

이 노드는 지금 진단만 한다 (실패해도 루프백하지 않는다). CLAUDE.md의 "진단과
수정은 분리해서 단계적으로 붙인다"에 따라, 리포트가 실제로 쓸만한지 먼저 보고
나서 루프백을 붙인다.

한계: fetch 호출의 첫 인자가 문자열/템플릿 리터럴일 때만 잡는다. URL을 변수에
담아 fetch(url) 하는 식이면 못 잡는다 - 그래서 frontend 노드 프롬프트에서
fetch(`${BASE}/경로`) 형태를 강제한다.
"""

import re
from pathlib import Path

from ...design_system import token_colors
from ...state import PipelineState

FRONTEND_OUT_DIR = Path("generated/frontend")

# vanilla는 index.html 하나지만, react는 src/App.jsx 같은 파일에 호출이 들어있다.
# .css는 fetch 호출이 없지만 디자인 토큰 검사 대상이라 포함한다.
SOURCE_SUFFIXES = {".html", ".js", ".jsx", ".ts", ".tsx", ".css"}

# 사람이 npm install / npm run build를 돌린 뒤라면 그 산출물까지 훑게 되는데,
# 거기엔 라이브러리 코드와 번들된 사본이 섞여 있어 없는 경로가 잔뜩 잡힌다.
IGNORED_DIRS = {"node_modules", "dist", "build", ".vite"}

# ${BASE}가 들어간 백틱 템플릿 리터럴. 호출을 어떻게 감싸든(래퍼 함수, axios,
# 변수에 담기) URL 자체는 소스에 리터럴로 남으므로 이쪽이 훨씬 안정적이다.
#
# 처음엔 fetch(...)의 첫 인자만 봤는데, 도메인이 셋인 앱을 생성하니 LLM이
# safeFetch(url, options) 래퍼를 만들어 썼고 - 그게 옳은 코드다 - 호출을 하나도
# 못 잡았다. 검사기가 코드 스타일을 강요하면 안 된다.
#
# 닫는 구분자로 백틱만 본다(따옴표는 제외). 쿼리스트링을 조립하는 삼항연산자
# `${BASE}/books${qs ? '?' + qs : ''}`처럼 ${...} 안에 홑따옴표가 들어오면,
# 따옴표에서 멈추는 정규식은 거기서 잘려 "${qs " 같은 반쪽짜리를 잡는다.
# 백틱 템플릿 리터럴은 백틱으로만 닫히므로, 내부에 따옴표가 있어도 안전하다.
_TEMPLATE_URL_RE = re.compile(r"`([^`]*\$\{\s*BASE\s*\}[^`]*)`")

# BASE 상수를 안 쓰고 경로를 따옴표 문자열로 직접 넣은 경우 (vanilla에서 흔하다).
_FETCH_RE = re.compile(r"""fetch\(\s*['"]([^'"]*)['"]""")


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def _normalize(path: str) -> str:
    """호출 경로와 명세 경로를 비교 가능한 하나의 형태로 맞춘다.

    `${BASE}/todos/${id}`  ->  /todos/{}
    /todos/{id}            ->  /todos/{}
    http://localhost:8000/todos?x=1 -> /todos
    `${BASE}/books${qs ? '?' + qs : ''}` -> /books   (쿼리스트링 조립은 버린다)

    path parameter(`/resource/${id}`)와 쿼리스트링 조립(`${BASE}/books${qs}`)을
    "/" 유무로 구분한다: "/" 바로 뒤에 오는 ${...}만 경로 파라미터로 인정하고,
    그 외의 ${...}는 거기서부터 통째로 잘라낸다. 순서가 중요하다 - 쿼리스트링
    조립 안에 리터럴 "?"가 들어있을 수 있어서(예: '?' + qs), 그걸 먼저 처리하지
    않고 "?"로 먼저 자르면 식 중간에서 잘려버린다.
    """
    p = re.sub(r"\$\{\s*BASE\s*\}", "", path)  # ${BASE} 접두사 제거
    p = re.sub(r"^https?://[^/]*", "", p)  # 절대 URL의 호스트 부분
    p = re.sub(r"(?<=/)\$\{[^}]*\}", "{}", p)  # "/" 뒤의 ${...} = path parameter
    p = re.split(r"\$\{", p)[0]  # 남은 ${...} = 쿼리스트링 조립, 거기서부터 버림
    p = re.split(r"[?#]", p)[0]  # 리터럴 쿼리스트링/해시
    p = re.sub(r"\{[^}]*\}", "{}", p)  # 명세의 {id} -> {}
    p = "/" + p.strip("/")
    return p


def _extract_calls(text: str) -> set[str]:
    return {
        _normalize(m)
        for m in _TEMPLATE_URL_RE.findall(text) + _FETCH_RE.findall(text)
    }


def _list_wrapper_keys(api_spec: dict) -> set[str]:
    """목록 응답을 감싸는 key들. api_spec은 목록 조회 response를
    {"books": [{...}]}처럼 배열을 특정 key로 감싸 정의한다(api_spec 노드 프롬프트).
    그 key(값이 배열인 것)를 모은다 - 프론트는 이 key로 응답을 풀어야 배열을 얻는다.
    """
    keys = set()
    for ep in api_spec.get("endpoints", []):
        resp = ep.get("response")
        if isinstance(resp, dict):
            keys |= {k for k, v in resp.items() if isinstance(v, list)}
    return keys


def _check_response_shape(api_spec: dict, sources_text: str) -> tuple[list[str], bool]:
    """경로는 맞아도 응답 '모양'이 어긋나는 계약 위반을 잡는다. (logs, ok)를 준다.

    백엔드가 목록을 {"books": [...]}로 감싸 주는데 프론트가 data.items처럼 다른 key로
    읽으면, 경로 검사는 통과하지만 배열을 못 푼다(실제로 {"todos":[...]}를 data.todos로
    읽어 '우연히' 맞았던 축이 CLAUDE.md의 확장 지점이었다). wrapper key가 프론트 소스에
    아예 안 나오면 그 응답을 못 풀고 있다는 신호다.

    key가 있는지만 본다(어떻게 쓰는지는 안 봄). 도메인 명사(books/members/loans)라
    프론트가 실제로 풀면 반드시 등장하므로, 부재는 강한 신호이고 오탐이 낮다.
    """
    keys = _list_wrapper_keys(api_spec)
    if not keys:
        return [], True
    missing = sorted(
        k for k in keys if not re.search(rf"\b{re.escape(k)}\b", sources_text)
    )
    if missing:
        return (
            [
                "응답 모양 불일치 가능 (경로는 맞지만 wrapper key를 안 씀): 목록 응답을 "
                + ", ".join(f"'{k}'" for k in missing)
                + " 키로 감싸는데 프론트 소스에 그 key가 없다 - 배열을 못 풀고 있을 수 있다."
            ],
            False,
        )
    return [f"목록 응답 wrapper key {len(keys)}개 전부 프론트에서 참조됨."], True


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
    if not called:
        # 호출이 하나도 없으면 위반도 0건이라 예전엔 그냥 통과했다. 실제로 프론트가
        # API를 전혀 안 부르는 상태와 구분이 안 되므로 이건 실패로 친다.
        logs.append(
            "API 호출을 하나도 못 찾음. 프론트가 백엔드를 안 부르고 있거나, "
            "URL을 리터럴로 안 쓰고 조립하고 있다 (검사기가 ${BASE}가 들어간 "
            "URL 리터럴을 찾는다)."
        )
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

    # 응답 모양(목록 wrapper key) 검사. 경로와 마찬가지로 계약이므로 passed에 반영한다.
    sources_text = "\n".join(texts)
    shape_logs, shape_ok = _check_response_shape(state["api_spec"], sources_text)
    logs += shape_logs

    # 디자인 토큰은 계약이 아니므로 passed에 반영하지 않는다 (진단만).
    logs += _check_design_tokens(sources_text)

    return {
        "frontend_report": {
            # 안 쓰는 경로는 실패로 안 치지만, 호출이 아예 없는 건 실패다.
            # 응답 wrapper key 불일치도 계약 위반이라 실패로 친다.
            "passed": bool(called) and not unknown and shape_ok,
            "logs": "\n".join(logs),
        }
    }


if __name__ == "__main__":
    # 정규화·추출 규칙이 깨지면 바로 드러나게 하는 최소 self-check.
    # src.nodes 패키지 import가 llm.py를 거치므로 .env를 먼저 읽어야 한다:
    #   python -c "from dotenv import load_dotenv; load_dotenv(); import runpy; \
    #              runpy.run_module('src.nodes.frontend.verify_frontend', run_name='__main__')"
    assert _normalize("${BASE}/todos/${id}") == "/todos/{}"
    assert _normalize("/todos/{id}") == "/todos/{}"
    assert _normalize("http://localhost:8000/todos?done=1") == "/todos"
    assert _normalize("${BASE}/todos") == "/todos"
    assert _normalize("/todos/{id}/complete") == "/todos/{}/complete"

    # 도서관 기획서를 돌렸을 때 실제로 터진 버그: 쿼리스트링을 삼항연산자로
    # 조립하면 ${...} 안에 홑따옴표가 들어온다. 이걸 "/books"로 정리하지 못하고
    # "/books${qs "처럼 반쪽만 잡아서, 위반 0건인데 통과로 잘못 판정났었다.
    assert _normalize("${BASE}/books${qs ? '?' + qs : ''}") == "/books"
    assert _normalize("${BASE}/loans${qs ? '?' + qs : ''}") == "/loans"

    html = """
      const BASE = "http://localhost:8000";
      fetch(`${BASE}/todos`);
      fetch(`${BASE}/todos/${id}/complete`, {method: "PUT"});
      fetch('/api/legacy');
    """
    assert _extract_calls(html) == {"/todos", "/todos/{}/complete", "/api/legacy"}

    # 래퍼 함수를 거쳐도 URL 리터럴만 있으면 잡아야 한다. 이걸 못 잡아서
    # "호출 0건인데 계약 검사 통과"가 났었다.
    wrapped = """
      const BASE = "http://localhost:8000";
      async function safeFetch(url, options) { return fetch(url, options); }
      const books = await safeFetch(`${BASE}/books`, undefined, setError);
      await safeFetch(`${BASE}/loans/${id}/return`, { method: 'PUT' });
      let url = `${BASE}/books`;
    """
    assert _extract_calls(wrapped) == {"/books", "/loans/{}/return"}

    # 실제 도서관 프론트가 쓴 삼항연산자 쿼리스트링 조립. 이걸 못 잡아서 호출
    # 0건 -> "명세의 경로 N개를 모두 정확히 호출함"으로 잘못 통과했었다.
    qs_wrapped = """
      const BASE = "http://localhost:8000";
      const qs = params.toString()
      const res = await fetch(`${BASE}/books${qs ? '?' + qs : ''}`)
      const res2 = await fetch(`${BASE}/loans${qs ? '?' + qs : ''}`)
    """
    assert _extract_calls(qs_wrapped) == {"/books", "/loans"}

    # 응답 모양 검사: wrapper key 추출 + 프론트 참조 여부.
    lib_spec = {
        "endpoints": [
            {"method": "GET", "path": "/books",
             "response": {"books": [{"id": "number", "title": "string"}]}},
            {"method": "GET", "path": "/loans",
             "response": {"loans": [{"id": "number"}]}},
            {"method": "POST", "path": "/books",
             "response": {"id": "number", "title": "string"}},  # 단건: wrapper 아님
        ]
    }
    assert _list_wrapper_keys(lib_spec) == {"books", "loans"}
    # 프론트가 두 key를 다 풀면 통과.
    ok_src = "const {books} = await res.json(); const d = data.loans;"
    logs, ok = _check_response_shape(lib_spec, ok_src)
    assert ok and "전부 프론트에서 참조됨" in logs[0]
    # loans를 안 풀면(예: data.items로 잘못 읽음) 실패 + 어떤 key인지 알려준다.
    bad_src = "const {books} = await res.json(); const d = data.items;"
    logs, ok = _check_response_shape(lib_spec, bad_src)
    assert not ok and "'loans'" in logs[0] and "books" not in logs[0]
    # wrapper key가 없는 명세(단건만)는 검사할 게 없어 통과.
    assert _check_response_shape({"endpoints": [lib_spec["endpoints"][2]]}, "") == ([], True)

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
