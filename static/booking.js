// 共用的預約時段選擇器（會員預約頁與後台新增預約都使用）
(function () {
  const form = document.getElementById('booking-form');
  if (!form) return;

  const isAdmin = form.dataset.admin === '1';
  const minDate = form.dataset.min;
  const maxDate = form.dataset.max;
  const closedWeekdays = JSON.parse(form.dataset.closedWeekdays || '[]'); // 0=週一
  const closedDates = JSON.parse(form.dataset.closedDates || '[]');
  const EN = document.documentElement.lang === 'en';
  const T = window.T || (s => s);
  const WD = EN ? ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] : ['日', '一', '二', '三', '四', '五', '六'];
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const wdLabel = d => EN ? WD[d.getDay()] : '週' + WD[d.getDay()];
  const monLabel = d => EN ? MON[d.getMonth()] : (d.getMonth() + 1) + '月';

  const dateInput = form.querySelector('input[name=date]');
  const timeInput = form.querySelector('input[name=time]');
  const strip = document.getElementById('date-strip');
  const other = document.getElementById('date-other');
  const slotsBox = document.getElementById('slots');
  const sumText = document.getElementById('sum-text');
  const submitBtn = document.getElementById('submit-btn');

  const pad = n => String(n).padStart(2, '0');
  const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parse = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const pyWeekday = d => (d.getDay() + 6) % 7;
  const isClosed = d => closedWeekdays.includes(pyWeekday(d)) || closedDates.includes(iso(d));

  function getService() {
    const el = form.querySelector('[name=service_id]:checked') || form.querySelector('select[name=service_id]');
    if (!el || !el.value) return null;
    const src = el.tagName === 'SELECT' ? el.selectedOptions[0] : el;
    return { id: el.value, name: src.dataset.name, duration: src.dataset.duration, price: src.dataset.price };
  }

  // 日期列：顯示 14 天
  function buildStrip(startIso) {
    if (!strip) return;
    strip.innerHTML = '';
    let d = parse(startIso || minDate);
    const end = maxDate ? parse(maxDate) : null;
    for (let i = 0; i < 14; i++) {
      if (end && d > end) break;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'date-chip' + (isClosed(d) ? ' closed' : '');
      b.dataset.date = iso(d);
      b.innerHTML = `<div class="dw">${wdLabel(d)}</div><div class="dd">${d.getDate()}</div><div class="dm">${monLabel(d)}</div>`;
      b.addEventListener('click', () => selectDate(b.dataset.date));
      strip.appendChild(b);
      d.setDate(d.getDate() + 1);
    }
    highlightDate();
  }

  function highlightDate() {
    if (!strip) return;
    strip.querySelectorAll('.date-chip').forEach(c => c.classList.toggle('selected', c.dataset.date === dateInput.value));
  }

  function selectDate(v) {
    dateInput.value = v;
    if (other) other.value = v;
    if (strip && !strip.querySelector(`[data-date="${v}"]`)) buildStrip(v);
    highlightDate();
    loadSlots();
  }

  let reqId = 0;
  async function loadSlots() {
    timeInput.value = '';
    updateSummary();
    const svc = getService();
    if (!svc) { slotsBox.innerHTML = `<div class="slots-empty">${T('請先選擇服務項目')}</div>`; return; }
    if (!dateInput.value) { slotsBox.innerHTML = `<div class="slots-empty">${T('請選擇日期')}</div>`; return; }
    slotsBox.innerHTML = `<div class="slots-empty">${T('載入可預約時段…')}</div>`;
    const my = ++reqId;
    try {
      const params = new URLSearchParams({ service_id: svc.id, date: dateInput.value });
      if (isAdmin) params.set('admin', '1');
      const res = await fetch('/api/slots?' + params);
      const data = await res.json();
      if (my !== reqId) return;
      if (data.closed) { slotsBox.innerHTML = `<div class="slots-empty">${data.message}${EN ? '. ' : '，'}${T('請選擇其他日期')}</div>`; return; }
      const slots = data.slots || [];
      if (!slots.length || !slots.some(s => s.available)) {
        slotsBox.innerHTML = `<div class="slots-empty">${T('這天已無可預約時段，請選擇其他日期')}</div>`;
        if (!slots.length) return;
      } else {
        slotsBox.innerHTML = '';
      }
      const grid = document.createElement('div');
      grid.className = 'slots';
      slots.forEach(s => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'slot';
        b.textContent = s.time;
        b.disabled = !s.available;
        if (isAdmin && s.available) b.title = EN ? `${s.remaining} left` : `剩餘 ${s.remaining} 位`;
        b.addEventListener('click', () => {
          grid.querySelectorAll('.slot').forEach(x => x.classList.remove('selected'));
          b.classList.add('selected');
          timeInput.value = s.time;
          timeInput.dataset.end = s.end;
          updateSummary();
        });
        grid.appendChild(b);
      });
      if (slots.some(s => s.available)) slotsBox.appendChild(grid);
    } catch (e) {
      slotsBox.innerHTML = `<div class="slots-empty">${T('無法載入時段，請重新整理頁面')}</div>`;
    }
  }

  // 優惠券：只有適用目前項目的券可以選；選券時若項目不適用且券只對應一個項目，自動切換到該項目
  const couponRadios = [...form.querySelectorAll('input[name=user_coupon_id]')];
  function couponServices(r) { return (r.dataset.services || '').split(',').filter(Boolean); }
  function syncCoupons() {
    const svc = getService();
    couponRadios.forEach(r => {
      if (!r.value) return;
      const ok = !svc || couponServices(r).includes(String(svc.id));
      r.closest('.cp-opt').classList.toggle('na', !ok);
      if (!ok && r.checked) { const none = couponRadios.find(x => !x.value); if (none) none.checked = true; }
    });
  }
  function selectedCoupon() { return couponRadios.find(r => r.checked && r.value) || null; }
  couponRadios.forEach(r => r.addEventListener('change', () => {
    if (!r.value) { updateSummary(); return; }
    const svc = getService();
    const ids = couponServices(r);
    if ((!svc || !ids.includes(String(svc.id))) && ids.length) {
      const target = form.querySelector(`input[name=service_id][value="${ids[0]}"]`);
      if (target && ids.length === 1) {
        target.checked = true;
        const det = target.closest('details'); if (det) det.open = true;
        loadSlots();
      } else if (!svc || !ids.includes(String(svc.id))) {
        // 多個適用項目：打開第一個適用項目所在的分類，讓客人自己選
        const det = target && target.closest('details'); if (det) { det.open = true; det.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      }
    }
    syncCoupons(); updateSummary();
  }));

  function updateSummary() {
    syncCoupons && couponRadios.length && syncCoupons();
    const svc = getService();
    const ready = svc && dateInput.value && timeInput.value;
    if (submitBtn) submitBtn.disabled = !ready;
    if (!sumText) return;
    if (!svc) { sumText.innerHTML = `<strong>${T('尚未選擇服務')}</strong>`; return; }
    let line = '';
    if (dateInput.value) {
      const d = parse(dateInput.value);
      line = (EN ? `${d.getDate()} ${MON[d.getMonth()]} (${WD[d.getDay()]})` : `${d.getMonth() + 1}/${d.getDate()}（${WD[d.getDay()]}）`) +(timeInput.value ? ` ${timeInput.value}` : ' · ' + T('請選擇時間'));
    }
    const cp = selectedCoupon();
    if (cp) line += `<br>🎫 ${cp.dataset.name} · ${T('體驗價')} ${cp.dataset.price}`;
    sumText.innerHTML = `<strong>${svc.name}</strong>${line}`;
  }

  form.querySelectorAll('[name=service_id]').forEach(el => el.addEventListener('change', loadSlots));
  if (other) other.addEventListener('change', () => other.value && selectDate(other.value));
  // 預約須知彈窗：必須勾選確認才能送出
  const modal = document.getElementById('notice-modal');
  const confirmInput = form.querySelector('input[name=confirm_notice]');
  if (modal) {
    const ok = document.getElementById('notice-ok');
    const go = document.getElementById('notice-confirm');
    const close = () => { modal.hidden = true; document.body.style.overflow = ''; };
    ok.addEventListener('change', () => { go.disabled = !ok.checked; });
    document.getElementById('notice-cancel').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !modal.hidden) close(); });
    go.addEventListener('click', () => {
      if (!ok.checked) return;
      confirmInput.value = '1';
      go.disabled = true;
      form.submit();
    });
    form.addEventListener('submit', e => {
      if (confirmInput.value === '1') return;
      e.preventDefault();
      if (!timeInput.value) { (window.hrAlert || alert)(T('請選擇預約時間')); return; }
      const sum = document.getElementById('notice-summary');
      if (sum && sumText) sum.innerHTML = sumText.innerHTML;
      ok.checked = false; go.disabled = true;
      modal.hidden = false; document.body.style.overflow = 'hidden';
      ok.focus();
    });
  }
  form.addEventListener('submit', e => { if (!timeInput.value) { e.preventDefault(); if (!modal) (window.hrAlert || alert)(T('請選擇預約時間')); } });

  // 從「立即使用」進來且券適用多個項目時：展開對應的主項目讓客人挑選
  const preCp = couponRadios.length ? selectedCoupon() : null;
  if (preCp && !getService()) {
    const first = form.querySelector(`input[name=service_id][value="${couponServices(preCp)[0]}"]`);
    const det = first && first.closest('details');
    if (det) det.open = true;
  }

  // 初始化：預設選第一個營業日
  buildStrip(minDate);
  let first = parse(minDate);
  for (let i = 0; i < 60 && isClosed(first); i++) first.setDate(first.getDate() + 1);
  selectDate(dateInput.value || iso(first));
})();
