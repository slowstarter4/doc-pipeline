"""
노드: test_code를 generated/tests/에 쓴다.

test_gen은 재시도 루프가 없다(생성만, 실행은 사람이). 그래서 write_backend처럼
루프 안에 있을 필요는 없지만, "생성 노드는 자기 산출물 필드만 반환한다" 규칙을
지키려고 쓰기를 별도 노드로 뺐다. write_files는 write_backend 것을 재사용한다
(잔여 파일 정리 규칙을 세 곳에 복사하지 않기 위함).
"""

from pathlib import Path

from ...state import PipelineState
from .write_backend import write_files

TESTS_OUT_DIR = Path("generated/tests")


def write_tests_node(state: PipelineState) -> dict:
    test_code = state.get("test_code") or {}
    if test_code.get("_parse_error"):
        # 파싱 실패해도 파이프라인을 멈추지 않는다 - 테스트는 생성만 하는 곁가지라
        # 실패해도 backend/frontend 갈래에 영향이 없다. 사람이 로그로 확인한다.
        return {}
    write_files(TESTS_OUT_DIR, test_code.get("files", []))
    return {}
