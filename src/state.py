"""
공유 상태(state) = 노드 사이로 흐르는 문서들.

원칙: 각 노드는 여기서 필요한 필드를 읽고, 자기 산출물 필드만 되돌려준다.
      LangGraph가 그 조각을 이 state에 병합해준다.
"""

from typing import TypedDict, Optional


class PipelineState(TypedDict, total=False):
    # ── 입력 ──
    plan_doc: str  # 사람이 쓴 기획문서 (ground truth)

    # ── 문서화 단계 산출물 ──
    requirements: Optional[str]  # 요구사항정의서
    screen_design: Optional[str]  # 화면설계서 (markdown, fan-out)
    data_model: Optional[dict]  # ERD (JSON, fan-out)
    schema_ddl: Optional[str]  # ERD의 결정적 sqlite DDL 변환 (백엔드가 이 스키마를 공유)
    api_spec: Optional[dict]  # API 명세 (OpenAPI-lite, 공유 계약. fan-in 이후 도출)
    openapi_spec: Optional[dict]  # 정식 OpenAPI 3.0 문서 (api_spec의 결정적 변환)
    consistency_report: Optional[dict]  # 일관성 체크 리포트 (진단만, 자동 수정 없음)
    approved: Optional[bool]  # HITL 게이트 결과 - 사람이 진행을 승인했는지
    backend_code: Optional[dict]  # {"files": [{"path", "content"}, ...]}
    verify_report: Optional[
        dict
    ]  # {"passed": bool, "logs": str} - 백엔드 실행 검증 결과
    retry_count: Optional[int]  # backend 재생성 시도 횟수 (무한 루프 방지)
    frontend_code: Optional[dict]  # {"files": [{"path", "content"}, ...]}
    frontend_report: Optional[
        dict
    ]  # {"passed": bool, "logs": str} - fetch 경로 ↔ api_spec 대조 결과
    frontend_retry_count: Optional[int]  # frontend 재생성 시도 횟수 (무한 루프 방지)
    test_code: Optional[dict]  # {"files": [...]} - api_spec에서 생성한 pytest 계약 테스트
