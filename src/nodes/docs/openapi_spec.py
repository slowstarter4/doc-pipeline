"""
노드5b: API 명세(JSON) → 정식 OpenAPI 3.0 문서 (결정적 변환, LLM 미사용)

우리 파이프라인의 api_spec은 {"endpoints": [...]} 형태의 단순화된 내부 스키마다.
schemathesis 같은 표준 도구로 자동 계약 검사를 하려면 정식 OpenAPI 3.0 문서가
필요하다.

이 변환은 규칙 기반 파이썬 코드로만 이루어진다 (LLM 호출 없음). 같은 api_spec을
넣으면 항상 같은 OpenAPI 문서가 나와야 - 계약 검사 도구 자체가 비결정적이면
검사 결과를 신뢰할 수 없기 때문이다. 지금까지의 노드들과 달리 이 노드는
call_llm을 쓰지 않는다.
"""

import re

from ...state import PipelineState

_TYPE_MAP = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
}

# path parameter 전용 타입 매핑. body 필드의 "number"는 실수(가격 등)일 수 있지만,
# path parameter로 쓰이는 "number" 필드는 거의 항상 리소스 식별자(id)라서
# 정수로 취급하는 게 실제 백엔드 구현(id: int 등)과 더 잘 맞는다. 이렇게 안 하면
# schemathesis가 6.49e-205 같은 실수를 넣어보다 서버가 정수 파싱에 실패해
# '명세는 통과인데 서버가 거부'하는 거짓 실패가 난다.
_PATH_PARAM_TYPE_MAP = {
    **_TYPE_MAP,
    "number": {"type": "integer"},
}


def _schema_for(value, required_map: dict | None = None) -> dict:
    """{"필드명": "타입"} 또는 중첩 구조를 OpenAPI 스키마로 변환한다.
    required_map이 주어지면 해당 필드의 required 배열도 채운다.
    """
    if isinstance(value, list):
        item_schema = (
            _schema_for(value[0], required_map) if value else {"type": "object"}
        )
        return {"type": "array", "items": item_schema}

    if isinstance(value, dict):
        properties = {}
        required = []
        for name, sub in value.items():
            if isinstance(sub, (list, dict)):
                properties[name] = _schema_for(sub, required_map)
            else:
                properties[name] = _TYPE_MAP.get(sub, {"type": "string"})
            if required_map and required_map.get(name):
                required.append(name)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    return _TYPE_MAP.get(value, {"type": "string"})


def _build_required_map(data_model: dict) -> dict:
    """ERD의 엔티티들에서 '필드명 -> required 여부' 맵을 만든다.

    한계: 엔티티가 여러 개면 필드명이 겹칠 수 있는데, 지금은 이름이 같으면
    하나라도 required=true면 required로 취급하는 단순한 전역 네임스페이스를
    쓴다. 지금 범위(단일 엔티티 Todo 앱)에서는 충분하지만, 엔티티 간 필드명
    충돌이 흔해지는 프로젝트에서는 엔티티별로 네임스페이스를 분리하는 개선이
    필요하다.
    """
    required_map: dict = {}
    for entity in data_model.get("entities", []):
        for field in entity.get("fields", []):
            name = field.get("name")
            if name is None:
                continue
            if field.get("required"):
                required_map[name] = True
            else:
                required_map.setdefault(name, False)
    return required_map


def _build_type_map(data_model: dict) -> dict:
    """ERD의 엔티티들에서 '필드명 -> 타입 문자열' 맵을 만든다.

    path parameter(예: {id})의 실제 타입을 알아내는 데 쓴다. 이게 없으면
    path parameter를 전부 무조건 string으로 문서화하게 되는데, 실제 백엔드가
    id를 정수로 파싱하는 경우(FastAPI의 `id: int` 등) schemathesis가 명세를
    믿고 넣은 임의의 문자열이 서버에서 파싱 실패하는 '명세가 구현보다 느슨한'
    거짓 실패가 생긴다.

    required_map과 같은 한계(엔티티 간 필드명 충돌)를 공유한다.
    """
    type_map: dict = {}
    for entity in data_model.get("entities", []):
        for field in entity.get("fields", []):
            name = field.get("name")
            if name is None:
                continue
            type_map.setdefault(name, field.get("type"))
    return type_map


