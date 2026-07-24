"""
백엔드 구현체 레지스트리.

새 스택을 추가하는 법: 1) src/nodes/backend_xxx.py에 노드 함수를 만든다
(입력: PipelineState, 출력: {"backend_code": {"files": [...]}})
2) 아래 BACKEND_NODES에 한 줄 등록한다. graph.py는 이 딕셔너리만 보고
   고르기 때문에 배선을 따로 손댈 필요가 없다.

이렇게 레지스트리로 묶어두는 이유: graph.py에 if/elif가 스택 개수만큼
늘어나는 걸 막고, 등록 여부를 한눈에 볼 수 있게 하기 위함.
"""

from .backend import backend_node, PORT as _FASTAPI_PORT
from .backend_spring import backend_spring_node, PORT as _SPRING_PORT
from .backend_express import backend_express_node, PORT as _EXPRESS_PORT
from .backend_express_ts import backend_express_ts_node, PORT as _EXPRESS_TS_PORT

# key = .env의 BACKEND_TARGET 값 (소문자)
BACKEND_NODES = {
    "fastapi": backend_node,           # Python
    "spring": backend_spring_node,     # Java
    "express": backend_express_node,   # Node.js (JavaScript)
    "typescript": backend_express_ts_node,  # Node.js (TypeScript)
}

# 각 스택이 실제로 뜨는 포트. 숫자 자체는 각 backend_*.py의 PORT 상수가 정본이고
# (거기서 생성 프롬프트가 그 값으로 서버를 띄우게 시킨다), 여기서는 다시 내보내기만
# 한다 - 두 곳에 같은 숫자를 따로 적어두면 하나만 바뀌었을 때 어긋난다.
#
# frontend 생성 노드(frontend.py, frontend_react.py)가 이 딕셔너리로 BASE 상수의
# 포트를 맞춘다. 실제로 BASE가 8000(fastapi 기본값)에 하드코딩돼 있어서 스프링
# (8080)으로 바꿨더니 프론트가 백엔드에 연결을 못 한 적이 있다.
BACKEND_PORTS = {
    "fastapi": _FASTAPI_PORT,
    "spring": _SPRING_PORT,
    "express": _EXPRESS_PORT,
    "typescript": _EXPRESS_TS_PORT,
}

# 각 타깃의 실행 안내 메시지 (main.py에서 사용)
RUN_INSTRUCTIONS = {
    "fastapi": f"pip install -r requirements.txt && uvicorn main:app --reload --port {_FASTAPI_PORT}",
    "spring": "./gradlew bootRun",
    "express": "npm install && npm start",
    "typescript": "npm install && npm run build && npm start",
}
