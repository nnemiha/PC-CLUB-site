"""Run in the API container: python -m unittest test_admin -v"""
import unittest
from unittest.mock import AsyncMock
from aiohttp import web, CookieJar
from aiohttp.test_utils import TestClient, TestServer
from admin import install, password_hash

class AdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = AsyncMock()
        self.app = web.Application()
        self.app['pool'] = self.pool
        install(self.app)
        self.client = TestClient(TestServer(self.app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_bookings_require_session(self):
        response = await self.client.get('/api/admin/bookings')
        self.assertEqual(response.status, 401)
        self.pool.fetch.assert_not_called()

    async def test_login_rejects_cross_site_form(self):
        response = await self.client.post('/api/admin/login', data={'login':'admin','password':'test'})
        self.assertEqual(response.status, 403)
        self.pool.fetchrow.assert_not_called()

    async def test_expired_session_denied(self):
        self.client.session.cookie_jar.update_cookies({'marinovani_admin':'invalid-token'})
        self.pool.fetchrow.return_value = None
        response = await self.client.get('/api/admin/bookings')
        self.assertEqual(response.status, 401)
        self.pool.fetch.assert_not_called()

    async def test_status_change_requires_csrf(self):
        self.client.session.cookie_jar.update_cookies({'marinovani_admin':'test-token'})
        self.pool.fetchrow.return_value = {'csrf':'expected','token_hash':'hash'}
        response = await self.client.patch('/api/admin/bookings/1', json={'status':'confirmed'},
            headers={'X-Admin-Request':'1'})
        self.assertEqual(response.status, 403)
        self.pool.fetchval.assert_not_called()

    async def test_status_change_updates_database(self):
        self.client.session.cookie_jar.update_cookies({'marinovani_admin':'test-token'})
        self.pool.fetchrow.return_value = {'csrf':'expected','token_hash':'hash'}
        self.pool.fetchval.return_value = 7
        response = await self.client.patch('/api/admin/bookings/7', json={'status':'confirmed'},
            headers={'X-Admin-Request':'1','X-CSRF-Token':'expected'})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.pool.fetchval.call_args.args[1:], ('confirmed',7))

    def test_password_salt_changes_hash(self):
        self.assertNotEqual(password_hash('example-password','00'*16), password_hash('example-password','11'*16))

if __name__ == '__main__':
    unittest.main()
