"""
노드10: frontend_code를 generated/frontend/에 쓴다.

write_backend와 같은 이유로 별도 노드다 - 나중에 프론트에도 재시도 루프를 붙이면
재생성마다 디스크에 다시 써야 하기 때문이다. 폴더 비우기·쓰기 로직은
write_backend.write_files를 그대로 쓴다.
"""

from pathlib import Path

from ..state import PipelineState
from .write_backend import write_files

FRONTEND_OUT_DIR = Path("generated/frontend")


def write_frontend_node(state: PipelineState) -> dict:
    frontend_code = state["frontend_code"]

    if frontend_code.get("_parse_error"):
        return {
            "frontend_report": {
                "passed": False,
                "logs": f"프론트엔드 코드 JSON 파싱 실패:\n{frontend_code.get('_raw', '')[:2000]}",
            }
        }

    write_files(FRONTEND_OUT_DIR, frontend_code.get("files", []))
    return {"frontend_report": None}
