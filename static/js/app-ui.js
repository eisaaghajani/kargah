/* static/js/app-ui.js — [patch5] ابزارهای مشترک همه‌ی صفحات (فقط فضای نام window.ui) */
(function () {
    var ui = window.ui = {};

    // تبدیل ارقام فارسی/عربی و حذف جداکننده‌ها
    ui.norm = function (s) {
        return String(s == null ? '' : s)
            .replace(/[۰-۹]/g, function (c) { return c.charCodeAt(0) - 1776; })
            .replace(/[٠-٩]/g, function (c) { return c.charCodeAt(0) - 1632; })
            .replace(/[,،\s]/g, '').replace('٫', '.');
    };
    // 1234567 -> 1,234,567
    ui.fmt = function (s) {
        var n = ui.norm(s).replace(/[^\d]/g, '');
        return n ? Number(n).toLocaleString('en-US') : '';
    };
    // ورودی پول: هنگام تایپ، سه‌رقم‌سه‌رقم جدا می‌شود
    ui.money = function (el) {
        if (typeof el === 'string') el = document.getElementById(el);
        if (el) el.addEventListener('input', function () { el.value = ui.fmt(el.value); });
    };

    // درخواست JSON؛ همیشه {success, error} برمی‌گرداند
    ui.call = function (method, url, body) {
        return fetch(url, {
            method: method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)
        }).then(function (r) {
            return r.json().catch(function () { return {success: false, error: 'خطای ارتباط با سرور'}; });
        }).catch(function () { return {success: false, error: 'اتصال برقرار نشد.'}; });
    };

    var toastEl, toastTimer;
    ui.toast = function (msg, bad) {
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.setAttribute('role', 'status');
            document.body.appendChild(toastEl);
        }
        // پیام باید داخل دیالوگِ بازِ فعلی نمایش داده شود، وگرنه زیر آن پنهان می‌ماند
        var host = document.querySelector('dialog[open]') || document.body;
        if (toastEl.parentNode !== host) host.appendChild(toastEl);
        toastEl.textContent = msg;
        toastEl.className = 'toast' + (bad ? ' bad' : '');
        toastEl.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toastEl.hidden = true; }, bad ? 3600 : 2200);
    };

    // پنجره‌ی تأیید یکدست (جایگزین confirm و alert مرورگر)
    ui.confirm = function (message, opts) {
        opts = opts || {};
        return new Promise(function (resolve) {
            var d = document.createElement('dialog');
            d.className = 'modal sm';
            var h = document.createElement('div'); h.className = 'modal-head';
            var t = document.createElement('h3'); t.textContent = opts.title || (opts.danger ? 'حذف' : 'تأیید'); h.appendChild(t);
            var p = document.createElement('p'); p.textContent = message; p.style.margin = '0 0 4px';
            var row = document.createElement('div'); row.className = 'btn-row';
            var no = document.createElement('button'); no.type = 'button'; no.className = 'btn secondary'; no.textContent = 'انصراف';
            var ok = document.createElement('button'); ok.type = 'button'; ok.className = 'btn' + (opts.danger ? ' danger' : ''); ok.textContent = opts.ok || (opts.danger ? 'حذف' : 'تأیید');
            row.appendChild(no); row.appendChild(ok);
            d.appendChild(h); d.appendChild(p); d.appendChild(row);
            document.body.appendChild(d);
            var result = false;
            ok.onclick = function () { result = true; d.close(); };
            no.onclick = function () { d.close(); };
            d.addEventListener('click', function (e) { if (e.target === d) d.close(); });
            d.addEventListener('close', function () { d.remove(); resolve(result); });
            d.showModal();
        });
    };

    // بستن دیالوگ با کلیک روی پس‌زمینه
    ui.backdropClose = function (dlg) {
        if (typeof dlg === 'string') dlg = document.getElementById(dlg);
        if (dlg) dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    };
})();

