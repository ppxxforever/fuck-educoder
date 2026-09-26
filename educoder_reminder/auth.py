"""Request signing matching Educoder's public web client (2026-09-24).

Source: https://www-cdn.educoder.net/umi.68b7af4f.js, setHeader/getKey.
These are public client constants, not the user's login credentials.
"""
import base64
import hashlib
import time
import uuid

_AK = 'WlRsa1pEVmlORE15TW1ZNVpqZGtPRE5rTURBNVpHVTVZbVpoTVRBd1l6TT0='
_SK = 'TW1VelpHRXdObUZsTWpaaVlUbG1OelpoTldRNFpETTFOVGMwTm1ZeVptVT0='


def signing_headers(method='GET', timestamp=None):
    timestamp = time.time_ns() // 1_000_000 if timestamp is None else timestamp
    ak, sk = (base64.b64decode(base64.b64decode(v)).decode('ascii') for v in (_AK, _SK))
    message = f'method={method.upper()}&ak={ak}&sk={sk}&time={timestamp}'
    signature = hashlib.md5(base64.b64encode(message.encode('ascii')), usedforsecurity=False).hexdigest()
    return {'X-EDU-Timestamp': str(timestamp), 'X-EDU-Signature': signature,
            'X-Request-Id': str(uuid.uuid4())}
