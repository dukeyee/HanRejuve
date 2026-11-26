// Email 與馬來西亞手機號碼即時檢查（伺服器端也會再檢查一次）
(function () {
  const EMAIL_RE = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$/;
  const MY_RE = /^1(1\d{8}|[02-9]\d{7})$/;

  function myPhoneOk(v) {
    let s = v.replace(/[\s\-().]/g, '');
    for (const p of ['+60', '60', '0']) { if (s.startsWith(p)) { s = s.slice(p.length); break; } }
    return MY_RE.test(s);
  }

  function hook(input, test, msg) {
    const hint = document.createElement('div');
    hint.className = 'field-error';
    input.closest('.field').appendChild(hint);
    const check = (show) => {
      const v = input.value.trim();
      const bad = v !== '' && !test(v);
      input.setCustomValidity(bad ? msg : '');
      input.classList.toggle('invalid', bad && show);
      hint.textContent = bad && show ? msg : '';
    };
    input.addEventListener('input', () => check(input.classList.contains('invalid')));
    input.addEventListener('blur', () => check(true));
    input.form && input.form.addEventListener('submit', () => check(true));
    check(false);
  }

  document.querySelectorAll('input[type=email]:not([disabled])').forEach(el =>
    hook(el, v => EMAIL_RE.test(v), (window.T || (s => s))('Email 格式不正確，例如 name@gmail.com')));
  document.querySelectorAll('input[data-my-phone]').forEach(el =>
    hook(el, myPhoneOk, (window.T || (s => s))('請輸入馬來西亞手機號碼，例如 12-345 6789')));
})();