/* [patch8] تقویم شمسی برای همه‌ی فیلدهای تاریخ (بدون وابستگی به کتابخانه‌ی بیرونی) */
(function () {
    var ui = window.ui;

    // ---------- تبدیل شمسی ↔ میلادی (الگوریتم jalaali-js) ----------
    var BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
    function div(a, b) { return ~~(a / b); }
    function mod(a, b) { return a - ~~(a / b) * b; }
    function jalCal(jy, noLeap) {
        var bl = BREAKS.length, gy = jy + 621, leapJ = -14, jp = BREAKS[0], jm, jump = 0, leap, leapG, march, n, i;
        if (jy < jp || jy >= BREAKS[bl - 1]) throw new Error('سال نامعتبر');
        for (i = 1; i < bl; i += 1) {
            jm = BREAKS[i]; jump = jm - jp;
            if (jy < jm) break;
            leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
            jp = jm;
        }
        n = jy - jp;
        leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
        if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
        leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
        march = 20 + leapJ - leapG;
        if (noLeap) return {gy: gy, march: march};
        if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
        leap = mod(mod(n + 1, 33) - 1, 4);
        if (leap === -1) leap = 4;
        return {leap: leap, gy: gy, march: march};
    }
    function g2d(gy, gm, gd) {
        var d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
        return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
    }
    function d2g(jdn) {
        var j = 4 * jdn + 139361631;
        j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
        var i = div(mod(j, 1461), 4) * 5 + 308;
        var gd = div(mod(i, 153), 5) + 1, gm = mod(div(i, 153), 12) + 1;
        return {gy: div(j, 1461) - 100100 + div(8 - gm, 6), gm: gm, gd: gd};
    }
    function j2d(jy, jm, jd) {
        var r = jalCal(jy, true);
        return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
    }
    function d2j(jdn) {
        var gy = d2g(jdn).gy, jy = gy - 621, r = jalCal(jy, false), k = jdn - g2d(gy, 3, r.march), jm, jd;
        if (k >= 0) {
            if (k <= 185) return {y: jy, m: 1 + div(k, 31), d: mod(k, 31) + 1};
            k -= 186;
        } else {
            jy -= 1; k += 179;
            if (r.leap === 1) k += 1;
        }
        jm = 7 + div(k, 30); jd = mod(k, 30) + 1;
        return {y: jy, m: jm, d: jd};
    }
    function monthLen(y, m) { return m <= 6 ? 31 : (m <= 11 ? 30 : (jalCal(y).leap === 0 ? 30 : 29)); }
    function todayJ() { var n = new Date(); return d2j(g2d(n.getFullYear(), n.getMonth() + 1, n.getDate())); }
    function weekdaySat0(y, m, d) {            // شنبه = 0 ... جمعه = 6
        var g = d2g(j2d(y, m, d));
        return (new Date(Date.UTC(g.gy, g.gm - 1, g.gd)).getUTCDay() + 1) % 7;
    }
    function p2(n) { return (n < 10 ? '0' : '') + n; }
    function fmt(y, m, d) { return y + '/' + p2(m) + '/' + p2(d); }
    function parse(s) {
        var r = /^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/.exec(ui.norm(s));
        if (!r) return null;
        var y = +r[1], m = +r[2], d = +r[3];
        if (y < 1200 || y > 1700 || m < 1 || m > 12 || d < 1 || d > monthLen(y, m)) return null;
        return {y: y, m: m, d: d};
    }
    ui.jalali = {toJalali: function (gy, gm, gd) { return d2j(g2d(gy, gm, gd)); },
                 toGregorian: function (y, m, d) { return d2g(j2d(y, m, d)); },
                 monthLength: monthLen, today: todayJ, format: fmt, parse: parse};

    // ---------- پنجره‌ی تقویم ----------
    var MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
    var WEEK = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
    var dlg;

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    }
    function btn(cls, text, label, onclick) {
        var b = el('button', cls, text); b.type = 'button';
        if (label) b.setAttribute('aria-label', label);
        b.onclick = onclick;
        return b;
    }

    function openCalendar(input) {
        if (!dlg) {
            dlg = el('dialog', 'modal sm cal');
            dlg.setAttribute('aria-label', 'انتخاب تاریخ');
            dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
            document.body.appendChild(dlg);
        }
        var today = todayJ(), sel = parse(input.value), base = sel || today;
        var view = {y: base.y, m: base.m};
        var clearable = input.dataset.jdate === 'clear';

        function choose(y, m, d) {
            input.value = fmt(y, m, d);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            dlg.close();
        }
        function shift(delta) {
            view.m += delta;
            if (view.m < 1) { view.m = 12; view.y -= 1; }
            if (view.m > 12) { view.m = 1; view.y += 1; }
            render();
        }
        function render() {
            dlg.innerHTML = '';
            var head = el('div', 'modal-head');
            head.appendChild(el('h3', null, 'انتخاب تاریخ'));
            var x = btn('icon-sm', '', 'بستن', function () { dlg.close(); });
            x.innerHTML = '<i class="fas fa-times"></i>';
            head.appendChild(x);
            dlg.appendChild(head);

            var nav = el('div', 'cal-head');
            nav.appendChild(btn('cal-nav', '›', 'ماه قبل', function () { shift(-1); }));
            var ms = el('select'); ms.setAttribute('aria-label', 'ماه');
            MONTHS.forEach(function (n, i) { var o = new Option(n, i + 1); o.selected = (i + 1 === view.m); ms.appendChild(o); });
            ms.onchange = function () { view.m = +ms.value; render(); };
            var ys = el('select'); ys.setAttribute('aria-label', 'سال');
            for (var y = Math.min(view.y, today.y) - 20; y <= Math.max(view.y, today.y) + 5; y++) {
                var o = new Option(y, y); o.selected = (y === view.y); ys.appendChild(o);
            }
            ys.onchange = function () { view.y = +ys.value; render(); };
            nav.appendChild(ms); nav.appendChild(ys);
            nav.appendChild(btn('cal-nav', '‹', 'ماه بعد', function () { shift(1); }));
            dlg.appendChild(nav);

            var grid = el('div', 'cal-grid');
            WEEK.forEach(function (w, i) { grid.appendChild(el('div', 'cal-wd' + (i === 6 ? ' fri' : ''), w)); });
            var offset = weekdaySat0(view.y, view.m, 1), len = monthLen(view.y, view.m);
            for (var b = 0; b < offset; b++) grid.appendChild(el('span'));
            for (let d = 1; d <= len; d++) {
                var cls = 'cal-d';
                if ((offset + d - 1) % 7 === 6) cls += ' fri';
                if (sel && sel.y === view.y && sel.m === view.m && sel.d === d) cls += ' sel';
                if (today.y === view.y && today.m === view.m && today.d === d) cls += ' today';
                grid.appendChild(btn(cls, d, null, function () { choose(view.y, view.m, d); }));
            }
            dlg.appendChild(grid);

            var row = el('div', 'btn-row');
            row.appendChild(btn('btn secondary', 'بستن', null, function () { dlg.close(); }));
            if (clearable && input.value) row.appendChild(btn('btn secondary', 'پاک کردن', null, function () {
                input.value = '';
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));
                dlg.close();
            }));
            row.appendChild(btn('btn', 'امروز', null, function () { choose(today.y, today.m, today.d); }));
            dlg.appendChild(row);
        }
        render();
        if (!dlg.open) dlg.showModal();
    }

    // فیلد تاریخ: با لمس، تقویم باز می‌شود (تایپ دستی لازم نیست)
    ui.datepicker = function (input) {
        if (typeof input === 'string') input = document.getElementById(input);
        if (!input || input.dataset.jdateReady) return;
        input.dataset.jdateReady = '1';
        input.readOnly = true;
        input.classList.add('jd-input');
        input.setAttribute('autocomplete', 'off');
        input.addEventListener('click', function () { openCalendar(input); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCalendar(input); }
        });
    };
    function init() { document.querySelectorAll('input[data-jdate]').forEach(function (i) { ui.datepicker(i); }); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

/* [patch11] دکمه‌ی بستنِ دیالوگ با باز شدن، قاب فوکوس نگیرد (ورودی‌ها فوکوس خود را نگه می‌دارند) */
(function () {
    if (typeof HTMLDialogElement === 'undefined') return;
    var orig = HTMLDialogElement.prototype.showModal;
    HTMLDialogElement.prototype.showModal = function () {
        orig.call(this);
        var a = document.activeElement;
        if (a && a !== document.body && this.contains(a) && a.classList && a.classList.contains('icon-sm') && a.blur) a.blur();
    };
})();

/* [patch12] سه فیلد هماهنگ: مقدار، قیمت هر واحد، مبلغ کل — با پر کردن هر دو‌تا، سومی خودکار حساب می‌شود.
   مقدار (وزن/تعداد) ثابت می‌ماند و قیمت واحد از مبلغ کل محاسبه می‌شود؛ مگر اینکه فقط قیمت و مبلغ را بدهید. */
(function () {
    var ui = window.ui;
    ui.link3 = function (q, p, t, onChange) {
        var anchor = 'p';                         // آخرین فیلد «پولی» که کاربر پر کرده: قیمت واحد یا مبلغ کل
        function val(e) { var v = parseFloat(ui.norm(e.value)); return isFinite(v) && v > 0 ? v : 0; }
        function setP(v) { p.value = ui.fmt(String(Math.round(v))); }
        function setT(v) { t.value = ui.fmt(String(Math.round(v))); }
        function setQ(v) { q.value = String(+v.toFixed(3)); }
        function done() { if (onChange) onChange(); }
        q.addEventListener('input', function () {
            var Q = val(q), P = val(p), T = val(t);
            if (Q) { if (anchor === 't' && T) setP(T / Q); else if (P) setT(Q * P); else if (T) setP(T / Q); }
            done();
        });
        p.addEventListener('input', function () {
            anchor = 'p';
            var Q = val(q), P = val(p), T = val(t);
            if (Q && P) setT(Q * P); else if (P && T) setQ(T / P);
            done();
        });
        t.addEventListener('input', function () {
            anchor = 't';
            var Q = val(q), P = val(p), T = val(t);
            if (Q && T) setP(T / Q); else if (P && T) setQ(T / P);
            done();
        });
        return {reset: function () { anchor = 'p'; }};
    };
})();


/* [patch13] دکمه‌ی تمام‌صفحه / خروج از تمام‌صفحه */
(function () {
    var ui = window.ui, de = document.documentElement;
    var req = de.requestFullscreen || de.webkitRequestFullscreen;
    var exitFn = document.exitFullscreen || document.webkitExitFullscreen;
    function active() { return !!(document.fullscreenElement || document.webkitFullscreenElement); }
    function sync() {
        document.querySelectorAll('[data-fs]').forEach(function (b) {
            b.hidden = !req;                       // مثلاً روی آیفون پشتیبانی نمی‌شود؛ دکمه پنهان می‌ماند
            var on = active(), i = b.querySelector('i'), t = b.querySelector('[data-fs-text]');
            if (i) i.className = 'fas ' + (on ? 'fa-compress' : 'fa-expand');
            if (t) t.textContent = on ? 'خروج از تمام‌صفحه' : 'تمام‌صفحه';
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }
    ui.toggleFullscreen = function () {
        if (!req) return ui.toast('این مرورگر تمام‌صفحه را پشتیبانی نمی‌کند.', true);
        var fail = function () { ui.toast('تمام‌صفحه فعال نشد.', true); };
        try { var p = active() ? exitFn.call(document) : req.call(de); if (p && p.catch) p.catch(fail); } catch (e) { fail(); }
    };
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync); else sync();
})();
