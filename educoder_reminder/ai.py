"""OpenAI 兼容的 AI 对话客户端，用于题库缺答案时自动做题。

配置（.env）：
  AI_API_KEY   API 密钥（必填，留空则禁用自动做题）
  AI_BASE_URL  接口基地址，默认 https://api.deepseek.com
  AI_MODEL     模型名，默认 deepseek-chat
"""
import os
import re

import httpx

DEFAULT_BASE_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-chat'


class AIError(Exception):
    """AI 调用失败或配置缺失。"""


def load_ai_config():
    key = (os.environ.get('AI_API_KEY') or '').strip()
    base = (os.environ.get('AI_BASE_URL') or DEFAULT_BASE_URL).strip().rstrip('/')
    model = (os.environ.get('AI_MODEL') or DEFAULT_MODEL).strip()
    return key, base, model


def ai_configured() -> bool:
    key, _, _ = load_ai_config()
    return bool(key)


async def ai_chat(system, user, *, temperature=0.2, max_tokens=None) -> str:
    """调用 OpenAI 兼容 chat/completions，返回 assistant 文本。"""
    key, base, model = load_ai_config()
    if not key:
        raise AIError('未配置 AI_API_KEY，无法自动做题。')
    url = f'{base}/chat/completions'
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'temperature': temperature,
        'stream': False,
    }
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
