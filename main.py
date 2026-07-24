"""
진입점. 프로젝트 루트에서 실행:  python main.py

파일 쓰기(write_backend_node)와 실행 검증(verify_backend_node, fastapi 한정)은
이제 그래프 안에서 일어난다 - 재시도 루프가 backend로 돌아갈 때마다 디스크에
다시 써야 하기 때문에, "파이프라인 다 끝난 뒤 마지막에 파일 쓰기"였던 이전
구조로는 루프를 만들 수 없었다. main.py는 이제 결과 출력과 사람 승인만 맡는다.
"""

import json
import os
import sys
from pathlib import Path

# 윈도우 콘솔 기본 인코딩(cp949)에서는 아래 출력의 이모지(✅ 🚦 등)가
# UnicodeEncodeError로 파이프라인 결과 출력을 통째로 죽인다. 파이프로
# 연결했을 때(python main.py | tail)도 마찬가지. 표준 출력만 utf-8로 돌린다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()  # src import보다 먼저! .env를 여기서 먼저 읽어야 함

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graph import build_pipeline
from src.nodes import RUN_INSTRUCTIONS, FRONTEND_RUN_INSTRUCTIONS

BACKEND_OUT_DIR = Path("generated/backend")
FRONTEND_OUT_DIR = Path("generated/frontend")


def print_docs(result: dict):
    print("=" * 60)
    print("요구사항정의서\n")
    print(result["requirements"])

    print("=" * 60)
    print("화면설계서\n")
    print(result["screen_design"])

    print("=" * 60)
    print("데이터 모델 (ERD)\n")
    print(json.dumps(result["data_model"], ensure_ascii=False, indent=2))

    print("=" * 60)
    print("API 명세 (JSON)\n")
    print(json.dumps(result["api_spec"], ensure_ascii=False, indent=2))

    print("=" * 60)
    print("OpenAPI 3.0 문서 (schemathesis 계약 검사용, 결정적 변환)\n")
    n_paths = len(result["openapi_spec"].get("paths", {}))
    print(f"  {n_paths}개 경로 변환 완료 (generated/backend/openapi.json으로 저장됨)")

    print("=" * 60)
    print("일관성 체크 리포트\n")
    report = result["consistency_report"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("passed") is False:
        print(
            f"\n⚠️  이슈 {len(report.get('issues', []))}건 발견 — 아래에서 검토하세요."
        )
    elif report.get("passed") is True:
        print("\n✅  일관성 체크 통과.")


def ask_human_approval(payload: dict) -> str:
    """review_gate의 interrupt() 페이로드를 사람에게 보여주고 승인/거부를 입력받는다."""
    print("\n" + "=" * 60)
    print("🚦 검토 게이트 (HITL) - 사람의 판단이 필요합니다\n")
    print(payload["question"])
    print()
    for issue in payload["issues"]:
        print(f"  [{issue.get('severity', '?')}] {issue.get('location', '')}")
        print(f"      {issue.get('description', '')}")
    print()
    while True:
        ans = input("진행할까요? (y=승인 / n=중단): ").strip().lower()
        if ans in ("y", "yes"):
            return "approve"
        if ans in ("n", "no"):
            return "reject"
        print("y 또는 n으로 답해주세요.")


def print_verify_result(result: dict):
    print("=" * 60)
    print("백엔드 실행 검증 (자기 수정 루프)\n")
    report = result.get("verify_report") or {}
    retry_count = result.get("retry_count", 0)
    print(f"  재시도 횟수: {retry_count}")
    print(f"  로그:\n{report.get('logs', '(없음)')}")

    target = os.getenv("BACKEND_TARGET", "fastapi").lower()
    if report.get("passed") is True:
        print("\n✅  자동 검증 통과.")
    elif target == "fastapi":
        print(
            f"\n🚫 재시도 {retry_count}회 후에도 통과하지 못했습니다. 로그를 보고 수동으로 확인해 주세요."
        )
    else:
        print(
            f"\nℹ️  {target}은 자동 검증 대상이 아닙니다 (fastapi만 지원). 아래 안내로 수동 확인하세요."
        )

    cmd = RUN_INSTRUCTIONS.get(target, "(알 수 없는 타깃)")
    print(f"\n👉 서버 실행 ({target}): cd {BACKEND_OUT_DIR} && {cmd}")
    print(
        "\n🔍 계약 검사 (서버를 위 명령으로 띄운 뒤, 별도 터미널에서 실행):\n"
        "   pip install schemathesis\n"
        f"   schemathesis run {BACKEND_OUT_DIR}/openapi.json "
        "--url http://localhost:포트번호 --checks all"
    )


def print_frontend_result(result: dict):
    print("=" * 60)
    print("프론트엔드 계약 검사 (fetch 경로 ↔ API 명세, LLM 미사용)\n")
    report = result.get("frontend_report") or {}
    retry_count = result.get("frontend_retry_count", 0)
    print(f"  재시도 횟수: {retry_count}")
    print(f"  로그:\n{report.get('logs', '(없음)')}")

    if report.get("passed") is True:
        print("\n✅  계약 검사 통과.")
    else:
        # 계약 위반이면 frontend로 루프백해 재생성한다(backend와 대칭). 여기서
        # passed=False로 왔다는 건 재시도 상한(MAX_FRONTEND_RETRIES)까지 갔는데도
        # 못 고쳤다는 뜻이다 - 로그를 보고 사람이 확인해야 한다.
        print(
            f"\n🚫 재시도 {retry_count}회 후에도 계약 위반이 남았습니다. 로그를 보고 "
            "수동으로 확인해 주세요."
        )

    fe_target = os.getenv("FRONTEND_TARGET", "vanilla").lower()
    cmd = FRONTEND_RUN_INSTRUCTIONS.get(fe_target, "(알 수 없는 타깃)")
    print(f"\n👉 프론트 실행 ({fe_target}): cd {FRONTEND_OUT_DIR} && {cmd}")
    print("   단, 백엔드가 먼저 떠 있어야 데이터가 보인다 (위 실행 명령 참고).")


def main():
    # 기획문서 경로는 인자로 받는다: python main.py examples/shop_plan.md
    plan_path = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/todo_plan.md")
    plan = plan_path.read_text(encoding="utf-8")
    print(f"기획문서: {plan_path}\n")

    checkpointer = MemorySaver()
    app = build_pipeline(checkpointer=checkpointer)
    # thread_id를 기획문서마다 다르게 둔다 - 나중에 영속 checkpointer로 바꾸면
    # 문서별로 승인 대기 상태가 섞이지 않는다.
    config = {"configurable": {"thread_id": f"pipeline-{plan_path.stem}"}}

    result = app.invoke({"plan_doc": plan}, config=config)

    # review_gate에서 interrupt()가 걸리면 result에 "__interrupt__" 키가 담겨 온다.
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        decision = ask_human_approval(payload)
        result = app.invoke(Command(resume=decision), config=config)

    print_docs(result)

    print("=" * 60)
    if result.get("approved") is False:
        print("🚫 사람이 진행을 승인하지 않아 백엔드 코드 생성을 건너뛰었습니다.")
        print("   기획문서나 요구사항을 보강한 뒤 다시 실행해 보세요.")
        return

    print_verify_result(result)
    print_frontend_result(result)


if __name__ == "__main__":
    main()
