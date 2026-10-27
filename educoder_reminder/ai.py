"""OpenAI 兼容的 AI 对话客户端，用于题库缺答案时自动做题。

配置（.env）：
  AI_API_KEY        API 密钥（必填，留空则禁用自动做题）
  AI_BASE_URL       接口基地址，默认 https://api.deepseek.com
  AI_MODEL          主模型（选择题等），默认 deepseek-flash
  AI_CODE_MODEL     代码/绘图题专用模型，留空则回落到 AI_MODEL；
                    默认 deepseek-flash（如需更高通过率可换 deepseek-v4-pro，更贵）

说明：deepseek-chat / deepseek-reasoner 已于 2026-07-24 下线，请改用
      deepseek-flash（默认）或 deepseek-v4-pro；思考模式由 thinking 参数控制。
"""
import os
import re

import httpx

DEFAULT_BASE_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-flash'


class AIError(Exception):
    """AI 调用失败或配置缺失。"""


def load_ai_config():
    key = (os.environ.get('AI_API_KEY') or '').strip()
    base = (os.environ.get('AI_BASE_URL') or DEFAULT_BASE_URL).strip().rstrip('/')
    model = (os.environ.get('AI_MODEL') or DEFAULT_MODEL).strip()
    return key, base, model


def load_code_model():
    """代码/绘图题专用模型；未配置时返回 None（调用方回落到主模型）。"""
    return (os.environ.get('AI_CODE_MODEL') or '').strip() or None


_REASONING_HINTS = ('reasoner', 'o1-', 'o3-', '-o1', '-o3', 'thinking', 'r1-')


def _is_reasoning_model(model):
    """旧式推理模型名（deepseek-reasoner / o1 / o3 等）不支持 temperature/top_p。"""
    m = (model or '').lower()
    return any(h in m for h in _REASONING_HINTS)


def _is_deepseek(base):
    """只有 DeepSeek 官方接口才支持 thinking/reasoning_effort 参数。"""
    return 'deepseek' in (base or '').lower()


def ai_configured() -> bool:
    key, _, _ = load_ai_config()
    return bool(key)


async def ai_chat(system, user, *, temperature=0.2, max_tokens=None, model=None,
                  thinking=None, reasoning_effort=None) -> str:
    """调用 OpenAI 兼容 chat/completions，返回 assistant 文本。

    model 为 None 时使用主模型（AI_MODEL）；代码题可传入 AI_CODE_MODEL。

    thinking：True/False=开启/关闭思考模式（仅 DeepSeek 接口生效，其它 OpenAI 兼容
    服务忽略该参数走温度采样）；reasoning_effort 可选 low/high/max，仅在思考模式下
    生效。思考模式下 temperature 无效，会自动省略。
    """
    key, base, default_model = load_ai_config()
    model = model or default_model
    if not key:
        raise AIError('未配置 AI_API_KEY，无法自动做题。')
    url = f'{base}/chat/completions'
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'stream': False,
    }
    if thinking is not None and _is_deepseek(base):
        payload['thinking'] = {'type': 'enabled' if thinking else 'disabled'}
        if thinking and reasoning_effort:
            payload['reasoning_effort'] = reasoning_effort
        if not thinking:
            payload['temperature'] = temperature
    elif not _is_reasoning_model(model):
        payload['temperature'] = temperature
    if max_tokens:
        payload['max_tokens'] = max_tokens
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise AIError(f'AI 接口请求失败：{exc}') from None
    if resp.status_code != 200:
        raise AIError(f'AI 接口返回 HTTP {resp.status_code}：{resp.text[:300]}')
    try:
        data = resp.json()
        return data['choices'][0]['message']['content']
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIError(f'AI 接口响应结构异常：{exc}') from None


def extract_json_block(text):
    """从 AI 回复里抽出 JSON（容忍 markdown 代码围栏与前后说明文字）。"""
    text = (text or '').strip()
    m = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
    if m:
        text = m.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def strip_code_fence(text):
    """从 AI 回复里抽出代码（容忍 markdown 代码围栏）。"""
    text = (text or '').strip()
    m = re.search(r'```[^\n]*\n(.*?)```', text, re.S)
    if m:
        return m.group(1).rstrip()
    return text
