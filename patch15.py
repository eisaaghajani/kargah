# -*- coding: utf-8 -*-
# پچ ۱۵: پیوست (عکس فاکتور / PDF) برای هزینه و درآمد با پیش‌نمایش، اشتراک عکس آرشیو، کپی‌رایت، انبار در میانبرها
import os, re, sys, shutil, py_compile

if len(sys.argv) < 2:
    print('مسیر پروژه را بدهید: python patch15.py "D:\\kargah"'); sys.exit(1)
root = os.path.abspath(sys.argv[1])
problems = []


def fail(msg):
    print('✗ ' + msg); sys.exit(1)


def load(rel, alts=()):
    for r in (rel,) + tuple(alts):
        p = os.path.join(root, r)
        if os.path.isfile(p):
            raw = open(p, 'rb').read()
            try:
                txt = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                fail('encoding فایل UTF-8 نیست: ' + r)
            return {'path': p, 'rel': r, 'text': txt.replace('\r\n', '\n'),
                    'bom': raw.startswith(b'\xef\xbb\xbf'), 'crlf': '\r\n' in txt}
    fail('فایل پیدا نشد: ' + rel)


def dump(f):
    t = f['text'].replace('\n', '\r\n') if f['crlf'] else f['text']
    open(f['path'], 'wb').write((b'\xef\xbb\xbf' if f['bom'] else b'') + t.encode('utf-8'))


def sub_once(f, old, new, label):
    n = f['text'].count(old)
    if n != 1:
        problems.append('%s [%s]: لنگر %d بار پیدا شد' % (f['rel'], label, n)); return
    f['text'] = f['text'].replace(old, new)


if os.path.exists(os.path.join(root, 'attachments.py')):
    print('✓ پچ ۱۵ قبلاً اعمال شده است؛ تغییری داده نشد.'); sys.exit(0)

F = {k: load(v) for k, v in dict(models='models.py', tenancy='tenancy.py', archive='archive.py', account='account.py', app='app.py',
        base='templates/base.html', ledger='templates/finance_ledger.html', arch_html='templates/archive.html', acct_html='templates/account.html').items()}
css_f, js_f = load('static/css/app-ui.css', ('app-ui.css',)), load('static/js/app-ui.js')
if '[patch14]' not in css_f['text']:
    fail('ابتدا پچ‌های قبلی (تا ۱۴) را اعمال کنید.')

