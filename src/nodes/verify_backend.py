"""
노드8: 생성된 백엔드를 실제로 실행해서 검증한다 (지금은 FastAPI만).

오늘 우리가 손으로 20번 넘게 반복한 "생성 -> 서버 실행 -> curl로 확인 -> 실패면
원인 진단 -> 프롬프트 수정 -> 재생성"을 자동화하는 게 이 노드의 목적이다.

범위를 FastAPI 하나로 좁힌 이유: 스택마다 기동 방식(uvicorn vs gradle bootRun vs
npm start)과 빌드 시간, 실패 모드(포트 예약, Gradle 버전, 컴파일 시간)가 크게
달라서, 전부 한 번에 자동화하면 오늘 겪은 것 같은 환경 문제까지 다 떠안게 된다.
FastAPI는 기동이 빠르고(별도 컴파일 없음) 실패가 곧바로 드러나서 첫 번째
자기 수정 루프 대상으로 적합하다. 다른 스택은 검증을 건너뛰고 바로 통과시킨다
(수동 검증은 여전히 유효 - 오늘 실제로 다 해봤다).

검증 방법: 전용 포트(사람이 수동으로 쓰는 8000과 겹치지 않게)에서 서버를 띄우고,
POST/GET/PUT/DELETE 기본 흐름을 requests로 직접 호출해 스모크 테스트한다.
schemathesis 수준의 정밀한 계약 검사는 아니지만(그건 사람이 여전히 손으로
돌릴 수 있다), "애초에 서버가 뜨는지, 기본 CRUD가 도는지"는 확실히 잡아낸다.

실패하면 verify_report.logs에 원인(서버 시작 실패 로그, 스모크 테스트 실패
메시지)을 담아 state에 남긴다. 이 로그는 backend_node가 재생성할 때 프롬프트에
포함시켜, LLM이 "왜 실패했는지"를 보고 고치도록 한다.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from ..state import PipelineState

VERIFY_PORT = 8010
BACKEND_DIR = Path("generated/backend")
STARTUP_TIMEOUT = 20  # 초
POLL_INTERVAL = 0.5


def _wait_for_server(base_url: str, probe_path: str, timeout: float) -> bool:
    """probe_path로 응답이 오기 시작할 때까지 기다린다.

    상태 코드는 안 본다 - 404여도 서버는 뜬 것이다. 여기서 보는 건 '기동했나'뿐이고,
    응답이 맞는지는 스모크 테스트가 본다.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{base_url}{probe_path}", timeout=1)
            return True
        except requests.exceptions.RequestException:
            time.sleep(POLL_INTERVAL)
    return False


_SAMPLE_BY_TYPE = {
    "string": "테스트",
    "number": 1,
    "boolean": False,
    "date": "2026-01-01",
}


def _plain_get_paths(api_spec: dict) -> list[str]:
    """path parameter가 없는 GET 경로들. 어떤 기획문서든 목록 조회는 여기 걸린다."""
    return [
        ep["path"]
        for ep in api_spec.get("endpoints", [])
        if ep.get("method", "").upper() == "GET" and "{" not in ep.get("path", "")
    ]


def _first_create(api_spec: dict) -> tuple[str, dict] | None:
    """첫 번째 '생성' 엔드포인트와 보낼 body를 만든다. 없으면 None.

    body 값은 타입만 보고 지어낸 더미다. 그래서 enum(분류: 소설/비소설/...)이나
    자릿수 제약(ISBN 13자리), 외래키 같은 규칙은 못 맞춘다 - 그런 건 400을 받고
    호출한 쪽이 '검사 못 함'으로 처리한다. 여기서 정교한 값 생성을 하지 않는 이유:
    그건 schemathesis가 하는 일이고, 이 노드의 목적은 '서버가 살아서 명세대로
    반응하나'까지다.
    """
    for ep in api_spec.get("endpoints", []):
        if ep.get("method", "").upper() != "POST" or "{" in ep.get("path", ""):
            continue
        request = ep.get("request") or {}
        if not isinstance(request, dict) or not request:
            continue
        body = {k: _SAMPLE_BY_TYPE.get(v, "테스트") for k, v in request.items()}
        return ep["path"], body
    return None


