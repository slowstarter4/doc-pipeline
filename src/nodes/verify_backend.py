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


def _wait_for_server(base_url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{base_url}/todos", timeout=1)
            return True
        except requests.exceptions.RequestException:
            time.sleep(POLL_INTERVAL)
    return False


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
    base_url: str, proc: subprocess.Popen
) -> tuple[list[str], subprocess.Popen | None]:
    """항목을 하나 만들고 서버를 껐다 켠 뒤에도 남아있는지 본다.

    이게 in-memory 구현과 DB 구현을 가르는 유일한 검사다. 스모크 테스트는 서버가
    떠 있는 동안만 보므로 메모리에만 담아둬도 전부 통과한다.

    떠 있는 서버(proc)를 받아서 POST → 종료 → 재기동 → 조회 순으로 진행하고,
    새로 띄운 프로세스를 돌려준다 (호출한 쪽이 정리한다).
    """
    try:
        r = requests.post(
            f"{base_url}/todos",
            json={"title": "영속성 확인용", "dueDate": "2026-01-01"},
            timeout=5,
        )
        if r.status_code not in (200, 201):
            _stop_server(proc)
            return [f"영속성 검사용 POST가 실패함: {r.status_code}"], None
        new_id = r.json().get("id")
    except Exception as e:
        _stop_server(proc)
        return [f"영속성 검사용 POST 중 예외: {e}"], None

    _stop_server(proc)

    problems: list[str] = []
    new_proc = _start_server()
    if not _wait_for_server(base_url, STARTUP_TIMEOUT):
        stderr = _stop_server(new_proc)
        problems.append(
            f"영속성 검사를 위해 서버를 재기동했는데 {STARTUP_TIMEOUT}초 안에 "
            f"안 떴음. stderr:\n{stderr[-1000:]}"
        )
        return problems, None

    try:
        r = requests.get(f"{base_url}/todos", timeout=5)
        if new_id not in _list_ids(r.json()):
            problems.append(
                "서버를 껐다 켜니 방금 만든 항목이 사라짐 - 데이터를 메모리에만 "
                "들고 있다는 뜻이다. sqlite3 파일 DB(todos.db)에 저장하도록 고쳐야 한다. "
                f"재기동 후 응답: {r.text[:300]}"
            )
        else:
            requests.delete(f"{base_url}/todos/{new_id}", timeout=5)
    except Exception as e:
        problems.append(f"재기동 후 목록 조회 중 예외: {e}")

    return problems, new_proc


def _run_smoke_test(base_url: str) -> list[str]:
    """기본 CRUD 흐름을 실제로 호출해서 문제를 텍스트 목록으로 모은다.
    빈 리스트면 전부 통과."""
    problems = []

    try:
        r = requests.get(f"{base_url}/todos", timeout=5)
        if r.status_code != 200:
            problems.append(f"GET /todos: 200이 아니라 {r.status_code} 반환")
    except Exception as e:
        problems.append(f"GET /todos 요청 자체가 실패함: {e}")
        return problems  # 목록 조회도 안 되면 나머지는 의미 없음

    try:
        r = requests.post(
            f"{base_url}/todos",
            json={"title": "테스트 할 일", "dueDate": "2026-01-01"},
            timeout=5,
        )
        if r.status_code not in (200, 201):
            problems.append(
                f"POST /todos: 200/201이 아니라 {r.status_code} 반환 (body: {r.text[:300]})"
            )
        else:
            body = r.json()
            new_id = body.get("id")
            if new_id is None:
                problems.append(f"POST /todos 응답에 id 필드가 없음: {body}")
            else:
                # 완료 처리
                r2 = requests.put(f"{base_url}/todos/{new_id}/complete", timeout=5)
                if r2.status_code != 200:
                    problems.append(
                        f"PUT /todos/{new_id}/complete: 200이 아니라 {r2.status_code} 반환"
                    )
                # 삭제
                r3 = requests.delete(f"{base_url}/todos/{new_id}", timeout=5)
                if r3.status_code != 200:
                    problems.append(
                        f"DELETE /todos/{new_id}: 200이 아니라 {r3.status_code} 반환"
                    )
    except Exception as e:
        problems.append(f"POST/PUT/DELETE 흐름 중 예외 발생: {e}")

    return problems


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

        # 이전 실행이 남긴 DB 파일이 있으면 지운다. 안 지우면 지난번 데이터가 남아
        # "재기동 후에도 항목이 있다"가 이번 코드의 성과인지 잔여물인지 구분이 안 된다.
        db_file = BACKEND_DIR / "todos.db"
        if db_file.exists():
            try:
                db_file.unlink()
            except PermissionError:
                pass  # 다른 프로세스가 잡고 있어도 죽지 않고 진행

        proc = _start_server()

        if not _wait_for_server(base_url, STARTUP_TIMEOUT):
            stderr = _stop_server(proc)
            return {
                "verify_report": {
                    "passed": False,
                    "logs": f"서버가 {STARTUP_TIMEOUT}초 안에 기동하지 못함. stderr:\n{stderr[-2000:]}",
                }
            }

        problems = _run_smoke_test(base_url)
        if problems:
            return {
                "verify_report": {
                    "passed": False,
                    "logs": "스모크 테스트 실패:\n"
                    + "\n".join(f"- {p}" for p in problems),
                }
            }

        # 영속성 검사는 서버를 한 번 껐다 켜야 하므로 스모크가 통과한 뒤에만 한다.
        problems, proc = _check_persistence(base_url, proc)
        if problems:
            return {
                "verify_report": {
                    "passed": False,
                    "logs": "영속성 검사 실패:\n"
                    + "\n".join(f"- {p}" for p in problems),
                }
            }

        return {
            "verify_report": {
                "passed": True,
                "logs": "모든 스모크 테스트 통과 (재기동 후 데이터 유지 확인 포함)",
            }
        }

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
    print("verify_backend self-check 통과")