# آیکون‌های رسمی Font Awesome Free 5 — CC BY 4.0
ICONS3 = {
    'file-pdf': ('0 0 384 512', 'M181.9 256.1c-5-16-4.9-46.9-2-46.9 8.4 0 7.6 36.9 2 46.9zm-1.7 47.2c-7.7 20.2-17.3 43.3-28.4 62.7 18.3-7 39-17.2 62.9-21.9-12.7-9.6-24.9-23.4-34.5-40.8zM86.1 428.1c0 .8 13.2-5.4 34.9-40.2-6.7 6.3-29.1 24.5-34.9 40.2zM248 160h136v328c0 13.3-10.7 24-24 24H24c-13.3 0-24-10.7-24-24V24C0 10.7 10.7 0 24 0h200v136c0 13.2 10.8 24 24 24zm-8 171.8c-20-12.2-33.3-29-42.7-53.8 4.5-18.5 11.6-46.6 6.2-64.2-4.7-29.4-42.4-26.5-47.8-6.8-5 18.3-.4 44.1 8.1 77-11.6 27.6-28.7 64.6-40.8 85.8-.1 0-.1.1-.2.1-27.1 13.9-73.6 44.5-54.5 68 5.6 6.9 16 10 21.5 10 17.9 0 35.7-18 61.1-61.8 25.8-8.5 54.1-19.1 79-23.2 21.7 11.8 47.1 19.5 64 19.5 29.2 0 31.2-32 19.7-43.4-13.9-13.6-54.3-9.7-73.6-7.2zM377 105L279 7c-4.5-4.5-10.6-7-17-7h-6v128h128v-6.1c0-6.3-2.5-12.4-7-16.9zm-74.1 255.3c4.1-2.7-2.5-11.9-42.8-9 37.1 15.8 42.8 9 42.8 9z'),
    'paperclip': ('0 0 448 512', 'M43.246 466.142c-58.43-60.289-57.341-157.511 1.386-217.581L254.392 34c44.316-45.332 116.351-45.336 160.671 0 43.89 44.894 43.943 117.329 0 162.276L232.214 383.128c-29.855 30.537-78.633 30.111-107.982-.998-28.275-29.97-27.368-77.473 1.452-106.953l143.743-146.835c6.182-6.314 16.312-6.422 22.626-.241l22.861 22.379c6.315 6.182 6.422 16.312.241 22.626L171.427 319.927c-4.932 5.045-5.236 13.428-.648 18.292 4.372 4.634 11.245 4.711 15.688.165l182.849-186.851c19.613-20.062 19.613-52.725-.011-72.798-19.189-19.627-49.957-19.637-69.154 0L90.39 293.295c-34.763 35.56-35.299 93.12-1.191 128.313 34.01 35.093 88.985 35.137 123.058.286l172.06-175.999c6.177-6.319 16.307-6.433 22.626-.256l22.877 22.364c6.319 6.177 6.434 16.307.256 22.626l-172.06 175.998c-59.576 60.938-155.943 60.216-214.77-.485z'),
    'share-alt': ('0 0 448 512', 'M352 320c-22.608 0-43.387 7.819-59.79 20.895l-102.486-64.054a96.551 96.551 0 0 0 0-41.683l102.486-64.054C308.613 184.181 329.392 192 352 192c53.019 0 96-42.981 96-96S405.019 0 352 0s-96 42.981-96 96c0 7.158.79 14.13 2.276 20.841L155.79 180.895C139.387 167.819 118.608 160 96 160c-53.019 0-96 42.981-96 96s42.981 96 96 96c22.608 0 43.387-7.819 59.79-20.895l102.486 64.054A96.301 96.301 0 0 0 256 416c0 53.019 42.981 96 96 96s96-42.981 96-96-42.981-96-96-96z'),
    'download': ('0 0 512 512', 'M216 0h80c13.3 0 24 10.7 24 24v168h87.7c17.8 0 26.7 21.5 14.1 34.1L269.7 378.3c-7.5 7.5-19.8 7.5-27.3 0L90.1 226.1c-12.6-12.6-3.7-34.1 14.1-34.1H192V24c0-13.3 10.7-24 24-24zm296 376v112c0 13.3-10.7 24-24 24H24c-13.3 0-24-10.7-24-24V376c0-13.3 10.7-24 24-24h146.7l49 49c20.1 20.1 52.5 20.1 72.6 0l49-49H488c13.3 0 24 10.7 24 24zm-124 88c0-11-9-20-20-20s-20 9-20 20 9 20 20 20 20-9 20-20zm64 0c0-11-9-20-20-20s-20 9-20 20 9 20 20 20 20-9 20-20z'),
}