def _start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(VERIFY_PORT)],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _stop_server(proc: subprocess.Popen) -> str:
    """서버를 멈추고 stderr를 회수한다. 실패 로그에 쓸 수 있게."""
    proc.terminate()
    try:
        _, stderr = proc.communicate(timeout=5)
        return stderr or ""
    except subprocess.TimeoutExpired:
        proc.kill()
        return "(서버 강제 종료, 로그 회수 실패)"


def _list_ids(payload) -> list:
    """목록 조회 응답에서 id들을 뽑는다.

    스택마다 목록을 그냥 배열로 주기도 하고 {"todos": [...]}처럼 감싸서 주기도 해서,
    둘 다 받아준다. 여기서 모양을 강제하지 않는 이유: 응답 모양은 api_spec이 정하는
    계약이고, 이 함수는 '데이터가 남아있나'만 보면 되기 때문이다.
    """
    items = payload
    if isinstance(payload, dict):
        lists = [v for v in payload.values() if isinstance(v, list)]
        items = lists[0] if lists else []
    if not isinstance(items, list):
        return []
    return [item.get("id") for item in items if isinstance(item, dict)]


def _check_persistence(
    base_url: str, api_spec: dict, proc: subprocess.Popen
) -> tuple[list[str], list[str], subprocess.Popen | None]:
    """항목을 하나 만들고 서버를 껐다 켠 뒤에도 남아있는지 본다.
    (problems, notes, 새 프로세스)를 돌려준다.

    이게 in-memory 구현과 DB 구현을 가르는 검사다. 스모크 테스트는 서버가 떠 있는
    동안만 보므로 메모리에만 담아둬도 전부 통과한다.

    더미 body가 도메인 규칙(enum, 자릿수, 외래키)에 걸려 생성이 거부되면 이 검사를
    할 수 없다. 그때는 실패로 치지 않고 DB 파일 존재 여부로 대체한다.
    """
    create = _first_create(api_spec)
    if create is None:
        return [], ["생성 엔드포인트가 없어 영속성 검사를 건너뜀."], proc

    path, body = create
    new_id = None
    try:
        r = requests.post(f"{base_url}{path}", json=body, timeout=5)
        if r.status_code in (200, 201):
            new_id = r.json().get("id")
    except Exception:
        pass  # 아래에서 대체 검사로 넘어간다

    _stop_server(proc)

    if new_id is None:
        # ponytail: 더미 데이터가 도메인 규칙에 막혔다. 진짜 왕복 검사 대신 DB 파일
        # 존재만 본다. 파일을 만들어놓고 데이터는 메모리에 두는 구현은 못 잡는다 -
        # 정교한 값 생성이 필요하면 그건 schemathesis의 일이다.
        db_files = list(BACKEND_DIR.glob("*.db"))
        note = (
            f"영속성 왕복 검사는 못 함 (더미 데이터가 POST {path}에서 거부됨 - "
            "enum·자릿수·외래키 같은 규칙 때문일 수 있다). "
            + (
                f"대신 DB 파일 확인: {[f.name for f in db_files]}"
                if db_files
                else "DB 파일도 없음 - 메모리에만 저장하는 구현일 수 있다."
            )
        )
        return ([] if db_files else [note]), ([note] if db_files else []), None

    problems: list[str] = []
    new_proc = _start_server()
    if not _wait_for_server(base_url, path, STARTUP_TIMEOUT):
        stderr = _stop_server(new_proc)
        problems.append(
            f"영속성 검사를 위해 서버를 재기동했는데 {STARTUP_TIMEOUT}초 안에 "
            f"안 떴음. stderr:\n{stderr[-1000:]}"
        )
        return problems, [], None

    try:
        r = requests.get(f"{base_url}{path}", timeout=5)
        if new_id not in _list_ids(r.json()):
            problems.append(
                "서버를 껐다 켜니 방금 만든 항목이 사라짐 - 데이터를 메모리에만 "
                "들고 있다는 뜻이다. sqlite3 파일 DB에 저장하도록 고쳐야 한다. "
                f"재기동 후 응답: {r.text[:300]}"
            )
        else:
            requests.delete(f"{base_url}{path}/{new_id}", timeout=5)
    except Exception as e:
        problems.append(f"재기동 후 목록 조회 중 예외: {e}")

    return problems, [], new_proc


