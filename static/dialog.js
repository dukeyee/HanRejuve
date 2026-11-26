// 網站自己的確認／提示視窗（取代瀏覽器的 confirm / alert，內建預覽瀏覽器也能使用）
//
// 用法：
//   <form data-confirm="確定要…？">              送出前詢問
//   <button data-confirm="確定要…？">             按這個按鈕送出前詢問
//   hrConfirm('訊息', {danger: true}).then(ok => …)
//   hrAlert('訊息')
(function () {
  const T = window.T || (s => s);
  let box;

  function build() {
    box = document.createElement('div');
    box.className = 'modal';
    box.hidden = true;
    box.setAttribute('role', 'alertdialog');
    box.setAttribute('aria-modal', 'true');
    box.innerHTML =
      '<div class="modal-box">' +
      '<div class="modal-icon"></div>' +
      '<h2 class="dlg-title"></h2>' +
      '<p class="notice-text dlg-msg"></p>' +
      '<div class="actions modal-actions">' +
      '<button type="button" class="btn ghost dlg-cancel"></button>' +
      '<button type="button" class="btn dlg-ok"></button>' +
      '</div></div>';
    document.body.appendChild(box);
  }

  function dialog(message, opts) {
    opts = opts || {};
    if (!box) build();
    const alertOnly = !!opts.alertOnly;
    const okBtn = box.querySelector('.dlg-ok');
    const cancelBtn = box.querySelector('.dlg-cancel');
    box.querySelector('.modal-icon').textContent = alertOnly ? '!' : '?';
    box.querySelector('.dlg-title').textContent = opts.title || (alertOnly ? T('提示') : T('請確認'));
    box.querySelector('.dlg-msg').textContent = message;
    okBtn.textContent = opts.ok || T('確定');
    cancelBtn.textContent = opts.cancel || T('取消');
    cancelBtn.hidden = alertOnly;
    okBtn.classList.toggle('danger-solid', !!opts.danger);
    const before = document.activeElement;

    return new Promise(resolve => {
      function done(result) {
        box.hidden = true;
        document.body.style.overflow = '';
        okBtn.onclick = cancelBtn.onclick = box.onclick = null;
        document.removeEventListener('keydown', onKey);
        if (before && before.focus) before.focus();
        resolve(result);
      }
      function onKey(e) {
        if (e.key === 'Escape') done(false);
        if (e.key === 'Enter' && document.activeElement === okBtn) { e.preventDefault(); done(true); }
      }
      okBtn.onclick = () => done(true);
      cancelBtn.onclick = () => done(false);
      box.onclick = e => { if (e.target === box) done(false); };
      document.addEventListener('keydown', onKey);
      box.hidden = false;
      document.body.style.overflow = 'hidden';
      (alertOnly ? okBtn : cancelBtn).focus();
    });
  }

  window.hrConfirm = (message, opts) => dialog(message, opts);
  window.hrAlert = (message, opts) => dialog(message, Object.assign({ alertOnly: true }, opts));

  // 表單或送出按鈕上有 data-confirm 時，先詢問再送出
  document.addEventListener('submit', e => {
    const form = e.target;
    if (form.dataset.confirmed === '1') return;
    const submitter = e.submitter;
    const message = (submitter && submitter.dataset.confirm) || form.dataset.confirm;
    if (!message) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const danger = !!((submitter && submitter.classList.contains('danger')) ||
                      (!submitter && form.querySelector('button.danger')));
    window.hrConfirm(message, { danger }).then(ok => {
      if (!ok) return;
      form.dataset.confirmed = '1';
      try {
        if (form.requestSubmit) form.requestSubmit(submitter || undefined);
        else form.submit();
      } finally {
        delete form.dataset.confirmed;
      }
    });
  }, true);
})();