ATTACHMENTS_PY = r'''# D:\kargah\attachments.py  —  پیوست فاکتور/رسید برای هزینه و درآمد (عکس یا PDF)، با پیش‌نمایش و دانلود
import io
import os
import uuid

import jdatetime
from flask import Blueprint, g, jsonify, request, send_file
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.orm import object_session

from archive import _path, _remove_files, _save_image
from extensions import db
from finance import _err
from models import ArchivePhoto, Expense, FinanceFile, Income

bp = Blueprint('attach', __name__)
KINDS = {'expense': Expense, 'income': Income}
MAX_FILES = 10                       # حداکثر پیوست برای هر هزینه/درآمد
MAX_BYTES = 8 * 1024 * 1024          # حداکثر حجم هر فایل


@event.listens_for(FinanceFile, 'after_delete')
def _queue_delete(mapper, connection, target):
    """فایل‌های روی دیسک بعد از commit پاک می‌شوند (همان سازوکار آرشیو)."""
    s = object_session(target)
    if s is not None:
        s.info.setdefault('trash', []).extend([x for x in (target.filename, target.thumb) if x])


def _fj(f):
    return {'id': f.id, 'name': f.orig_name or 'پیوست', 'kind': f.kind, 'size': f.size_bytes or 0}


def _quota_error(adding):
    limit = current_user.photo_limit
    if limit is None:
        return None
    used = ArchivePhoto.query.count() + FinanceFile.query.count()
    if used + adding > limit:
        return 'سقف فضای عکس و پیوست پلن رایگان (%d فایل) پر می‌شود. برای حذف سقف، پلن حرفه‌ای بگیرید.' % limit
    return None


@bp.app_context_processor
def _inject():
    def files_of(kind, rec_id):
        """پیوست‌های هر ردیفِ لیست (یک‌بار برای کل صفحه از دیتابیس خوانده می‌شود)."""
        cache = g.get('_files_cache')
        if cache is None:
            cache = {'expense': {}, 'income': {}}
            yid = (request.view_args or {}).get('year_id')
            if yid:
                for model, col, key in ((Expense, FinanceFile.expense_id, 'expense'), (Income, FinanceFile.income_id, 'income')):
                    q = FinanceFile.query.join(model, col == model.id).filter(model.farming_year_id == yid).order_by(FinanceFile.id)
                    for f in q:
                        cache[key].setdefault(f.expense_id if key == 'expense' else f.income_id, []).append(_fj(f))
            g._files_cache = cache
        return cache.get(kind, {}).get(rec_id, [])
    return {'files_of': files_of, 'copyright_year': jdatetime.date.today().year}


@bp.route('/api/attachments/<kind>/<int:rec_id>', methods=['GET', 'POST'])
def attachments(kind, rec_id):
    model = KINDS.get(kind)
    if not model:
        return _err('نوع پیوست نامعتبر است.', 404)
    rec = db.session.get(model, rec_id)
    if not rec:
        return _err('ثبت پیدا نشد.', 404)
    if request.method == 'GET':
        return jsonify(success=True, files=[_fj(f) for f in rec.files])

    ups = [u for u in request.files.getlist('files') if u and u.filename]
    if not ups:
        return _err('فایلی انتخاب نشده است.')
    if len(rec.files) + len(ups) > MAX_FILES:
        return _err('حداکثر %d پیوست برای هر ثبت مجاز است.' % MAX_FILES)
    quota = _quota_error(len(ups))
    if quota:
        return _err(quota, 403)

    sub = 'f%d' % rec.farming_year_id          # پوشه‌ی جدا از عکس‌های آرشیو
    written, rows = [], []
    try:
        for u in ups:
            data = u.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('«%s» بزرگ‌تر از ۸ مگابایت است.' % u.filename[:40])
            name = os.path.basename(u.filename)[:150]
            if data[:5] == b'%PDF-':
                rel = '%s/%s.pdf' % (sub, uuid.uuid4().hex)
                os.makedirs(os.path.dirname(_path(rel)), exist_ok=True)
                with open(_path(rel), 'wb') as fh:
                    fh.write(data)
                written.append(rel)
                rows.append(FinanceFile(filename=rel, thumb=None, orig_name=name, kind='pdf', mime='application/pdf', size_bytes=len(data)))
            else:
                u.stream = io.BytesIO(data)
                rel, thumb, size = _save_image(u, sub)      # اعتبارسنجی با Pillow، کوچک‌سازی و بندانگشتی
                written += [rel, thumb]
                rows.append(FinanceFile(filename=rel, thumb=thumb, orig_name=name, kind='image', mime='image/jpeg', size_bytes=size))
        for r in rows:
            setattr(r, 'expense_id' if kind == 'expense' else 'income_id', rec.id)
            db.session.add(r)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        _remove_files(written)
        return _err(str(e))
    return jsonify(success=True, files=[_fj(f) for f in rec.files])


@bp.route('/api/attachments/file/<int:fid>', methods=['DELETE'])
def delete_file(fid):
    f = db.session.get(FinanceFile, fid)
    if not f:
        return _err('پیوست پیدا نشد.', 404)
    db.session.delete(f)
    db.session.commit()
    return jsonify(success=True)


def _serve(fid, thumb):
    f = db.session.get(FinanceFile, fid)
    rel = (f.thumb if thumb else f.filename) if f else None
    if not rel:
        return _err('پیدا نشد.', 404)
    inline_pdf = f.kind == 'pdf' and not thumb
    resp = send_file(_path(rel), mimetype='application/pdf' if inline_pdf else 'image/jpeg',
                     as_attachment=request.args.get('download') == '1',
                     download_name=(f.orig_name or 'attachment') + ('' if (f.orig_name or '').lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.webp')) else ('.pdf' if inline_pdf else '.jpg')))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.cache_control.private = True
    resp.cache_control.max_age = 3600
    return resp


@bp.route('/media/file/<int:fid>')
def file_media(fid):
    return _serve(fid, False)


@bp.route('/media/file/<int:fid>/thumb')
def file_thumb(fid):
    return _serve(fid, True)
'''
ASSETS_CSS = r'''
/* ================= [patch15] پیوست، پیش‌نمایش، کپی‌رایت، نوار پایین ۷‌تایی ================= */
.toast { z-index: 90; }
.app-footer { text-align: center; padding: 18px 12px 10px; font-size: .78rem; color: var(--muted); }
.app-footer a { color: var(--primary); text-decoration: none; }
body.auth-body .app-footer { padding-bottom: 18px; }

@media (max-width: 767.98px) {
    /* نوار پایین با ۷ میانبر (شامل انبار) */
    .app-nav .nav-item { font-size: .7rem; padding: 8px 1px; line-height: 1.25; text-align: center; }
    .app-nav .nav-item i { font-size: 1.4rem; }
}

.att-strip { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.att-th {
    width: 46px; height: 46px; padding: 0; border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
    display: grid; place-items: center; background: var(--bg); color: var(--red); cursor: pointer; font-size: 1.3rem;
}
.att-th img { width: 100%; height: 100%; object-fit: cover; display: block; }
.att-more { align-self: center; font-size: .78rem; color: var(--muted); }
.att-chip { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg); font-size: .85rem; }
.att-chip span { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.att-field input[type=file] { width: 100%; }

dialog.modal.viewer:not(.sm):not(.cal)[open] { display: block; width: min(940px, 96vw); padding: 12px; }
.v-head { display: flex; align-items: center; gap: 10px; justify-content: space-between; margin-bottom: 8px; }
.v-head strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.v-body { height: 68vh; display: grid; place-items: center; overflow: auto; border-radius: 12px; background: var(--bg); }
.v-body img { max-width: 100%; max-height: 100%; object-fit: contain; }
.v-body iframe { width: 100%; height: 100%; border: 0; }
.v-foot { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; justify-content: center; }
.lb-bar { position: absolute; bottom: 18px; left: 0; right: 0; display: flex; gap: 10px; justify-content: center; z-index: 3; }
.lb-bar button { padding: 9px 18px; border: 0; border-radius: 999px; background: rgba(255, 255, 255, .92); color: #1f2933; cursor: pointer; font-size: .9rem; }

/* روی موبایل، کپی‌رایت زیر دکمه‌ی شناور نرود */
@media (max-width: 767.98px) {
    body:not(.auth-body) .app-footer { padding-bottom: 84px; }
}
'''
ASSETS_JS = r'''
/* [patch15] اشتراک‌گذاری/دانلود فایل و پیش‌نمایش پیوست‌ها */
(function () {
    var ui = window.ui;
    function download(url, name) {
        var a = document.createElement('a'); a.href = url; a.download = name || ''; document.body.appendChild(a); a.click(); a.remove();
    }
    // اشتراک‌گذاری با منوی خود گوشی (Web Share)؛ اگر مرورگر/آدرس پشتیبانی نکند، فایل دانلود می‌شود
    // (Web Share فقط روی HTTPS یا localhost کار می‌کند)
    ui.shareFile = async function (url, name, title) {
        try {
            var r = await fetch(url, {credentials: 'same-origin'}), blob = await r.blob();
            var file = new File([blob], name, {type: blob.type});
            if (navigator.canShare && navigator.canShare({files: [file]})) { await navigator.share({files: [file], title: title || name}); return true; }
        } catch (e) { if (e && e.name === 'AbortError') return false; }
        download(url, name);
        ui.toast('اشتراک‌گذاری مستقیم در این مرورگر/آدرس ممکن نیست؛ فایل دانلود شد.');
        return false;
    };
    ui.downloadFile = download;

    // items: [{url, kind: 'image'|'pdf', name, remove?: async fn}]
    ui.viewer = function (items, index) {
        if (!items.length) return;
        var i = Math.min(Math.max(index || 0, 0), items.length - 1), dlg = document.createElement('dialog');
        dlg.className = 'modal viewer'; document.body.appendChild(dlg);
        function btn(cls, html, fn) { var b = document.createElement('button'); b.type = 'button'; b.className = cls; b.innerHTML = html; b.onclick = fn; return b; }
        function render() {
            var it = items[i]; dlg.innerHTML = '';
            var head = document.createElement('div'); head.className = 'v-head';
            var t = document.createElement('strong'); t.textContent = it.name + (items.length > 1 ? '  (' + (i + 1) + ' از ' + items.length + ')' : '');
            head.appendChild(t); head.appendChild(btn('icon-sm', '<i class="fas fa-times"></i>', function () { dlg.close(); }));
            var body = document.createElement('div'); body.className = 'v-body';
            if (it.kind === 'pdf') { var f = document.createElement('iframe'); f.src = it.url; f.title = it.name; body.appendChild(f); }
            else { var im = document.createElement('img'); im.src = it.url; im.alt = it.name; body.appendChild(im); }
            var foot = document.createElement('div'); foot.className = 'v-foot';
            if (items.length > 1) {
                foot.appendChild(btn('btn-sm secondary', 'قبلی', function () { i = (i - 1 + items.length) % items.length; render(); }));
                foot.appendChild(btn('btn-sm secondary', 'بعدی', function () { i = (i + 1) % items.length; render(); }));
            }
            foot.appendChild(btn('btn-sm', '<i class="fas fa-share-alt"></i> اشتراک', function () { ui.shareFile(it.url, it.name, it.name); }));
            foot.appendChild(btn('btn-sm secondary', '<i class="fas fa-download"></i> دانلود', function () { download(it.url + (it.url.indexOf('blob:') === 0 ? '' : '?download=1'), it.name); }));
            if (it.kind === 'pdf') { var a = document.createElement('a'); a.className = 'btn-sm secondary'; a.href = it.url; a.target = '_blank'; a.rel = 'noopener'; a.textContent = 'باز کردن در تب جدید'; foot.appendChild(a); }
            if (it.remove) foot.appendChild(btn('btn-sm secondary', '<i class="fas fa-trash"></i> حذف', async function () { dlg.close(); await it.remove(); }));
            dlg.appendChild(head); dlg.appendChild(body); dlg.appendChild(foot);
        }
        dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
        dlg.addEventListener('close', function () { dlg.remove(); });
        render(); dlg.showModal();
    };
})();
'''