def _run_smoke_test(base_url: str, api_spec: dict) -> tuple[list[str], list[str]]:
    """명세에 있는 경로를 실제로 호출한다. (problems, notes)를 돌려준다.

    기획문서마다 경로도 도메인도 다르므로 경로를 하드코딩하지 않는다. 확실히 검사할
    수 있는 건 'path parameter 없는 GET이 200을 주나'다 - 여기서 서버 크래시,
    라우트 누락, 기동 직후 예외가 다 드러난다.

    생성(POST)은 더미 body로 시도하되, 거부당해도 실패로 치지 않는다. 값이 도메인
    규칙에 안 맞을 뿐 서버가 틀린 게 아닐 수 있기 때문이다.
    """
    problems: list[str] = []
    notes: list[str] = []

    get_paths = _plain_get_paths(api_spec)
    if not get_paths:
        notes.append("명세에 path parameter 없는 GET이 없어 조회 검사를 건너뜀.")

    for path in get_paths:
        try:
            r = requests.get(f"{base_url}{path}", timeout=5)
            if r.status_code != 200:
                problems.append(
                    f"GET {path}: 200이 아니라 {r.status_code} 반환 (body: {r.text[:200]})"
                )
        except Exception as e:
            problems.append(f"GET {path} 요청 자체가 실패함: {e}")

    create = _first_create(api_spec)
    if create is None:
        notes.append("명세에 request body가 있는 POST가 없어 생성 검사를 건너뜀.")
        return problems, notes

    path, body = create
    try:
        r = requests.post(f"{base_url}{path}", json=body, timeout=5)
        if r.status_code in (200, 201):
            if r.json().get("id") is None:
                problems.append(f"POST {path} 응답에 id 필드가 없음: {r.text[:200]}")
            else:
                notes.append(f"POST {path} 생성 확인됨.")
        elif r.status_code >= 500:
            problems.append(
                f"POST {path}: 서버 오류 {r.status_code} (body: {r.text[:300]})"
            )
        else:
            notes.append(
                f"POST {path}가 더미 데이터를 {r.status_code}로 거부함 - 도메인 규칙"
                "(enum·자릿수·외래키)일 수 있어 실패로 치지 않는다."
            )
    except Exception as e:
        problems.append(f"POST {path} 중 예외 발생: {e}")

    return problems, notes


