const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('.site-nav');
menuButton.addEventListener('click', () => {
  const expanded = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!expanded));
  menuButton.setAttribute('aria-label', expanded ? 'Открыть меню' : 'Закрыть меню');
  navigation.classList.toggle('open', !expanded);
});
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
  menuButton.setAttribute('aria-expanded', 'false');
  menuButton.setAttribute('aria-label', 'Открыть меню');
  navigation.classList.remove('open');
}));

document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  const filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(item => {
    const active = item === button;
    item.classList.toggle('active', active);
    item.setAttribute('aria-pressed', String(active));
  });
  document.querySelectorAll('[data-plan-id]').forEach(card => { card.hidden = filter !== 'all' && card.dataset.category !== filter; });
}));

// Stable identifiers are ready to map to future database records.
const plans = {
  'pc-hour': {title: 'ПК / 1 час', description: 'Короткая сессия за игровым ПК. Продолжительность: 1 час.', price: 'Пример: от 250 ₽ / час'},
  'pc-evening': {title: 'ПК / 5 часов', description: 'Пакет для длинной игровой сессии за ПК. Продолжительность: 5 часов.', price: 'Пример: от 990 ₽ / пакет'},
  'pc-day': {title: 'ПК / день', description: 'Дневной пакет за игровым ПК. Время действия уточняется.', price: 'Пример: от 1 790 ₽ / день'},
  'console-hour': {title: 'Консоль / 1 час', description: 'Игровое время в консольной зоне. Продолжительность: 1 час.', price: 'Пример: от 450 ₽ / час'}
};
const dialog = document.querySelector('#plan-dialog');
document.querySelectorAll('[data-plan-open]').forEach(button => button.addEventListener('click', () => {
  const plan = plans[button.dataset.planOpen];
  if (!plan) return;
  document.querySelector('#dialog-title').textContent = plan.title;
  document.querySelector('#dialog-description').textContent = plan.description;
  document.querySelector('#dialog-price').textContent = plan.price;
  dialog.showModal();
}));
dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.querySelector('.dialog-ok').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
document.querySelector('#year').textContent = new Date().getFullYear();
