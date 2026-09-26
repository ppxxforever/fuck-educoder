"""ServerChan transport; no Educoder credentials enter this context."""
import hashlib
import re

from playwright.async_api import async_playwright, Error as PlaywrightError


class PushError(Exception):
    pass


def endpoint(key):
    if re.fullmatch(r'SCT[A-Za-z0-9_-]+', key):
        return 'Turbo', f'https://sctapi.ftqq.com/{key}.send'
    match = re.fullmatch(r'sctp([0-9]+)t[A-Za-z0-9_-]+', key)
    if match:
        return 'SC3', f'https://{match[1]}.push.ft07.com/send/{key}.send'
    raise PushError('SendKey 格式无效，请检查 .env；不会输出密钥。')


def receiver_id(key):
    endpoint(key)
    return hashlib.sha256(key.encode()).hexdigest()


def validate_response(status, data):
    if status != 200 or not isinstance(data, dict) or type(data.get('code')) is not int or data['code'] != 0:
        raise PushError('Server 酱未确认发送成功，请检查控制台的额度和推送日志。')


async def send(key, title, body):
    _, url = endpoint(key)
    if '\n' in title or len(title) > 100 or len(body.encode()) > 30000:
        raise PushError('通知内容超出本地长度限制，未发送。')
    try:
        async with async_playwright() as p:
            context = await p.request.new_context(timeout=20000)
            try:
                response = await context.post(url, form={'title': title, 'desp': body}, max_redirects=0)
                try:
                    data = await response.json()
                except (ValueError, UnicodeError):
                    raise PushError('Server 酱响应无法解析，送达状态未知。') from None
                validate_response(response.status, data)
            finally:
                await context.dispose()
    except PlaywrightError:
        # Playwright exception strings include the URL (and therefore the key).
        raise PushError('Server 酱网络请求失败，送达状态未知；将在限额内延迟重试。') from None
