(() => {
  const form = document.querySelector('#booking-form');
  const result = document.querySelector('#booking-result');
  const button = form.querySelector('[type=submit]');
  const select = form.elements.zone;
  let zones = [];
  let busy = false;
  function price() {
    const zone = zones.find(z => z.code === select.value);
    document.querySelector('#booking-price').textContent = zone
      ? `По часовому тарифу: ${zone.price * Number(form.elements.hours.value)} ₽. Ночные пакеты уточняет администратор.` : '';
    document.querySelector('#booking-telegram').href = 'https://t.me/imangelo_bot' +
      (zone ? `?start=${encodeURIComponent(zone.code)}` : '');
  }
  form.addEventListener('input', price);
  async function load() {
    try {
      const response = await fetch('/api/zones');
      if (!response.ok) throw new Error();
      zones = await response.json();
      if (!Array.isArray(zones) || !zones.length) throw new Error();
      select.replaceChildren(new Option('Выбери зону', ''));
      zones.forEach(z => select.add(new Option(`${z.title} — ${z.price} ₽/час`, z.code)));
      button.disabled = false;
    } catch {
      result.textContent = 'Не удалось загрузить зоны. Обнови страницу позже.';
    }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true;
    button.disabled = true;
    result.textContent = 'Отправляем…';
    try {
      const response = await fetch('/api/bookings', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: form.elements.name.value, phone: form.elements.phone.value,
          zone: select.value, date: form.elements.date.value,
          hours: Number(form.elements.hours.value), consent: form.elements.consent.checked
        })
      });
      const data = await response.json();
      if (!response.ok) {
        result.textContent = data.error || 'Не удалось отправить заявку.';
        return;
      }
      form.reset();
      price();
      result.textContent = `Заявка №${data.id} сохранена! Администратор свяжется для подтверждения.`;
    } catch {
      result.textContent = 'Не удалось получить ответ. Заявка могла сохраниться — уточни у администратора перед повторной отправкой.';
    } finally {
      busy = false;
      button.disabled = false;
    }
  });
  // Connect existing tariff buttons to the real form instead of the demo dialog.
  const presets = {
    'pc-hour': ['standard_pc', 1], 'pc-evening': ['standard_pc', 5],
    'pc-day': ['standard_pc', 12], 'console-hour': ['ps5', 1]
  };
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-plan-open]');
    if (!trigger) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const preset = presets[trigger.dataset.planOpen];
    if (preset && zones.length) {
      select.value = preset[0];
      form.elements.hours.value = preset[1];
      price();
    }
    document.querySelector('#booking').scrollIntoView({behavior: 'smooth'});
  }, true);
  load();
})();
