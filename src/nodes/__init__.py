"""파이프라인 노드들. 단계별 하위 패키지로 나눠 둔다:
- docs/     : 문서 생성·검토 (requirements ~ review_gate)
- backend/  : 백엔드 생성·DB 스키마·쓰기·실행 검증 (스택 레지스트리 포함)
- frontend/ : 프론트 생성·쓰기·계약 검증 (스택 레지스트리 포함)

graph.py는 이 __init__의 재수출만 쓴다 - 파일을 옮겨도 여기 경로만 고치면 되고
그래프 배선은 안 바뀐다.
"""

from .docs.requirements import requirements_node
from .docs.screen_design import screen_design_node
from .docs.data_model import data_model_node
from .backend.schema_ddl import schema_ddl_node
from .docs.api_spec import api_spec_node
from .docs.openapi_spec import openapi_spec_node
from .docs.consistency_check import consistency_check_node
from .docs.review_gate import review_gate_node
from .backend.write_backend import write_backend_node
from .backend.verify_backend import verify_backend_node
from .frontend.write_frontend import write_frontend_node
from .frontend.verify_frontend import verify_frontend_node
from .backend.backend_registry import BACKEND_NODES, RUN_INSTRUCTIONS
from .frontend.frontend_registry import FRONTEND_NODES, FRONTEND_RUN_INSTRUCTIONS

__all__ = [
    "requirements_node",
    "screen_design_node",
    "data_model_node",
    "schema_ddl_node",
    "api_spec_node",
    "openapi_spec_node",
    "consistency_check_node",
    "review_gate_node",
    "write_backend_node",
    "verify_backend_node",
    "write_frontend_node",
    "verify_frontend_node",
    "BACKEND_NODES",
    "RUN_INSTRUCTIONS",
    "FRONTEND_NODES",
    "FRONTEND_RUN_INSTRUCTIONS",
]
