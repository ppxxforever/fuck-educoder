import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dotenv import dotenv_values

from educoder_reminder import login
from educoder_reminder.client import Client, load_settings
from educoder_reminder.errors import AuthenticationExpired, CollectionError


def response(data, status=200):
    result = AsyncMock()
    result.status = status
    result.json.return_value = data
    return result


class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_discovered_from_school_endpoint(self):
        context = AsyncMock()
        context.get.return_value = response({'login': 'ppjcesyh9'})
        self.assertEqual(await login.verify_identity(context), 'ppjcesyh9')
        self.assertEqual(context.get.call_args.kwargs['params'], {'school': 1})

    def test_classroom_url_no_longer_required(self):
        with patch.dict(os.environ, {'EDUCODER_LOGIN_ACCOUNT': 'account', 'EDUCODER_LOGIN_PASSWORD': 'password'}, clear=True), \
                patch('educoder_reminder.client.load_dotenv'):
            username, headers = load_settings()
        self.assertIsNone(username)
        self.assertEqual(headers['Referer'], 'https://www.educoder.net/')

    async def test_mismatch_forces_password_login_and_updates_username(self):
        context = AsyncMock()
        context.get.return_value = response({'login': 'stale_cookie_account'})
        replacement = AsyncMock()
        replacement.get.return_value = response({'login': 'ppjcesyh9'})
        client = Client(context, 'old_config', object(), {})
        with patch('educoder_reminder.client.recover_session', return_value=replacement) as recover:
            await client.ensure_authenticated()
        self.assertTrue(recover.call_args.kwargs['force_login'])
        self.assertEqual(client.username, 'ppjcesyh9')

    async def test_mid_batch_account_change_never_replays_old_course_request(self):
        context = AsyncMock()
        context.get.return_value = response({'status': 401})
        replacement = AsyncMock()
        replacement.get.return_value = response({'login': 'new_account'})
        client = Client(context, 'old_account', object(), {})
        with patch('educoder_reminder.client.recover_session', return_value=replacement):
            with self.assertRaises(CollectionError):
                await client.get('/api/courses/old_course/homework_commons.json', {})
        self.assertEqual(replacement.get.await_count, 1)
        self.assertEqual(replacement.get.call_args.args[0], login.IDENTITY_URL)

    async def test_anonymous_200_response_is_expired(self):
        context = AsyncMock()
        context.get.return_value = response({'login': ''})
        with self.assertRaises(AuthenticationExpired):
            await login.verify_identity(context, 'me')

    async def test_identity_mismatch_not_treated_as_expiration(self):
        context = AsyncMock()
        context.get.return_value = response({'login': 'someone_else'})
        with self.assertRaises(CollectionError) as caught:
            await login.verify_identity(context, 'me')
        self.assertNotIsInstance(caught.exception, AuthenticationExpired)

    async def test_signature_error_does_not_trigger_password_login(self):
        context = AsyncMock()
        context.get.return_value = response({'status': -102})
        client = Client(context, 'me')
        client.recover = AsyncMock()
        with self.assertRaises(CollectionError):
            await client.ensure_authenticated()
        client.recover.assert_not_awaited()

    async def test_healthy_session_avoids_browser(self):
        context = AsyncMock()
        context.get.return_value = response({'login': 'me'})
        client = Client(context, 'me')
        client.recover = AsyncMock()
        await client.ensure_authenticated()
        client.recover.assert_not_awaited()

    async def test_auth_401_retries_original_request_once(self):
        context = AsyncMock()
        context.get.return_value = response({'status': 401})
        replacement = AsyncMock()
        replacement.get.side_effect = [response({'login': 'me'}), response({'count': 1, 'courses': []})]
        client = Client(context, 'me', object(), {})
        with patch('educoder_reminder.client.recover_session', return_value=replacement) as recover:
            self.assertEqual(await client.get('/api/users/me/courses.json', {'page': 2}), {'count': 1, 'courses': []})
            recover.assert_awaited_once()
            self.assertEqual(replacement.get.call_args.kwargs['params'], {'page': 2, 'zzud': 'me'})
            replacement.get.side_effect = None
            replacement.get.return_value = response({'status': 401})
            with self.assertRaises(AuthenticationExpired):
                await client.get('/api/users/me/courses.json', {})
            recover.assert_awaited_once()

    async def test_permission_error_does_not_login_with_valid_identity(self):
        context = AsyncMock()
        context.get.side_effect = [response({}, 403), response({'login': 'me'})]
        client = Client(context, 'me')
        client.recover = AsyncMock()
        with self.assertRaises(CollectionError):
            await client.get('/api/courses/joined/homework_commons.json', {})
        client.recover.assert_not_awaited()

    def test_credentials_saved_atomically_and_password_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            path = Path(directory) / '.env'
            path.write_text("EDUCODER_LOGIN_PASSWORD='test${literal}'\nSERVERCHAN_SENDKEY='not-a-real-key'\n")
            with patch.object(login, 'ENV_PATH', path):
                login.persist_credentials('newtoken', 'session=newtoken; trust=yes', 'ppjcesyh9')
            values = dotenv_values(path, interpolate=False)
            self.assertEqual(values['EDUCODER_LOGIN_PASSWORD'], 'test${literal}')
            self.assertEqual(values['EDUCODER_TOKEN'], 'newtoken')
            self.assertEqual(values['EDUCODER_CLASSROOMS_URL'], 'https://www.educoder.net/users/ppjcesyh9/classrooms')
            self.assertEqual(values['EDUCODER_COOKIE'], 'session=newtoken; trust=yes')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(directory).glob('.env-login-*')), [])

    def test_failed_replace_preserves_old_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            original = "EDUCODER_TOKEN='oldtoken'\nEDUCODER_COOKIE='oldcookie'\n"
            path.write_text(original)
            with patch.object(login, 'ENV_PATH', path), patch.object(login.os, 'replace', side_effect=OSError):
                with self.assertRaises(CollectionError):
                    login.persist_credentials('new', 'newcookie')
            self.assertEqual(path.read_text(), original)

    def test_cooldown_survives_repeated_calls_and_daily_limit(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(login, 'STATE_DIR', Path(directory)):
            login.reserve_attempt('me', now=100000)
            with self.assertRaises(CollectionError):
                login.reserve_attempt('me', now=100001)
            login.reserve_attempt('me', now=101800)
            login.reserve_attempt('me', now=103600)
            with self.assertRaises(CollectionError):
                login.reserve_attempt('me', now=105400)
            login.reserve_attempt('me', now=186401)

    async def test_other_process_refreshed_credentials_reused(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            path = Path(directory) / '.env'
            path.write_text("EDUCODER_TOKEN='already-new'\nEDUCODER_COOKIE='session=already-new'\n")
            context = AsyncMock()
            playwright = AsyncMock()
            with patch.object(login, 'STATE_DIR', Path(directory)), patch.object(login, 'ENV_PATH', path), \
                    patch.object(login, 'checked_context', return_value=context):
                self.assertIs(await login.recover_session(playwright, 'me', {}), context)
                playwright.chromium.launch.assert_not_awaited()
