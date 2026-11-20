from aiohttp import web
from common import connect

async def zones(request):
    rows = await request.app['pool'].fetch('SELECT code,title,price FROM zones ORDER BY price')
    return web.json_response([dict(r) for r in rows])

async def health(request):
    await request.app['pool'].fetchval('SELECT 1')
    return web.json_response({'ok': True})

async def lifecycle(app):
    app['pool'] = await connect()
    yield
    await app['pool'].close()

app = web.Application()
app.cleanup_ctx.append(lifecycle)
app.add_routes([web.get('/api/zones', zones), web.get('/api/health', health)])
if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8000, access_log=None)
