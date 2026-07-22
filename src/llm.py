"""
LLM 호출 헬퍼 (OpenRouter 경유) + JSON 파싱 유틸.
OpenRouter는 OpenAI 호환이라 OpenAI SDK를 그대로 쓰고 base_url만 바꾼다.
모델을 바꾸려면 .env의 PIPELINE_MODEL 하나만 바꾸면 됨.

주의: 리즈닝(사고) 모델(예: deepseek-v4-flash)은 기본적으로 '생각 과정'을
content에 섞어서 뱉을 수 있다. extra_body의 reasoning.exclude=True로 꺼서
최종 답만 받도록 강제한다. (OpenRouter 통합 reasoning 파라미터)
"""

import os
import json

from openai import OpenAI

MODEL = os.getenv("PIPELINE_MODEL", "~anthropic/claude-sonnet-latest")

_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


def call_llm(system: str, user: str, max_tokens: int = 8192) -> str:
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
            "reasoning": {"effort": "low", "exclude": True},
        },
    )
    return resp.choices[0].message.content


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
