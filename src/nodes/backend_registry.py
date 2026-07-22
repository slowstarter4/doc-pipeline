"""
백엔드 구현체 레지스트리.

새 스택을 추가하는 법: 1) src/nodes/backend_xxx.py에 노드 함수를 만든다
(입력: PipelineState, 출력: {"backend_code": {"files": [...]}})
2) 아래 BACKEND_NODES에 한 줄 등록한다. graph.py는 이 딕셔너리만 보고
   고르기 때문에 배선을 따로 손댈 필요가 없다.

이렇게 레지스트리로 묶어두는 이유: graph.py에 if/elif가 스택 개수만큼
늘어나는 걸 막고, 등록 여부를 한눈에 볼 수 있게 하기 위함.
"""

from .backend import backend_node
from .backend_spring import backend_spring_node
from .backend_express import backend_express_node
from .backend_express_ts import backend_express_ts_node

# key = .env의 BACKEND_TARGET 값 (소문자)
BACKEND_NODES = {
    "fastapi": backend_node,           # Python
    "spring": backend_spring_node,     # Java
    "express": backend_express_node,   # Node.js (JavaScript)
    "typescript": backend_express_ts_node,  # Node.js (TypeScript)
}

# 각 타깃의 실행 안내 메시지 (main.py에서 사용)
RUN_INSTRUCTIONS = {
    "fastapi": "pip install -r requirements.txt && uvicorn main:app --reload",
    "spring": "./gradlew bootRun",
    "express": "npm install && npm start",
    "typescript": "npm install && npm run build && npm start",
}
