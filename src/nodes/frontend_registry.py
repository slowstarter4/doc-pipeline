"""
프론트엔드 구현체 레지스트리. backend_registry와 같은 패턴이다.

새 스택을 추가하는 법: 1) src/nodes/frontend_xxx.py에 노드 함수를 만든다
(입력: PipelineState, 출력: {"frontend_code": {"files": [...]}})
2) 아래 FRONTEND_NODES에 한 줄 등록한다. graph.py는 이 딕셔너리만 보고
   고르기 때문에 배선을 따로 손댈 필요가 없다.

어떤 스택이든 fetch(`${BASE}/경로`) 형태를 쓰도록 프롬프트에서 강제해야 한다 -
verify_frontend가 그 형태를 기준으로 계약을 검사하기 때문이다.
"""

from .frontend import frontend_node
from .frontend_react import frontend_react_node

# key = .env의 FRONTEND_TARGET 값 (소문자)
FRONTEND_NODES = {
    "vanilla": frontend_node,       # 빌드 없는 단일 index.html
    "react": frontend_react_node,   # React + Vite
}

# 각 타깃의 실행 안내 메시지 (main.py에서 사용)
FRONTEND_RUN_INSTRUCTIONS = {
    "vanilla": "index.html을 브라우저로 바로 열면 됨 (빌드 불필요)",
    "react": "npm install && npm run dev  (기본 http://localhost:5173)",
}
