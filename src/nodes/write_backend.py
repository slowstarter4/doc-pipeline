"""
노드7: backend_code를 실제 파일로 디스크에 쓴다.

지금까지는 main.py가 그래프 실행이 끝난 뒤에 파일을 썼지만, 자기 수정 루프
(backend -> write_backend -> verify_backend -> 실패시 backend로 재생성)를 만들려면
"코드 생성"과 "파일 쓰기"가 같은 루프 안에 있어야 한다 - 재생성마다 디스크에
다시 써야 verify_backend가 최신 코드를 검증할 수 있기 때문이다.

BACKEND_OUT_DIR, 잔여 파일 정리 로직은 main.py에 있던 것과 동일하다.
"""

import json
import shutil
from pathlib import Path

from ..state import PipelineState

BACKEND_OUT_DIR = Path("generated/backend")


def write_files(out_dir: Path, files: list[dict]) -> None:
    """생성된 파일 목록을 out_dir에 쓴다. 쓰기 전에 폴더를 비운다.

    write_frontend_node도 이 함수를 쓴다 - 이전 실행의 잔여 파일이 섞이지 않게
    비우는 규칙을 두 곳에 복사하지 않기 위함.
    """
    if out_dir.exists():
        try:
            shutil.rmtree(out_dir)
        except PermissionError:
            pass  # 실행 중인 서버가 파일을 잡고 있어도 죽지 않고 덮어쓰기로 진행

    out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        path = out_dir / f["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f["content"], encoding="utf-8")


def write_backend_node(state: PipelineState) -> dict:
    backend_code = state["backend_code"]

    if backend_code.get("_parse_error"):
        # 파싱 실패 - verify 단계로 넘겨서 "실행 자체가 불가능함"으로 처리되게 한다.
        return {
            "verify_report": {
                "passed": False,
                "logs": f"백엔드 코드 JSON 파싱 실패:\n{backend_code.get('_raw', '')[:2000]}",
            }
        }

    write_files(BACKEND_OUT_DIR, backend_code.get("files", []))

    if "openapi_spec" in state:
        out_path = BACKEND_OUT_DIR / "openapi.json"
        out_path.write_text(
            json.dumps(state["openapi_spec"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 이전 시도의 리포트를 지운다 - 안 지우면 verify_backend가 낡은 파싱 실패
    # 리포트를 보고 검증을 건너뛴다.
    return {"verify_report": None}
