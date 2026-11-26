// 線上客服：會員端（右下角按鈕）與管理員端（客服訊息頁）共用的聊天介面
(function () {
  const T = window.T || (s => s);
  const OPEN_POLL_MS = 3000;     // 聊天中：每 3 秒檢查新訊息
  const IDLE_POLL_MS = 20000;    // 視窗關閉：每 20 秒檢查未讀數

  // ---- 共用：畫出訊息 ----
  function makeChat(bodyEl, mine) {
    let lastId = 0, lastDay = '';
    function add(m) {
      if (m.id <= lastId) return;
      lastId = m.id;
      const empty = bodyEl.querySelector('.chat-empty'); if (empty) empty.remove();
      const day = m.time.slice(0, 5);
      if (day !== lastDay) {
        lastDay = day;
        const sep = document.createElement('div'); sep.className = 'chat-day'; sep.textContent = day.replace('-', '/');
        bodyEl.appendChild(sep);
      }
      const row = document.createElement('div');
      row.className = 'chat-msg ' + (m.sender === mine ? 'me' : 'them');
      const bubble = document.createElement('div'); bubble.className = 'chat-bubble'; bubble.textContent = m.body;
      const time = document.createElement('div'); time.className = 'chat-time'; time.textContent = m.time.slice(6);
      row.append(bubble, time);
      bodyEl.appendChild(row);
    }
    function addAll(list) {
      const nearBottom = bodyEl.scrollHeight - bodyEl.scrollTop - bodyEl.clientHeight < 80;
      list.forEach(add);
      if (list.length && (nearBottom || list.some(m => m.sender === mine))) bodyEl.scrollTop = bodyEl.scrollHeight;
    }
    function reset() { lastId = 0; lastDay = ''; bodyEl.innerHTML = ''; }
    return { addAll, reset, get lastId() { return lastId; } };
  }

  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  }

  function wireForm(form, input, send) {
    input.addEventListener('input', () => autoGrow(input));
    input.addEventListener('keydown', e => {   // Enter 送出，Shift+Enter 換行（手機鍵盤照常換行）
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && window.matchMedia('(hover: hover)').matches) {
        e.preventDefault(); form.requestSubmit();
      }
    });
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      const btn = form.querySelector('button'); btn.disabled = true;
      try {
        const ok = await send(text);
        if (ok) { input.value = ''; autoGrow(input); }
      } finally { btn.disabled = false; input.focus(); }
    });
  }

  async function postMessage(url, csrf, text) {
    const fd = new FormData(); fd.append('_csrf', csrf); fd.append('body', text);
    const res = await fetch(url, { method: 'POST', body: fd, headers: { 'X-CSRF-Token': csrf } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      (window.hrAlert || alert)(T(data.error || '傳送失敗，請再試一次'));
      return null;
    }
    return data.message;
  }

  // ================================================================ 會員端
  const panel = document.getElementById('chat-panel');
  if (panel) {
    const fab = document.getElementById('chat-fab');
    const badge = document.getElementById('chat-fab-badge');
    const body = document.getElementById('chat-body');
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const api = panel.dataset.api, csrf = panel.dataset.csrf;
    const chat = makeChat(body, 'member');
    let open = false, timer = null, loaded = false;

    if (document.querySelector('.summary-bar')) fab.classList.add('raised');   // 預約頁避開底部的確認列

    function setBadge(n) { badge.textContent = n > 99 ? '99+' : n; badge.hidden = !n; }

    async function poll() {
      if (document.hidden) return schedule();
      try {
        if (open) {
          const res = await fetch(`${api}?after=${chat.lastId}`);
          const data = await res.json();
          if (data.ok) { chat.addAll(data.messages); setBadge(0); loaded = true; }
        } else {
          const res = await fetch(`${api}?peek=1`);
          const data = await res.json();
          if (data.ok) setBadge(data.unread);
        }
      } catch (_) { /* 網路斷線時下次再試 */ }
      schedule();
    }
    function schedule() { clearTimeout(timer); timer = setTimeout(poll, open ? OPEN_POLL_MS : IDLE_POLL_MS); }

    function setOpen(v) {
      open = v;
      panel.hidden = !v;
      fab.classList.toggle('active', v);
      document.body.classList.toggle('chat-open', v);
      if (v) { poll(); setTimeout(() => input.focus(), 50); } else schedule();
    }
    fab.addEventListener('click', () => setOpen(!open));
    document.getElementById('chat-close').addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && open) setOpen(false); });
    wireForm(form, input, async text => {
      const m = await postMessage(api, csrf, text);
      if (m) chat.addAll([m]);
      return !!m;
    });
    schedule();
  }

  // ================================================================ 管理員端（客服訊息頁）
  const admin = document.getElementById('admin-chat');
  if (admin) {
    const listEl = document.getElementById('conv-list');
    const body = document.getElementById('admin-chat-body');
    const form = document.getElementById('admin-chat-form');
    const input = document.getElementById('admin-chat-input');
    const head = document.getElementById('admin-chat-head');
    const csrf = admin.dataset.csrf, listApi = admin.dataset.listApi, convBase = admin.dataset.convBase;
    const memberBase = admin.dataset.memberBase;
    const chat = makeChat(body, 'admin');
    let current = +admin.dataset.openUid || 0, timer = null;

    function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    async function loadList() {
      try {
        const data = await (await fetch(listApi)).json();
        if (!data.ok) return;
        const navBadge = document.getElementById('nav-chat-badge');
        if (navBadge) { navBadge.textContent = data.unread; navBadge.hidden = !data.unread; }
        if (!data.conversations.length) {
          listEl.innerHTML = `<div class="empty">${esc(T('還沒有客服訊息'))}</div>`;
          return;
        }
        listEl.innerHTML = data.conversations.map(c => `
          <button type="button" class="conv ${c.uid === current ? 'on' : ''} ${c.unread ? 'unread' : ''}" data-uid="${c.uid}">
            <span class="conv-top"><strong>${esc(c.name)}</strong><span class="muted small">${esc(c.time)}</span></span>
            <span class="conv-bottom"><span class="conv-last">${c.last_sender === 'admin' ? esc(T('你：')) : ''}${esc(c.last)}</span>
            ${c.unread ? `<span class="chat-fab-badge static">${c.unread}</span>` : ''}</span>
          </button>`).join('');
        listEl.querySelectorAll('.conv').forEach(b => b.addEventListener('click', () => openConv(+b.dataset.uid)));
      } catch (_) {}
    }

    async function loadConv() {
      if (!current) return;
      try {
        const data = await (await fetch(`${convBase}${current}?after=${chat.lastId}`)).json();
        if (!data.ok) return;
        const m = data.member;
        head.innerHTML = `<button type="button" class="conv-back" id="conv-back">←</button>
          <div><strong>${esc(m.name)}</strong><div class="muted small">${esc(m.phone || '')} · ${esc(m.email)}</div></div>
          <a class="btn ghost sm" href="${memberBase}${m.uid}">${esc(T('會員資料'))}</a>`;
        document.getElementById('conv-back').onclick = () => { current = 0; admin.classList.remove('has-conv'); loadList(); };
        chat.addAll(data.messages);
      } catch (_) {}
    }

    function openConv(uid) {
      current = uid;
      chat.reset();
      body.innerHTML = `<div class="chat-empty">${esc(T('還沒有訊息，可以直接傳訊息給這位會員。'))}</div>`;
      admin.classList.add('has-conv');
      form.hidden = false;
      loadConv().then(loadList);
      history.replaceState(null, '', `?uid=${uid}`);
      input.focus();
    }

    async function tick() {
      if (!document.hidden) { await loadConv(); await loadList(); }
      clearTimeout(timer); timer = setTimeout(tick, OPEN_POLL_MS);
    }

    wireForm(form, input, async text => {
      const m = await postMessage(`${convBase}${current}`, csrf, text);
      if (m) { chat.addAll([m]); loadList(); }
      return !!m;
    });
    if (current) openConv(current); else { form.hidden = true; loadList(); }
    timer = setTimeout(tick, OPEN_POLL_MS);
  }

  // ================================================================ 管理員：其他後台頁面的未讀數
  const navBadge = document.getElementById('nav-chat-badge');
  if (navBadge && !admin && navBadge.dataset.api) {
    setInterval(async () => {
      if (document.hidden) return;
      try {
        const data = await (await fetch(navBadge.dataset.api)).json();
        if (data.ok) { navBadge.textContent = data.unread; navBadge.hidden = !data.unread; }
      } catch (_) {}
    }, IDLE_POLL_MS);
  }
})();
