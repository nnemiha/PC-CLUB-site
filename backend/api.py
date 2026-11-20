import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiohttp import web
from common import connect

TZ = ZoneInfo('Europe/Kaliningrad')

async def zones(request):
    rows = await request.app['pool'].fetch('SELECT code,title,price FROM zones ORDER BY price')
    return web.json_response([dict(row) for row in rows])

async def health(request):
    await request.app['pool'].fetchval('SELECT 1')
    return web.json_response({'ok': True})

async def create_booking(request):
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError()
        name, phone, zone, date = [data.get(key) for key in ('name', 'phone', 'zone', 'date')]
        hours = data.get('hours')
        if not all(isinstance(value, str) for value in (name, phone, zone, date)):
            raise ValueError()
        name = name.strip()
        phone = re.sub(r'[\s()+-]', '', phone)
        if not 2 <= len(name) <= 80:
            raise ValueError('Имя должно содержать от 2 до 80 символов.')
        if not re.fullmatch(r'[0-9]{10,15}', phone):
            raise ValueError('Укажи телефон с кодом страны: от 10 до 15 цифр.')
        if type(hours) is not int or not 1 <= hours <= 12:
            raise ValueError('Выбери от 1 до 12 часов.')
        if len(date) != 16:
            raise ValueError()
        starts = datetime.strptime(date, '%Y-%m-%dT%H:%M').replace(tzinfo=TZ)
        now = datetime.now(TZ)
        if not now < starts < now + timedelta(days=90):
            raise ValueError('Нужна будущая дата в пределах 90 дней.')
        if data.get('consent') is not True:
            raise ValueError('Подтверди передачу данных для связи по заявке.')
    except (ValueError, TypeError) as exc:
        message = str(exc) if isinstance(exc, ValueError) and str(exc).startswith(('Имя', 'Укажи', 'Выбери', 'Нужна', 'Подтверди')) else 'Проверь заполнение полей.'
        return web.json_response({'error': message}, status=400)

    pool = request.app['pool']
    try:
        if not await pool.fetchval('SELECT EXISTS(SELECT 1 FROM zones WHERE code=$1)', zone):
            return web.json_response({'error': 'Выбери зону из списка.'}, status=400)
        # Zero marks a website request; Telegram requests use a real user ID.
        number = await pool.fetchval('''INSERT INTO bookings
            (user_id,username,zone,customer_name,starts_at,hours,contact)
            VALUES (0,NULL,$1,$2,$3,$4,$5) RETURNING id''',
            zone, name, starts, hours, phone)
    except Exception:
        logging.exception('Website booking save failed')
        return web.json_response({'error': 'Не удалось сохранить заявку. Попробуй позже.'}, status=503)
    return web.json_response({'id': number}, status=201)

async def lifecycle(app):
    app['pool'] = await connect()
    yield
    await app['pool'].close()

app = web.Application(client_max_size=4096)
app.cleanup_ctx.append(lifecycle)
app.add_routes([
    web.get('/api/zones', zones),
    web.get('/api/health', health),
    web.post('/api/bookings', create_booking),
])
if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8000, access_log=None)
