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
import stat
from pathlib import Path

from ..state import PipelineState

BACKEND_OUT_DIR = Path("generated/backend")

# LLM이 만들 수 없는 gradle wrapper(특히 바이너리 gradle-wrapper.jar)를 여기서 넣어준다.
# 이게 없으면 RUN_INSTRUCTIONS의 `./gradlew bootRun`이 안 돌아 사람이 시스템 gradle을
# 따로 깔아야 한다. gradle 버전은 build.gradle의 spring-boot 3.3.4와 호환이 검증된 8.14.
_GRADLE_WRAPPER_SRC = Path("assets/gradle-wrapper")
_GRADLE_WRAPPER_FILES = [
    "gradlew",
    "gradlew.bat",
    "gradle/wrapper/gradle-wrapper.jar",
    "gradle/wrapper/gradle-wrapper.properties",
]


def _copy_gradle_wrapper(out_dir: Path) -> None:
    """spring 생성물(build.gradle 있음)에 gradle wrapper를 복사한다.

    스택을 BACKEND_TARGET env로 보지 않고 build.gradle 존재로 판단한다 - write_backend는
    스택을 몰라야 하고(자기 산출물만 봄), gradle을 쓰는 건 build.gradle이 있다는 사실과
    같기 때문이다. 자산이 없으면 조용히 건너뛴다(없어도 파이프라인은 안 죽고, 사람이
    시스템 gradle로 돌리면 된다).
    """
    if not _GRADLE_WRAPPER_SRC.exists():
        return
    for rel in _GRADLE_WRAPPER_FILES:
        src, dst = _GRADLE_WRAPPER_SRC / rel, out_dir / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # gradlew는 Unix에서 실행권한이 있어야 `./gradlew`가 돈다 (Windows에선 무의미하나 무해).
    gradlew = out_dir / "gradlew"
    if gradlew.exists():
        gradlew.chmod(
            gradlew.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )


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

    # ERD의 결정적 DDL도 함께 저장한다. 백엔드가 이 스키마를 그대로 물어 DB를
    # 초기화하므로(스택 간 스키마 공유), 사람이 스키마를 눈으로 확인하는 근거도 된다.
    ddl = state.get("schema_ddl")
    if ddl:
        (BACKEND_OUT_DIR / "schema.sql").write_text(ddl, encoding="utf-8")

    # spring 생성물이면 gradle wrapper를 넣어준다 (LLM이 바이너리 jar를 못 만든다).
    if (BACKEND_OUT_DIR / "build.gradle").exists():
        _copy_gradle_wrapper(BACKEND_OUT_DIR)

    # 이전 시도의 리포트를 지운다 - 안 지우면 verify_backend가 낡은 파싱 실패
    # 리포트를 보고 검증을 건너뛴다.
    return {"verify_report": None}
