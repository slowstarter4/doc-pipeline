"""
LLM 호출 헬퍼 (OpenRouter 경유) + JSON 파싱 유틸.
OpenRouter는 OpenAI 호환이라 OpenAI SDK를 그대로 쓰고 base_url만 바꾼다.
모델을 바꾸려면 .env의 PIPELINE_MODEL 하나만 바꾸면 됨.

주의: 리즈닝(사고) 모델(예: deepseek-v4-flash)은 기본적으로 '생각 과정'을
content에 섞어서 뱉을 수 있다. extra_body의 reasoning.exclude=True로 꺼서
최종 답만 받도록 강제한다. (OpenRouter 통합 reasoning 파라미터)

응답 캐시: 프롬프트(모델+system+user+max_tokens)가 같으면 디스크 캐시에서
바로 돌려주고 API를 안 부른다. 파이프라인은 backend 노드 하나만 바꿔가며
전체를 여러 번 재실행하는데, 그때마다 문서 단계(requirements~openapi)를 새로
생성하던 게 토큰의 대부분이었다. 문서 노드는 plan_doc이 같으면 프롬프트도 같아
전부 캐시 히트하고, 프롬프트를 고친 backend 노드만 미스가 나 재생성된다.
캐시가 LLM 비결정성을 고정하므로 디버깅 재현성도 좋아진다. LLM_CACHE=0으로 끈다.
"""

import os
import json
import hashlib
from pathlib import Path

from openai import OpenAI

MODEL = os.getenv("PIPELINE_MODEL", "~anthropic/claude-sonnet-latest")

_CACHE_DIR = Path(".cache/llm")
_CACHE_ENABLED = os.getenv("LLM_CACHE", "1") != "0"

_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# reasoning 설정을 캐시 키에 포함시켜야, 나중에 이 값을 바꿨을 때 낡은 응답을
# 재사용하지 않는다. call_llm과 _cache_key가 같은 dict를 봐야 하므로 상수로 뺀다.
_REASONING = {"effort": "low", "exclude": True}


def _cache_key(system: str, user: str, max_tokens: int) -> str:
    payload = json.dumps(
        [MODEL, system, user, max_tokens, _REASONING],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def call_llm(system: str, user: str, max_tokens: int = 8192) -> str:
    cache_file = None
    if _CACHE_ENABLED:
        cache_file = _CACHE_DIR / f"{_cache_key(system, user, max_tokens)}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

    resp = _client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        extra_body={
            # 리즈닝 모델의 사고 과정이 content에 섞이지 않게 한다.
            # exclude=True: 내부적으로 생각은 하되 응답엔 안 담음.
            "reasoning": _REASONING,
        },
    )
    content = resp.choices[0].message.content

    # content가 None(응답 실패)이면 캐시하지 않는다 - 실패를 캐시하면 다음 실행도
    # API를 안 부르고 계속 None을 돌려줘 조용히 고장난다.
    if cache_file is not None and content:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(content, encoding="utf-8")

    return content


def strip_json(text: str) -> dict:
    """```json 펜스가 붙어 나와도, 앞뒤에 잡소리가 붙어 나와도 최대한 안전하게 파싱한다."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    else:
        # 펜스가 없는데 앞에 잡소리가 붙어 나온 경우, 첫 '{'부터 마지막 '}'까지만 취한다.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


if __name__ == "__main__":
    # 캐시 키: 같은 입력이면 안정적으로 같은 키, 어느 한 인자라도 다르면 다른 키여야
    # 한다. 키가 흔들리면 히트가 안 나고, 인자 차이를 무시하면 낡은 응답을 재사용한다.
    k1 = _cache_key("sys", "user", 8192)
    assert k1 == _cache_key("sys", "user", 8192)  # 결정적
    assert k1 != _cache_key("sys2", "user", 8192)  # system 다르면 다름
    assert k1 != _cache_key("sys", "user2", 8192)  # user 다르면 다름
    assert k1 != _cache_key("sys", "user", 4096)  # max_tokens 다르면 다름
    assert len(k1) == 64 and all(c in "0123456789abcdef" for c in k1)  # sha256 hex

    # strip_json: 펜스·잡소리가 붙어도 파싱된다.
    assert strip_json('{"a": 1}') == {"a": 1}
    assert strip_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert strip_json('앞잡소리 {"a": 1} 뒷잡소리') == {"a": 1}
    print("llm self-check 통과")
