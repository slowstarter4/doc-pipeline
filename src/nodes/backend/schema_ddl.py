"""
노드3c: 데이터 모델(ERD) → sqlite DDL (결정적 변환, LLM 미사용)

`openapi_spec`이 api_spec을 정식 OpenAPI로 규칙 변환하듯, 이 노드는 ERD(data_model
dict)를 sqlite `CREATE TABLE` 문으로 규칙 변환한다. 목적: 스택마다 백엔드 LLM이
컬럼·타입을 제각각 해석하던 걸 막고, 4스택이 **같은 스키마**를 공유하게 하는 것.
백엔드 생성 프롬프트가 이 DDL을 그대로 물어서 `CREATE TABLE`을 지어내지 않게 한다.

LLM을 안 쓴다 - 같은 ERD면 항상 같은 DDL이어야 스택 간 스키마가 갈리지 않는다.

타입 매핑 근거 (sqlite 타입 어피니티):
- string → TEXT, date → TEXT (ISO 문자열)
- boolean → INTEGER (0/1. fastapi 구현도 boolean을 0/1로 저장한다)
- number → INTEGER. sqlite의 INTEGER 어피니티는 실수를 정수로 강제 변환하지 않고
  그대로 저장하므로(어피니티는 변환 '시도'지 강제가 아님), 가격 같은 실수도 손실
  없이 들어간다. 대부분의 number 필드는 개수·수량·식별자라 INTEGER가 더 자연스럽다.

한계: data_model 스키마에는 엔티티 간 관계(외래키) 정보가 없다. 그래서 memberId
같은 필드는 INTEGER 컬럼으로만 만들고 FOREIGN KEY 제약은 걸지 않는다. 관계 규칙
(중복대출 금지 등)은 이미 api_spec의 rules로 앱 레벨에서 강제되고 검증됐다.
"""

import os

from ...state import PipelineState

_DDL_TYPE_MAP = {
    "string": "TEXT",
    "number": "INTEGER",
    "boolean": "INTEGER",
    "date": "TEXT",
}

# 방언 분기는 PK 줄 하나뿐이다. 타입맵(boolean→INTEGER 0/1, date→TEXT)은 두 방언이
# 공유한다 - postgres 네이티브 BOOLEAN/DATE로 바꾸면 4스택 앱 코드(0/1 변환, ISO
# 문자열 저장)를 전부 고쳐야 해서 "4스택 같은 스키마 공유" 철학이 깨진다. postgres도
# INTEGER 컬럼에 0/1, TEXT 컬럼에 ISO 문자열이 그대로 들어가므로 앱 코드는 안 바뀐다.
# 실제로 방언이 갈리는 건 자동증가 PK뿐: sqlite는 AUTOINCREMENT, postgres는 SERIAL.
_DIALECT_PK = {
    "sqlite": "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "postgres": "id SERIAL PRIMARY KEY",
}


def _dialect() -> str:
    """DB_TARGET env로 방언 선택 (BACKEND_TARGET 패턴). 기본 sqlite."""
    return os.getenv("DB_TARGET", "sqlite").lower()


def _table_ddl(entity: dict, pk: str) -> str:
    """엔티티 하나를 CREATE TABLE 문자열로. id는 ERD에 없어도 DB가 매기도록 자동 추가."""
    name = entity.get("name")
    if not name:
        return ""

    lines = [f"  {pk}"]
    for field in entity.get("fields", []):
        fname = field.get("name")
        if not fname or fname == "id":
            continue  # id는 위에서 이미 넣었다. ERD가 id를 또 선언해도 무시.
        sql_type = _DDL_TYPE_MAP.get(field.get("type"), "TEXT")
        null = " NOT NULL" if field.get("required") else ""
        lines.append(f"  {fname} {sql_type}{null}")

    body = ",\n".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {name} (\n{body}\n);"


def schema_ddl_node(state: PipelineState) -> dict:
    data_model = state.get("data_model") or {}
    pk = _DIALECT_PK.get(_dialect(), _DIALECT_PK["sqlite"])
    tables = [
        ddl
        for entity in data_model.get("entities", [])
        if (ddl := _table_ddl(entity, pk))
    ]
    return {"schema_ddl": "\n\n".join(tables)}


if __name__ == "__main__":
    # 도서 대출 3엔티티로 자기 점검. required→NOT NULL, id 자동 추가, 타입 매핑 확인.
    model = {
        "entities": [
            {
                "name": "book",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "isbn", "type": "string", "required": True},
                    {"name": "publishedYear", "type": "number", "required": False},
                    {"name": "isAvailable", "type": "boolean", "required": True},
                ],
            },
            {
                "name": "loan",
                "fields": [
                    {"name": "memberId", "type": "number", "required": True},
                    {"name": "bookId", "type": "number", "required": True},
                    {"name": "dueDate", "type": "date", "required": True},
                    {"name": "id", "type": "number", "required": False},  # 무시돼야
                ],
            },
        ]
    }
    ddl = schema_ddl_node({"data_model": model})["schema_ddl"]  # 기본 sqlite
    print(ddl)

    assert "CREATE TABLE IF NOT EXISTS book (" in ddl
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
    assert "title TEXT NOT NULL" in ddl
    assert "publishedYear INTEGER" in ddl and "publishedYear INTEGER NOT NULL" not in ddl
    assert "isAvailable INTEGER NOT NULL" in ddl
    assert "memberId INTEGER NOT NULL" in ddl
    assert "dueDate TEXT NOT NULL" in ddl
    # ERD가 id를 또 선언해도 컬럼이 중복 생기면 안 된다 (loan에 id INTEGER 줄 없어야).
    assert ddl.count("id INTEGER PRIMARY KEY AUTOINCREMENT") == 2  # book, loan 각 1개
    assert "\n  id INTEGER,\n" not in ddl and "  id INTEGER\n" not in ddl
    # 빈 입력은 빈 문자열.
    assert schema_ddl_node({})["schema_ddl"] == ""
    assert schema_ddl_node({"data_model": {"entities": []}})["schema_ddl"] == ""

    # postgres 방언: PK만 SERIAL로 갈리고 타입맵(INTEGER 0/1, TEXT)은 그대로여야 한다.
    os.environ["DB_TARGET"] = "postgres"
    pg = schema_ddl_node({"data_model": model})["schema_ddl"]
    print("\n" + pg)
    assert pg.count("id SERIAL PRIMARY KEY") == 2
    assert "AUTOINCREMENT" not in pg
    assert "isAvailable INTEGER NOT NULL" in pg  # boolean 여전히 INTEGER (0/1 앱코드 유지)
    assert "dueDate TEXT NOT NULL" in pg          # date 여전히 TEXT (ISO 문자열 유지)
    del os.environ["DB_TARGET"]
    print("\nschema_ddl self-check 통과 (sqlite + postgres)")
