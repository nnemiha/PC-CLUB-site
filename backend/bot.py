import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from common import connect

dp = Dispatcher()
pool = None
tz = ZoneInfo(os.getenv('CLUB_TIMEZONE', 'Europe/Kaliningrad'))
owner = int(os.environ['OWNER_CHAT_ID'])

def keyboard(*labels):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=s)] for s in labels], resize_keyboard=True)

async def save(uid, step, data):
    await pool.execute('''INSERT INTO drafts VALUES ($1,$2,$3::jsonb)
        ON CONFLICT(user_id) DO UPDATE SET step=$2,data=$3::jsonb''', uid, step, json.dumps(data))

async def choose(m):
    rows = await pool.fetch('SELECT title,price FROM zones ORDER BY price')
    await save(m.from_user.id, 'zone', {})
    await m.answer('Выбери зону Marinovani:\n' + '\n'.join(f'{r["title"]}: {r["price"]} ₽/час' for r in rows),
                   reply_markup=keyboard(*(r['title'] for r in rows)))

@dp.message(Command('id'))
async def my_id(m: Message):
    await m.answer(f'Твой Telegram ID: {m.from_user.id}')

@dp.message(Command('cancel'))
async def cancel(m: Message):
    await pool.execute('DELETE FROM drafts WHERE user_id=$1', m.from_user.id)
    await m.answer('Заполнение отменено. Начать заново: /start', reply_markup=ReplyKeyboardRemove())

@dp.message(CommandStart())
async def start(m: Message):
    parts = (m.text or '').split(maxsplit=1)
    code = parts[1] if len(parts) == 2 else ''
    zone = await pool.fetchrow('SELECT * FROM zones WHERE code=$1', code)
    if not zone:
        return await choose(m)
    await save(m.from_user.id, 'name', {'zone': code})
    await m.answer(f'Выбрано: {zone["title"]}. Как тебя зовут?\nОтменить: /cancel', reply_markup=ReplyKeyboardRemove())

@dp.message(F.chat.type == 'private')
async def conversation(m: Message):
    uid = m.from_user.id
    row = await pool.fetchrow('SELECT * FROM drafts WHERE user_id=$1', uid)
    if not row:
        return await m.answer('Для новой заявки нажми /start. Узнать свой ID: /id')
    d = json.loads(row['data'])
    step = row['step']
    text = (m.text or '').strip()
    if step == 'zone':
        zone = await pool.fetchrow('SELECT code FROM zones WHERE title=$1', text)
        if not zone:
            return await m.answer('Выбери зону кнопкой ниже.')
        d['zone'] = zone['code']
        await save(uid, 'name', d)
        return await m.answer('Как тебя зовут?', reply_markup=ReplyKeyboardRemove())
    if step == 'name':
        if not 2 <= len(text) <= 80:
            return await m.answer('Введи имя от 2 до 80 символов.')
        d['name'] = text
        await save(uid, 'date', d)
        return await m.answer('Введи дату и время: ДД.ММ.ГГГГ ЧЧ:ММ\nНапример: ' +
                              (datetime.now(tz) + timedelta(days=1)).strftime('%d.%m.%Y 18:00') +
                              f'\nЧасовой пояс клуба: {tz.key}')
    if step == 'date':
        try:
            dt = datetime.strptime(text, '%d.%m.%Y %H:%M').replace(tzinfo=tz)
            if not datetime.now(tz) < dt < datetime.now(tz) + timedelta(days=90):
                raise ValueError()
        except ValueError:
            return await m.answer('Нужна будущая дата в пределах 90 дней, в формате ДД.ММ.ГГГГ ЧЧ:ММ.')
        d['date'] = dt.isoformat()
        await save(uid, 'hours', d)
        return await m.answer('На сколько часов? Введи число от 1 до 12.')
    if step == 'hours':
        if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 12:
            return await m.answer('Введи целое число от 1 до 12.')
        d['hours'] = int(text)
        await save(uid, 'contact', d)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Поделиться телефоном', request_contact=True)]], resize_keyboard=True)
        return await m.answer('Оставь телефон для связи: кнопкой или введи номер с кодом страны.', reply_markup=kb)
    if step == 'contact':
        if m.contact and m.contact.user_id == uid:
            phone = m.contact.phone_number
        elif m.contact:
            return await m.answer('Отправь собственный контакт.')
        else:
            phone = text
        phone = re.sub(r'[\s()+-]', '', phone)
        if not re.fullmatch(r'[0-9]{10,15}', phone):
            return await m.answer('Введи телефон с кодом страны, от 10 до 15 цифр.')
        d['contact'] = phone
        z = await pool.fetchrow('SELECT * FROM zones WHERE code=$1', d['zone'])
        await save(uid, 'confirm', d)
        return await m.answer(f'Проверь заявку:\n{z["title"]}\nИмя: {d["name"]}\n'
            f'Дата: {datetime.fromisoformat(d["date"]).strftime("%d.%m.%Y %H:%M")}\n'
            f'Часов: {d["hours"]}\nТелефон: {phone}\n'
            f'По часовому тарифу: {z["price"] * d["hours"]} ₽. Ночные пакеты уточняет администратор.\n'
            'Это заявка, место подтверждает администратор. Нажимая «Отправить заявку», '
            'ты соглашаешься передать эти данные клубу для связи по бронированию.',
            reply_markup=keyboard('Отправить заявку', '/cancel'))
    if step == 'confirm':
        if text != 'Отправить заявку':
            return await m.answer('Нажми «Отправить заявку» или /cancel.')
        if datetime.fromisoformat(d['date']) <= datetime.now(tz):
            return await choose(m)
        async with pool.acquire() as c:
            async with c.transaction():
                draft = await c.fetchrow('DELETE FROM drafts WHERE user_id=$1 RETURNING user_id', uid)
                if not draft:
                    return
                number = await c.fetchval('''INSERT INTO bookings
                    (user_id,username,zone,customer_name,starts_at,hours,contact)
                    VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id''',
                    uid, m.from_user.username, d['zone'], d['name'], datetime.fromisoformat(d['date']), d['hours'], d['contact'])
        await m.answer(f'Заявка №{number} сохранена! Администратор свяжется с тобой для подтверждения.\nНовая заявка: /start', reply_markup=ReplyKeyboardRemove())

async def notify(bot):
    while True:
        try:
            rows = await pool.fetch('''SELECT b.*, z.title FROM bookings b JOIN zones z ON z.code=b.zone
                WHERE NOT notified ORDER BY b.id LIMIT 10''')
            for r in rows:
                user = 'заявка с сайта' if r['user_id'] == 0 else ('@' + r['username'] if r['username'] else str(r['user_id']))
                await bot.send_message(owner, f'Новая заявка №{r["id"]}\n{r["title"]}\n'
                    f'{r["customer_name"]} ({user})\n'
                    f'{r["starts_at"].astimezone(tz).strftime("%d.%m.%Y %H:%M")} ({tz.key})\n'
                    f'Часов: {r["hours"]}\nТелефон: {r["contact"]}\nТребуется подтверждение администратором.')
                await pool.execute('UPDATE bookings SET notified=TRUE WHERE id=$1', r['id'])
        except Exception as exc:
            logging.warning('Notification failed (%s); will retry', type(exc).__name__)
        await asyncio.sleep(10)

async def main():
    global pool
    pool = await connect()
    async with Bot(os.environ['BOT_TOKEN']) as bot:
        await bot.delete_webhook(drop_pending_updates=False)
        task = asyncio.create_task(notify(bot))
        try:
            await dp.start_polling(bot, tasks_concurrency_limit=20)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await pool.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
