// Add <div id="marinovani-zones"></div> and the script tag to index.html.
(async () => {
  const target = document.getElementById('marinovani-zones');
  if (!target) return;
  target.textContent = 'Загружаем зоны…';
  try {
    const response = await fetch('/api/zones');
    if (!response.ok) throw new Error('API unavailable');
    const zones = await response.json();
    target.replaceChildren();
    for (const zone of zones) {
      const card = document.createElement('article');
      card.style.cssText = 'padding:24px;margin:16px 0;background:#20202b;border-radius:12px;color:white';
      const title = document.createElement('h3');
      title.textContent = zone.title;
      const price = document.createElement('p');
      price.textContent = `${zone.price} ₽/час`;
      const link = document.createElement('a');
      link.textContent = 'Оставить заявку в Telegram →';
      link.href = `https://t.me/imangelo_bot?start=${encodeURIComponent(zone.code)}`;
      link.style.color = '#ffca66';
      card.append(title, price, link);
      target.append(card);
    }
  } catch {
    target.textContent = 'Не удалось загрузить зоны. Попробуй обновить страницу.';
  }
})();
