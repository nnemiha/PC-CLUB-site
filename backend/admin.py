"""Owner registration, database sessions, and protected booking management."""
import asyncio
from collections import deque
import hashlib
import hmac
import os
import re
import secrets
import time
from aiohttp import web

COOKIE = 'marinovani_admin'
STATES = {'new', 'confirmed', 'cancelled'}

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

async def initialize(pool):
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute('SELECT pg_advisory_xact_lock(8100)')
            await c.execute('''
                ALTER TABLE bookings ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';
                CREATE TABLE IF NOT EXISTS admin_accounts (
                    id INTEGER PRIMARY KEY CHECK(id=1), login TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES admin_accounts(id),
                    csrf TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL
                );
            ''')

def error(message, status=400):
    return web.json_response({'error': message}, status=status)

async def body(request):
    # A custom header plus JSON forbids cross-origin HTML form submissions.
    # No CORS endpoints are enabled on this application.
    if request.headers.get('X-Admin-Request') != '1' or request.content_type != 'application/json':
        raise web.HTTPForbidden()
    try:
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text='Invalid JSON')

async def session(request, write=False):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 128:
        raise web.HTTPUnauthorized()
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = await request.app['pool'].fetchrow('''SELECT s.*,a.login FROM admin_sessions s
        JOIN admin_accounts a ON a.id=s.admin_id
        WHERE token_hash=$1 AND expires_at>now()''', digest)
    if not row:
        raise web.HTTPUnauthorized()
    if write and not hmac.compare_digest(request.headers.get('X-CSRF-Token', '').encode(), row['csrf'].encode()):
        raise web.HTTPForbidden()
    return row

async def issue_session(request):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    await request.app['pool'].execute('DELETE FROM admin_sessions WHERE expires_at<=now()')
    await request.app['pool'].execute('''INSERT INTO admin_sessions VALUES ($1,1,$2,now()+interval '8 hours')''', digest, csrf)
    response = web.json_response({'ok': True, 'csrf': csrf})
    response.set_cookie(COOKIE, token, httponly=True, samesite='Strict',
        secure=os.getenv('ADMIN_COOKIE_SECURE', 'false').lower() == 'true',
        max_age=28800, path='/api/admin')
    return response

def throttled(request):
    # Global cap is deliberate: rootless Docker may hide the real client IP.
    attempts = request.app['admin_attempts']
    now = time.monotonic()
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    if len(attempts) >= 20:
        return True
    attempts.append(now)
    return False

async def setup_status(request):
    exists = await request.app['pool'].fetchval('SELECT EXISTS(SELECT 1 FROM admin_accounts)')
    enabled = len(os.getenv('ADMIN_SETUP_KEY', '')) >= 24
    return web.json_response({'registered': exists, 'setup_enabled': enabled})

async def register(request):
    data = await body(request)
    if throttled(request):
        return error('Слишком много попыток. Подожди минуту.', 429)
    key = os.getenv('ADMIN_SETUP_KEY', '')
    supplied = data.get('setup_key')
    if len(key) < 24 or not isinstance(supplied, str) or not hmac.compare_digest(key.encode(), supplied.encode()):
        return error('Неверный код регистрации владельца.', 403)
    login, password = data.get('login'), data.get('password')
    if not isinstance(login, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', login):
        return error('Логин: 3–40 латинских букв, цифр, точек, дефисов или подчёркиваний.')
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        return error('Пароль должен содержать от 12 до 128 символов.')
    salt = secrets.token_hex(16)
    hashed = await asyncio.to_thread(password_hash, password, salt)
    async with request.app['pool'].acquire() as c:
        async with c.transaction():
            await c.execute('SELECT pg_advisory_xact_lock(8101)')
            if await c.fetchval('SELECT EXISTS(SELECT 1 FROM admin_accounts)'):
                return error('Администратор уже зарегистрирован. Используй вход.', 409)
            await c.execute('INSERT INTO admin_accounts VALUES (1,$1,$2,$3)', login, salt, hashed)
    return await issue_session(request)

async def login(request):
    data = await body(request)
    if throttled(request):
        return error('Слишком много попыток. Подожди минуту.', 429)
    name, password = data.get('login'), data.get('password')
    if not isinstance(name, str) or not isinstance(password, str) or len(password)>128:
        return error('Неверный логин или пароль.', 401)
    row = await request.app['pool'].fetchrow('SELECT * FROM admin_accounts WHERE login=$1', name)
    salt = row['salt'] if row else '0' * 32
    hashed = await asyncio.to_thread(password_hash, password, salt)
    if not row or not hmac.compare_digest(hashed, row['password_hash']):
        return error('Неверный логин или пароль.', 401)
    return await issue_session(request)

async def me(request):
    row = await session(request)
    return web.json_response({'login': row['login'], 'csrf': row['csrf']})

async def logout(request):
    await body(request)
    row = await session(request, write=True)
    await request.app['pool'].execute('DELETE FROM admin_sessions WHERE token_hash=$1', row['token_hash'])
    response = web.json_response({'ok': True})
    response.del_cookie(COOKIE, path='/api/admin')
    return response

async def bookings(request):
    await session(request)
    status = request.query.get('status', '')
    if status and status not in STATES:
        return error('Неизвестный статус.')
    try:
        page = max(0, min(int(request.query.get('page', '0')), 100000))
    except ValueError:
        return error('Неверная страница.')
    pool = request.app['pool']
    rows = await pool.fetch('''SELECT b.*,z.title AS zone_title FROM bookings b
        JOIN zones z ON z.code=b.zone WHERE ($1='' OR b.status=$1)
        ORDER BY b.id DESC LIMIT 51 OFFSET $2''', status, page * 50)
    counts = await pool.fetch('SELECT status,count(*) AS total FROM bookings GROUP BY status')
    items = []
    for r in rows[:50]:
        items.append({
            'id': r['id'], 'name': r['customer_name'], 'phone': r['contact'],
            'source': 'Сайт' if r['user_id']==0 else 'Telegram',
            'zone': r['zone_title'], 'starts_at': r['starts_at'].isoformat(),
            'hours': r['hours'], 'status': r['status'], 'notified': r['notified'],
            'created_at': r['created_at'].isoformat(),
        })
    return web.json_response({'items': items, 'has_next': len(rows)>50,
        'counts': {r['status']: r['total'] for r in counts}})

async def change_status(request):
    data = await body(request)
    await session(request, write=True)
    status = data.get('status')
    if not isinstance(status, str) or status not in STATES:
        return error('Неизвестный статус.')
    try:
        number = int(request.match_info['id'])
        if not 0 < number < 2**63:
            raise ValueError()
    except ValueError:
        return error('Неверный номер заявки.')
    changed = await request.app['pool'].fetchval('UPDATE bookings SET status=$1 WHERE id=$2 RETURNING id', status, number)
    if changed is None:
        return error('Заявка не найдена.', 404)
    return web.json_response({'ok': True})

@web.middleware
async def privacy(request, handler):
    response = await handler(request)
    if request.path.startswith('/api/admin'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

def install(app):
    app['admin_attempts'] = deque(maxlen=20)
    app.middlewares.append(privacy)
    app.add_routes([
        web.get('/api/admin/setup', setup_status), web.post('/api/admin/register', register),
        web.post('/api/admin/login', login), web.get('/api/admin/me', me),
        web.post('/api/admin/logout', logout), web.get('/api/admin/bookings', bookings),
        web.patch('/api/admin/bookings/{id}', change_status),
    ])