enc = lambda s: s.replace('<', '%3C').replace('>', '%3E').replace('#', '%23')
ICON_CSS = '\n/* ---- آیکون‌های جدید ---- */\n' + ', '.join('.fa-%s::before' % n for n in ICONS3) + ' {\n    content: ""; display: inline-block; width: 1em; height: 1em; vertical-align: -.14em; background-color: currentColor;\n    -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; -webkit-mask-position: center; mask-position: center; -webkit-mask-size: contain; mask-size: contain;\n}\n'
for n, (vb, d) in ICONS3.items():
    url = 'url("data:image/svg+xml,%%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'%s\'%%3E%%3Cpath d=\'%s\'/%%3E%%3C/svg%%3E")' % (vb, enc(d))
    ICON_CSS += '.fa-%s::before { -webkit-mask-image: %s; mask-image: %s; }\n' % (n, url, url)

# ---- models.py ----
sub_once(F['models'], "# ==================== انبار سم و کود ====================",
'''# ==================== پیوست هزینه/درآمد ====================
class FinanceFile(db.Model):
    """پیوست (عکس فاکتور یا PDF) برای یک هزینه یا یک درآمد؛ دقیقاً یکی از expense_id / income_id پر است."""
    __tablename__ = 'finance_files'
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=True)
    income_id = db.Column(db.Integer, db.ForeignKey('incomes.id'), nullable=True)
    filename = db.Column(db.String(200), nullable=False)
    thumb = db.Column(db.String(200), nullable=True)
    orig_name = db.Column(db.String(200), default='')
    kind = db.Column(db.String(10), default='image')       # image | pdf
    mime = db.Column(db.String(50), default='')
    size_bytes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    expense = db.relationship('Expense', backref=db.backref('files', cascade='all, delete-orphan'))
    income = db.relationship('Income', backref=db.backref('files', cascade='all, delete-orphan'))


# ==================== انبار سم و کود ====================''', 'FinanceFile model')

