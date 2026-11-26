// 圖片檢視器：點海報後全螢幕顯示，有「返回」按鈕；多張圖可左右切換／滑動
// 用法：<a href="大圖網址" data-viewer='[["網址","標籤"], ...]'>…</a>
(function () {
  const T = window.T || (s => s);
  let box, img, label, prevBtn, nextBtn, dots, list = [], idx = 0, pushed = false;

  function build() {
    box = document.createElement('div');
    box.className = 'viewer';
    box.hidden = true;
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.innerHTML =
      '<div class="viewer-bar">' +
      '<button type="button" class="viewer-back"><span aria-hidden="true">←</span> ' + T('返回') + '</button>' +
      '<span class="viewer-label"></span>' +
      '</div>' +
      '<div class="viewer-stage">' +
      '<button type="button" class="viewer-nav prev" aria-label="' + T('上一張') + '">‹</button>' +
      '<img alt="">' +
      '<button type="button" class="viewer-nav next" aria-label="' + T('下一張') + '">›</button>' +
      '</div>' +
      '<div class="viewer-dots"></div>';
    document.body.appendChild(box);
    img = box.querySelector('img');
    label = box.querySelector('.viewer-label');
    prevBtn = box.querySelector('.prev');
    nextBtn = box.querySelector('.next');
    dots = box.querySelector('.viewer-dots');
    box.querySelector('.viewer-back').onclick = () => close();
    prevBtn.onclick = e => { e.stopPropagation(); show(idx - 1); };
    nextBtn.onclick = e => { e.stopPropagation(); show(idx + 1); };
    box.querySelector('.viewer-stage').addEventListener('click', e => { if (e.target.classList.contains('viewer-stage')) close(); });
    // 手機左右滑動切換
    let x0 = null;
    img.addEventListener('touchstart', e => { x0 = e.touches[0].clientX; }, { passive: true });
    img.addEventListener('touchend', e => {
      if (x0 === null) return;
      const dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1));
      x0 = null;
    });
  }

  function show(i) {
    if (!list.length) return;
    idx = (i + list.length) % list.length;
    img.src = list[idx][0];
    label.textContent = list[idx][1] || '';
    const multi = list.length > 1;
    prevBtn.hidden = nextBtn.hidden = !multi;
    dots.innerHTML = multi ? list.map((_, k) => `<button type="button" class="${k === idx ? 'on' : ''}" data-k="${k}" aria-label="${k + 1}"></button>`).join('') : '';
    dots.querySelectorAll('button').forEach(b => b.onclick = () => show(+b.dataset.k));
  }

  function open(items, start) {
    if (!box) build();
    list = items; show(start || 0);
    box.hidden = false;
    document.body.style.overflow = 'hidden';
    history.pushState({ viewer: true }, '');   // 讓手機的「返回」鍵也能關閉
    pushed = true;
    box.querySelector('.viewer-back').focus();
  }

  function close(fromPop) {
    if (!box || box.hidden) return;
    box.hidden = true;
    img.removeAttribute('src');
    document.body.style.overflow = '';
    if (pushed && !fromPop) history.back();
    pushed = false;
  }

  window.addEventListener('popstate', () => close(true));
  document.addEventListener('keydown', e => {
    if (!box || box.hidden) return;
    if (e.key === 'Escape') close();
    if (e.key === 'ArrowLeft') show(idx - 1);
    if (e.key === 'ArrowRight') show(idx + 1);
  });
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-viewer]');
    if (!a) return;
    e.preventDefault();
    let items;
    try { items = JSON.parse(a.dataset.viewer); } catch (_) { items = [[a.getAttribute('href'), '']]; }
    open(items, +a.dataset.viewerStart || 0);
  });
})();