def verify_backend_node(state: PipelineState) -> dict:
    target = os.getenv("BACKEND_TARGET", "fastapi").lower()
    if target != "fastapi":
        # 다른 스택은 자동 검증 대상 밖 - 통과로 처리하고 넘어간다.
        return {
            "verify_report": {
                "passed": True,
                "logs": "(자동 검증은 fastapi 전용 - 건너뜀)",
            }
        }

    # 이미 파일 쓰기 단계에서 파싱 실패로 verify_report가 채워졌으면 그대로 유지.
    if state.get("verify_report") and state["verify_report"].get("logs", "").startswith(
        "백엔드 코드 JSON 파싱"
    ):
        return {}

    base_url = f"http://127.0.0.1:{VERIFY_PORT}"
    proc = None
    try:
        if not (BACKEND_DIR / "requirements.txt").exists():
            return {
                "verify_report": {
                    "passed": False,
                    "logs": f"{BACKEND_DIR}/requirements.txt 파일이 없음 - 백엔드 생성이 "
                    f"제대로 안 됐을 수 있음. 폴더 내용: {list(BACKEND_DIR.glob('*'))}",
                }
            }

        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install.returncode != 0:
            return {
                "verify_report": {
                    "passed": False,
                    "logs": f"의존성 설치 실패:\n{install.stderr[-2000:]}",
                }
            }

        # 이전 실행이 남긴 DB 파일들을 지운다. 안 지우면 지난번 데이터가 남아
        # "재기동 후에도 항목이 있다"가 이번 코드의 성과인지 잔여물인지 구분이 안 된다.
        # 파일명은 기획문서마다 다르므로(todos.db, library.db...) 확장자로 찾는다.
        for db_file in BACKEND_DIR.glob("*.db"):
            try:
                db_file.unlink()
            except PermissionError:
                pass  # 다른 프로세스가 잡고 있어도 죽지 않고 진행

        api_spec = state.get("api_spec") or {}
        probe = (_plain_get_paths(api_spec) or ["/"])[0]

        proc = _start_server()

        if not _wait_for_server(base_url, probe, STARTUP_TIMEOUT):
            stderr = _stop_server(proc)
            return {
                "verify_report": {
                    "passed": False,
                    "logs": f"서버가 {STARTUP_TIMEOUT}초 안에 기동하지 못함. stderr:\n{stderr[-2000:]}",
                }
            }

        problems, notes = _run_smoke_test(base_url, api_spec)
        if problems:
            return {
                "verify_report": {
                    "passed": False,
                    "logs": "스모크 테스트 실패:\n"
                    + "\n".join(f"- {p}" for p in problems),
                }
            }

        # 영속성 검사는 서버를 한 번 껐다 켜야 하므로 스모크가 통과한 뒤에만 한다.
        problems, persist_notes, proc = _check_persistence(base_url, api_spec, proc)
        if problems:
            return {
                "verify_report": {
                    "passed": False,
                    "logs": "영속성 검사 실패:\n"
                    + "\n".join(f"- {p}" for p in problems),
                }
            }

        checked = f"조회 {len(_plain_get_paths(api_spec))}개 경로 확인"
        logs = [f"스모크 테스트 통과 ({checked})"]
        logs += [f"- {n}" for n in notes + persist_notes]
        return {"verify_report": {"passed": True, "logs": "\n".join(logs)}}

    except Exception as e:
        # 예상 못한 예외(경로 문제, subprocess 실행 실패 등)도 반드시 로그로 남긴다.
        # 이게 없으면 verify_report가 아예 비워진 채로 조용히 넘어가는 침묵 실패가 생긴다.
        import traceback

        return {
            "verify_report": {
                "passed": False,
                "logs": f"verify_backend_node 실행 중 예외 발생: {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()[-2000:]}",
            }
        }

    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    # 목록 응답 모양이 스택마다 다른데, 영속성 검사가 거기 걸려 넘어지면 안 된다.
    # .env를 먼저 읽어야 패키지 import가 통과한다:
    #   python -c "from dotenv import load_dotenv; load_dotenv(); import runpy; \
    #              runpy.run_module('src.nodes.verify_backend', run_name='__main__')"
    assert _list_ids([{"id": 1}, {"id": 2}]) == [1, 2]
    assert _list_ids({"todos": [{"id": 3}]}) == [3]
    assert _list_ids({"count": 0, "items": [{"id": 4}]}) == [4]
    assert _list_ids({}) == []
    assert _list_ids(None) == []
    assert _list_ids([{"noid": 1}]) == [None]

    # 경로·body를 명세에서 뽑는다. 하드코딩된 /todos로 돌아가면 여기서 깨진다.
    spec = {
        "endpoints": [
            {"method": "GET", "path": "/books"},
            {"method": "GET", "path": "/books/{id}"},
            {"method": "POST", "path": "/books",
             "request": {"title": "string", "isbn": "string", "count": "number"}},
            {"method": "GET", "path": "/loans"},
        ]
    }
    assert _plain_get_paths(spec) == ["/books", "/loans"]
    assert _first_create(spec) == (
        "/books",
        {"title": "테스트", "isbn": "테스트", "count": 1},
    )
    assert _first_create({"endpoints": [{"method": "GET", "path": "/x"}]}) is None
    print("verify_backend self-check 통과")