# ---- tenancy.py ----
t = F['tenancy']
sub_once(t, "from sqlalchemy import event, func, select", "from sqlalchemy import event, func, or_, select", 'tenancy or_')
sub_once(t, "Income, IncomeType, Material, MaterialInvoice, MaterialPurchase, StockAdjustment, User, WorkMaterial, Workshop)",
         "FinanceFile, Income, IncomeType, Material, MaterialInvoice, MaterialPurchase, StockAdjustment, User, WorkMaterial, Workshop)", 'tenancy import')
sub_once(t, "    mt = select(t(Material).id).where(t(Material).workshop_id.in_(ws))\n",
         "    mt = select(t(Material).id).where(t(Material).workshop_id.in_(ws))\n"
         "    ex = select(t(Expense).id).where(t(Expense).farming_year_id.in_(yr))\n"
         "    ic = select(t(Income).id).where(t(Income).farming_year_id.in_(yr))\n", 'tenancy subqueries')
sub_once(t, "        (StockAdjustment, StockAdjustment.material_id.in_(mt)),\n",
         "        (StockAdjustment, StockAdjustment.material_id.in_(mt)),\n"
         "        (FinanceFile, or_(FinanceFile.expense_id.in_(ex), FinanceFile.income_id.in_(ic))),\n", 'tenancy criteria')