_ERROR_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
}


def openapi_spec_node(state: PipelineState) -> dict:
    """API 명세를 정식 OpenAPI 3.0으로 변환한다.

    성공 상태 코드와 에러 상태 코드는 REST 관례를 규칙으로 인코딩해서 채운다
    (LLM에 묻지 않는다 - 결정적이어야 하므로):
    - POST는 관례상 201(Created), 그 외(GET/PUT/DELETE)는 200.
    - path에 {id} 같은 파라미터가 있으면 404(Not Found)를 문서화한다
      (존재하지 않는 리소스를 요청할 수 있으므로).
    - request body가 있거나 path parameter가 있으면 400(Bad Request)을 문서화한다
      (둘 다 유효성 검증에 실패할 수 있으므로).
    이렇게 해야 schemathesis가 "명세에 없는 상태 코드"로 잘못 플래그하지 않고,
    실제로 서버가 그 코드를 반환하지 않으면(예: 유효성 검증 없이 다 받아버리면)
    그건 백엔드 노드 쪽 문제로 정확히 짚어낼 수 있다.
    """
    endpoints = state["api_spec"].get("endpoints", [])
    data_model = state.get("data_model", {})
    required_map = _build_required_map(data_model)
    type_map = _build_type_map(data_model)
    paths: dict = {}

    for ep in endpoints:
        method = ep["method"].lower()
        path = ep["path"]
        paths.setdefault(path, {})

        success_code = "201" if method == "post" else "200"
        success_desc = "생성됨" if success_code == "201" else "성공"

        responses = {
            success_code: {
                "description": success_desc,
                "content": {
                    "application/json": {
                        "schema": _schema_for(ep.get("response", {}), required_map)
                    }
                },
            }
        }

        has_path_param = bool(re.search(r"\{(\w+)\}", path))
        if has_path_param:
            responses["404"] = {
                "description": "리소스를 찾을 수 없음",
                "content": {"application/json": {"schema": _ERROR_SCHEMA}},
            }

        if ep.get("request") or has_path_param:
            responses["400"] = {
                "description": "잘못된 요청 (유효성 검증 실패)",
                "content": {"application/json": {"schema": _ERROR_SCHEMA}},
            }

        operation = {"summary": ep.get("summary", ""), "responses": responses}

        # 업무 규칙(rules)은 OpenAPI에 대응하는 자리가 없어서 description으로 옮긴다.
        # 계약의 일부인데 openapi.json에만 빠져 있으면, 이 문서를 보고 작업하는
        # 사람이나 도구가 제약을 모른 채 구현하게 된다.
        rules = ep.get("rules") or []
        if rules:
            operation["description"] = "업무 규칙:\n" + "\n".join(
                f"- {r}" for r in rules
            )

        # path parameter 자동 추출 (예: /todos/{id} -> id)
        # ERD에 해당 필드가 있으면 그 타입을 쓰고, 없으면 string으로 fallback한다.
        for match in re.findall(r"\{(\w+)\}", path):
            param_schema = _PATH_PARAM_TYPE_MAP.get(
                type_map.get(match), {"type": "string"}
            )
            operation.setdefault("parameters", []).append(
                {
                    "name": match,
                    "in": "path",
                    "required": True,
                    "schema": param_schema,
                }
            )

        if ep.get("request"):
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": _schema_for(ep["request"], required_map)
                    }
                },
            }

        paths[path][method] = operation

    openapi_doc = {
        "openapi": "3.0.3",
        "info": {"title": "Generated API (doc-pipeline)", "version": "1.0.0"},
        "paths": paths,
    }
    return {"openapi_spec": openapi_doc}
