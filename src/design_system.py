"""
디자인 토큰 로더.

파이프라인에 없던 축을 하나 채운다:
  기획문서    → 뭘 하는지 (동작)
  api_spec    → 뭘 부르는지 (계약)
  디자인 토큰  → 어떻게 생겼는지 (외형)   ← 이 파일이 담당

노드가 아니라 헬퍼인 이유: 그래프의 단계가 아니라 프론트 생성 노드들이 공유하는
입력이기 때문이다. vanilla와 react가 같은 로더를 써야 FRONTEND_TARGET을 바꿔도
디자인이 안 바뀐다.

Claude Design(claude.ai/design)과는 파일로만 이어진다. DesignSync는 Claude Code
안에서 사람의 로그인으로 도는 도구라 python이 못 부른다. 사람이 가끔 동기화해서
design/design_system.md를 갱신하고, 파이프라인은 그 파일만 본다 - schemathesis를
파이프라인 밖에 둔 것과 같은 판단이다.
"""

import re
from pathlib import Path

DESIGN_SYSTEM_PATH = Path("design/design_system.md")


def load_design_system() -> str:
    """토큰 문서를 읽는다. 없으면 빈 문자열 - 디자인 축 없이도 파이프라인은 돌아야 한다."""
    if not DESIGN_SYSTEM_PATH.exists():
        return ""
    return DESIGN_SYSTEM_PATH.read_text(encoding="utf-8")


def design_prompt_block() -> str:
    """프론트 생성 노드의 user 프롬프트에 붙일 조각."""
    tokens = load_design_system()
    if not tokens:
        return ""
    return (
        "[디자인 토큰 - 외형의 근거다]\n"
        f"{tokens}\n\n"
        "위 토큰을 지켜서 스타일을 작성한다. 색·크기·간격을 임의로 지어내지 말고 "
        "토큰에 있는 값을 쓴다. 토큰에 없는 값이 필요하면 가장 가까운 토큰 값을 쓴다.\n"
        "단, 화면 구성과 요소 배치는 화면설계서를 따른다 - 토큰은 톤앤매너만 정한다.\n\n"
    )


def token_colors() -> list[str]:
    """토큰 문서에서 색상 hex를 뽑는다 (소문자, 중복 제거).

    verify_frontend가 '이 색들이 생성물에 실제로 쓰였나'를 결정적으로 검사하는 데 쓴다.
    색을 고른 이유는 토큰 중에 문자열로 그대로 코드에 박히는 값이라 검사가 확실하기
    때문이다. 간격(12px)이나 굵기(600) 같은 값은 다른 이유로도 우연히 등장할 수 있어
    검사 신호가 약하다.
    """
    return sorted({m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", load_design_system())})


if __name__ == "__main__":
    # .env를 먼저 읽을 필요 없음 (이 모듈은 llm.py를 안 거친다):
    #   python -m src.design_system
    colors = token_colors()
    print(f"토큰 문서: {DESIGN_SYSTEM_PATH} ({'있음' if load_design_system() else '없음'})")
    print(f"색상 토큰 {len(colors)}개: {colors}")
    assert design_prompt_block().startswith("[디자인 토큰") or not load_design_system()