# ---- سقف فضای فایل: عکس‌های آرشیو + پیوست‌ها ----
a = F['archive']
n = a['text'].count('ArchivePhoto.query.count()')
if n < 1:
    problems.append('archive.py: شمارش عکس‌ها پیدا نشد')
else:
    a['text'] = a['text'].replace('ArchivePhoto.query.count()', '(ArchivePhoto.query.count() + _fin_count())')
    a['text'] = a['text'].rstrip('\n') + '\n\n\ndef _fin_count():\n    """تعداد پیوست‌های هزینه/درآمد (در سقف فضای عکس پلن حساب می‌شود)."""\n    from models import FinanceFile\n    return FinanceFile.query.count()\n'
sub_once(F['account'], "from models import ArchivePhoto, License, User, Workshop, ensure_columns, seed_missing_defaults",
         "from models import ArchivePhoto, FinanceFile, License, User, Workshop, ensure_columns, seed_missing_defaults", 'account import')
sub_once(F['account'], "used=ArchivePhoto.query.count()", "used=ArchivePhoto.query.count() + FinanceFile.query.count()", 'account used')
if 'عکس‌های آرشیو' in F['acct_html']['text']:
    F['acct_html']['text'] = F['acct_html']['text'].replace('عکس‌های آرشیو', 'عکس‌ها و پیوست‌ها')
else:
    problems.append('account.html: برچسب «عکس‌های آرشیو» پیدا نشد')

sub_once(F['app'], "# [next-blueprints]", "from attachments import bp as attach_bp\napp.register_blueprint(attach_bp)\n# [next-blueprints]", 'blueprint')

# ---- base.html: کپی‌رایت در همه‌ی صفحه‌ها، انبار در نوار میانبر ----
b = F['base']
sub_once(b, "<script src=\"{{ url_for('static', filename='js/app-ui.js') }}\"></script>",
         '<footer class="app-footer">© {{ copyright_year }} شرکت پارسه پردازشگر رایکاتاک · <a href="https://www.pprt.ir" target="_blank" rel="noopener">www.pprt.ir</a></footer>\n'
         "<script src=\"{{ url_for('static', filename='js/app-ui.js') }}\"></script>", 'footer')
sub_once(b, "('finance.settings_page', 'manage.manage_page', 'inventory.inventory_page')", "('finance.settings_page', 'manage.manage_page')", 'bottom nav')

