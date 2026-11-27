(() => {
  const $ = s => document.querySelector(s);
  const names = {new:'Новая', confirmed:'Подтверждена', cancelled:'Отменена'};
  let csrf = '', page = 0, registering = false, loading = false;
  function notice(text) { $('#notice').textContent = text; }
  async function api(path, method='GET', data) {
    const response = await fetch('/api/admin' + path, {
      method, credentials:'same-origin', cache:'no-store',
      headers: method==='GET' ? {} : {'Content-Type':'application/json', 'X-Admin-Request':'1', 'X-CSRF-Token':csrf},
      ...(data === undefined ? {} : {body:JSON.stringify(data)})
    });
    const value = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(value.error || (response.status===401 ? 'Войди в аккаунт.' : 'Ошибка сервера. Попробуй позже.'));
      error.status = response.status;
      throw error;
    }
    return value;
  }
  function paragraph(card, text) {
    const p = document.createElement('p'); p.textContent = text; card.append(p);
  }
  function date(value) {
    return new Intl.DateTimeFormat('ru-RU', {dateStyle:'short', timeStyle:'short', timeZone:'Europe/Kaliningrad'}).format(new Date(value));
  }
  async function load() {
    if (loading) return;
    loading = true;
    try {
      const data = await api('/bookings?status=' + encodeURIComponent($('#filter').value) + '&page=' + page);
      const c = data.counts;
      $('#counts').textContent = `Новых: ${c.new || 0} · Подтверждено: ${c.confirmed || 0} · Отменено: ${c.cancelled || 0}`;
      const cards = [];
      for (const item of data.items) {
        const card = document.createElement('article'); card.className='booking';
        const title = document.createElement('h2'); title.textContent=`№${item.id} · ${names[item.status] || item.status}`; card.append(title);
        paragraph(card, `${item.name} · ${item.phone}`);
        paragraph(card, `${item.zone} · ${date(item.starts_at)} · ${item.hours} ч. (Калининград)`);
        paragraph(card, `Источник: ${item.source} · Получена: ${date(item.created_at)}`);
        paragraph(card, `Уведомление владельцу в Telegram: ${item.notified ? 'отправлено' : 'ожидает отправки'}`);
        const actions = document.createElement('div'); actions.className='actions';
        for (const [status, label] of [['confirmed','Подтвердить'], ['cancelled','Отменить'], ['new','Вернуть в новые']]) {
          if (status===item.status) continue;
          const button=document.createElement('button'); button.textContent=label;
          button.addEventListener('click', async () => {
            if (status==='cancelled' && !confirm(`Отменить заявку №${item.id}?`)) return;
            button.disabled=true;
            try { await api('/bookings/'+item.id, 'PATCH', {status}); await load(); notice(`Заявка №${item.id}: ${names[status].toLowerCase()}.`); }
            catch(e) { notice(e.message); } finally { button.disabled=false; }
          });
          actions.append(button);
        }
        card.append(actions); cards.push(card);
      }
      $('#bookings').replaceChildren(...cards);
      if (!cards.length) $('#bookings').textContent='Заявок с этим статусом пока нет.';
      $('#page').textContent=`Страница ${page+1}`;
      $('#previous').disabled=page===0; $('#next').disabled=!data.has_next;
    } catch(e) {
      if (e.status===401) { $('#dashboard').hidden=true; $('#auth').hidden=false; }
      notice(e.message);
    } finally { loading=false; }
  }
  async function dashboard() {
    const me = await api('/me'); csrf=me.csrf;
    $('#auth').hidden=true; $('#dashboard').hidden=false;
    notice(`Выполнен вход: ${me.login}`); await load();
  }
  $('#auth-form').addEventListener('submit', async e => {
    e.preventDefault(); const form=e.currentTarget; const button=$('#auth-submit'); button.disabled=true;
    try {
      await api(registering ? '/register' : '/login', 'POST', {
        login:form.elements.login.value, password:form.elements.password.value,
        setup_key:form.elements.setup_key.value
      });
      form.reset(); await dashboard();
    } catch(e) { notice(e.message); } finally { button.disabled=false; }
  });
  $('#logout').addEventListener('click', async () => {
    try { await api('/logout','POST',{}); location.reload(); } catch(e) { notice(e.message); }
  });
  $('#filter').addEventListener('change', () => { page=0; load(); });
  $('#refresh').addEventListener('click', load);
  $('#previous').addEventListener('click', () => { if(page>0) { page--; load(); } });
  $('#next').addEventListener('click', () => { page++; load(); });
  async function start() {
    try {
      const setup = await api('/setup'); registering=!setup.registered;
      $('#auth').hidden=false;
      if (registering) {
        $('#auth-title').textContent='Регистрация владельца';
        $('#setup-field').hidden=false; $('#setup-hint').hidden=false;
        $('#auth-submit').textContent='Создать аккаунт';
        $('#auth-form').elements.password.minLength=12;
        $('#auth-form').elements.password.autocomplete='new-password';
        $('#auth-form').elements.setup_key.required=true;
        if (!setup.setup_enabled) {
          notice('Регистрация выключена. Добавь ADMIN_SETUP_KEY в серверный .env и перезапусти API.');
          $('#auth-submit').disabled=true; return;
        }
      }
      try { await dashboard(); } catch(e) { if(e.status!==401) throw e; notice(''); }
    } catch(e) { notice(e.message); }
  }
  setInterval(() => { if(!$('#dashboard').hidden && !document.hidden) load(); },15000);
  start();
})();