# ---- لیست و فرم هزینه/درآمد ----
l = F['ledger']
sub_once(l, "            {% if it.description %}<div class=\"li-desc\">{{ it.description }}</div>{% endif %}\n",
 "            {% if it.description %}<div class=\"li-desc\">{{ it.description }}</div>{% endif %}\n"
 "            {% set fl = files_of('income' if is_income else 'expense', it.id) %}\n"
 "            {% if fl %}<div class=\"att-strip\">{% for f in fl[:6] %}<button type=\"button\" class=\"att-th\" data-item=\"{{ it.id }}\" data-fid=\"{{ f.id }}\" data-kind=\"{{ f.kind }}\" data-name=\"{{ f.name }}\" title=\"{{ f.name }}\" onclick=\"openAtt({{ it.id }}, {{ f.id }})\">"
 "{% if f.kind == 'image' %}<img src=\"/media/file/{{ f.id }}/thumb\" alt=\"\" loading=\"lazy\">{% else %}<i class=\"fas fa-file-pdf\"></i>{% endif %}</button>{% endfor %}"
 "{% if fl|length > 6 %}<span class=\"att-more\">+{{ fl|length - 6 }}</span>{% endif %}</div>{% endif %}\n", 'list thumbs')
sub_once(l, '    <div id="fErr" class="alert" hidden></div>',
 '    <div class="field att-field"><span><i class="fas fa-paperclip"></i> پیوست (عکس فاکتور یا PDF، حداکثر ۱۰ فایل، هر کدام ۸ مگابایت)</span>\n'
 '        <input type="file" id="fFiles" accept="image/*,application/pdf" multiple>\n'
 '        <div id="fNew" class="att-strip"></div><div id="fExisting" class="att-strip"></div></div>\n'
 '    <div id="fErr" class="alert" hidden></div>', 'form file field')
sub_once(l, "$('formDlg').showModal();", "resetFiles(item);\n        $('formDlg').showModal();", 'open form hook')
sub_once(l, "if (res.success) { location.reload(); return; }",
 "if (res.success) {\n"
 "            const fl = $('fFiles').files;\n"
 "            if (fl.length) {\n"
 "                const up = await uploadFiles(editId || res.id, fl);\n"
 "                if (!up.success) { $('fErr').textContent = 'ثبت شد، ولی پیوست‌ها ذخیره نشد: ' + (up.error || ''); $('fErr').hidden = false; await new Promise(r => setTimeout(r, 2600)); }\n"
 "            }\n"
 "            location.reload(); return;\n"
 "        }", 'save uploads')
ATT_JS = r'''const ATT_KIND = '{{ 'income' if is_income else 'expense' }}';
    function attItems(itemId) {
        return [...document.querySelectorAll('.att-th[data-item="' + itemId + '"]')].map(b => ({
            id: +b.dataset.fid, url: '/media/file/' + b.dataset.fid, kind: b.dataset.kind, name: b.dataset.name,
            remove: () => removeAtt(+b.dataset.fid)
        }));
    }
    function openAtt(itemId, fid) { const items = attItems(itemId); ui.viewer(items, Math.max(0, items.findIndex(x => x.id === fid))); }
    async function removeAtt(fid) {
        if (!await ui.confirm('این پیوست حذف شود؟', {danger: true})) return;
        const r = await ui.call('DELETE', '/api/attachments/file/' + fid);
        if (r.success) location.reload(); else ui.toast(r.error || 'حذف نشد.', true);
    }
    async function uploadFiles(recId, files) {
        const fd = new FormData(); [...files].forEach(f => fd.append('files', f));
        try { return await (await fetch('/api/attachments/' + ATT_KIND + '/' + recId, {method: 'POST', body: fd})).json(); }
        catch (e) { return {success: false, error: 'ارتباط با سرور برقرار نشد.'}; }
    }
    function renderExisting(files) {
        const box = $('fExisting'); box.innerHTML = '';
        files.forEach((f, i) => {
            const c = document.createElement('div'); c.className = 'att-chip';
            const n = document.createElement('span'); n.textContent = f.name; n.onclick = () => ui.viewer(files.map(x => ({url: '/media/file/' + x.id, kind: x.kind, name: x.name})), i);
            const d = document.createElement('button'); d.type = 'button'; d.className = 'icon-sm danger'; d.innerHTML = '<i class="fas fa-trash"></i>'; d.title = 'حذف پیوست';
            d.onclick = async () => { if (!await ui.confirm('این پیوست حذف شود؟', {danger: true})) return; const r = await ui.call('DELETE', '/api/attachments/file/' + f.id); if (r.success) { files.splice(i, 1); renderExisting(files); } else ui.toast(r.error || 'حذف نشد.', true); };
            c.append(n, d); box.appendChild(c);
        });
    }
    async function resetFiles(item) {
        $('fFiles').value = ''; $('fNew').innerHTML = ''; $('fExisting').innerHTML = '';
        if (!item) return;
        const r = await ui.call('GET', '/api/attachments/' + ATT_KIND + '/' + item.id);
        if (r.success) renderExisting(r.files);
    }
    $('fFiles').addEventListener('change', () => {
        const box = $('fNew'); box.innerHTML = ''; const list = [...$('fFiles').files];
        const items = list.map(f => ({url: URL.createObjectURL(f), kind: f.type === 'application/pdf' ? 'pdf' : 'image', name: f.name}));
        items.forEach((it, i) => {
            const b = document.createElement('button'); b.type = 'button'; b.className = 'att-th'; b.title = it.name;
            if (it.kind === 'image') { const im = document.createElement('img'); im.src = it.url; im.alt = ''; b.appendChild(im); } else b.innerHTML = '<i class="fas fa-file-pdf"></i>';
            b.onclick = () => ui.viewer(items, i); box.appendChild(b);
        });
    });
    async function del(id) {'''
sub_once(l, "async function del(id) {", ATT_JS, 'ledger js')

# ---- آرشیو: اشتراک و دانلود عکس ----
ah = F['arch_html']['text']
m = re.search(r'(<img id="lbImg"[^>]*>)(.*?)(</div>)', ah, re.S)
if not m:
    problems.append('archive.html: لایت‌باکس پیدا نشد')
else:
    bar = ('\n    <div class="lb-bar"><button type="button" onclick="event.stopPropagation(); shareLb()"><i class="fas fa-share-alt"></i> اشتراک</button>'
           '<button type="button" onclick="event.stopPropagation(); dlLb()"><i class="fas fa-download"></i> دانلود</button></div>\n')
    ah = ah[:m.end(2)] + bar + ah[m.end(2):]
    k = ah.rfind('</script>')
    if k < 0:
        problems.append('archive.html: تگ script پیدا نشد')
    else:
        ah = ah[:k] + ("    // اشتراک‌گذاری/دانلود عکسِ بازشده\n"
                       "    function lbUrl() { return document.getElementById('lbImg').getAttribute('src'); }\n"
                       "    function shareLb() { const u = lbUrl(); ui.shareFile(u, 'kargah-photo-' + u.replace(/\\D+/g, '') + '.jpg', 'عکس آرشیو'); }\n"
                       "    function dlLb() { const u = lbUrl(); ui.downloadFile(u, 'kargah-photo-' + u.replace(/\\D+/g, '') + '.jpg'); }\n") + ah[k:]
        F['arch_html']['text'] = ah

css_f['text'] = css_f['text'].rstrip('\n') + '\n' + ASSETS_CSS + ICON_CSS
js_f['text'] = js_f['text'].rstrip('\n') + '\n' + ASSETS_JS

if problems:
    print('✗ هیچ فایلی تغییر نکرد:')
    for p in problems: print('  - ' + p)
    sys.exit(1)

bdir = os.path.join(root, '_backup_patch15')
allf = list(F.values()) + [css_f, js_f]
for f in allf:
    dst = os.path.join(bdir, f['rel'])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copy2(f['path'], dst)
db_file = os.path.join(root, 'instance', 'database.db')
if os.path.isfile(db_file) and not os.path.exists(os.path.join(bdir, 'instance', 'database.db')):
    os.makedirs(os.path.join(bdir, 'instance'), exist_ok=True)
    shutil.copy2(db_file, os.path.join(bdir, 'instance', 'database.db'))
for f in allf:
    dump(f)
open(os.path.join(root, 'attachments.py'), 'w', encoding='utf-8', newline='\n').write(ATTACHMENTS_PY)
for rel in ('models.py', 'tenancy.py', 'archive.py', 'account.py', 'app.py', 'attachments.py'):
    py_compile.compile(os.path.join(root, rel), doraise=True)
print('✓ پچ ۱۵ اعمال شد. پشتیبان: ' + bdir)
print('  پیوست هزینه/درآمد، اشتراک عکس آرشیو، کپی‌رایت و میانبر انبار اضافه شد.')
