# D:\kargah\account.py  —  حساب کاربری، کارگاه‌ها، پلن و لایسنس، پشتیبان‌گیری و بازیابی
import hashlib
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta

import click
import jdatetime
from flask import Blueprint, after_this_request, jsonify, render_template, request, send_file
from flask.cli import with_appcontext
from flask_login import current_user
from sqlalchemy import func

from extensions import db
from models import ArchivePhoto, License, User, Workshop, ensure_columns, seed_missing_defaults
from tenancy import adopt_orphans

bp = Blueprint('account', __name__)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'          # بدون O/0/I/1 تا اشتباه خوانده نشود
REQUIRED_TABLES = {'users', 'workshops', 'farming_years', 'activities', 'materials', 'daily_works', 'work_materials'}
MAX_UNPACKED = 2 * 1024 ** 3
_fails = defaultdict(list)       # (نوع، کاربر) -> زمان تلاش‌های ناموفق


# ---------------------------------------------------------------- ابزارها
def _ok(**kw):
    return jsonify(dict(success=True, **kw))


def _bad(msg, code=400):
    return jsonify({'success': False, 'error': msg}), code


def _body():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def _throttled(kind):
    now = time.time()
    key = (kind, current_user.id)
    _fails[key] = [t for t in _fails[key] if now - t < 600]
    return len(_fails[key]) >= 5


def _record_fail(kind):
    _fails[(kind, current_user.id)].append(time.time())


def _need_password(d):
    if _throttled('pw'):
        return _bad('تلاش ناموفق زیاد بود؛ چند دقیقه بعد دوباره امتحان کنید.', 429)
    if not current_user.check_password(d.get('current_password') or ''):
        _record_fail('pw')
        return _bad('رمز عبور فعلی درست نیست.', 403)
    _fails.pop(('pw', current_user.id), None)
    return None


def is_owner():
    """مالک برنامه = قدیمی‌ترین کاربر؛ فقط او به پشتیبان و بازیابی کل برنامه دسترسی دارد."""
    first = db.session.query(func.min(User.id)).scalar()
    return current_user.is_authenticated and current_user.id == first


def _jdate(dt):
    return jdatetime.date.fromgregorian(date=dt.date()).strftime('%Y/%m/%d')


@bp.record_once
def _register_cli(state):
    for cmd in (reset_password, make_license, list_licenses, restore_cmd):
        state.app.cli.add_command(cmd)


# ---------------------------------------------------------------- صفحه
@bp.route('/account')
def account_page():
    now = datetime.now()
    plan = current_user.effective_plan
    exp = current_user.plan_expires_at
    info = {'plan': plan, 'lifetime': plan == 'pro' and exp is None, 'expires': None, 'days_left': None, 'expired': False}
    if plan == 'pro' and exp:
        info['expires'] = _jdate(exp)
        info['days_left'] = max((exp - now).days, 0)
    elif current_user.plan == 'pro' and exp and exp < now:
        info['expired'] = True
        info['expires'] = _jdate(exp)
    return render_template('account.html', workshops=Workshop.query.order_by(Workshop.id).all(),
                           used=ArchivePhoto.query.count(), limit=current_user.photo_limit, info=info, owner=is_owner())


# ---------------------------------------------------------------- مشخصات و رمز
@bp.route('/api/account/profile', methods=['PUT'])
def update_profile():
    d = _body()
    err = _need_password(d)
    if err:
        return err
    name = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip().lower() or None
    if not name:
        return _bad('نام کاربری را وارد کنید.')
    if len(name) > 100:
        return _bad('نام کاربری نباید بیش از ۱۰۰ حرف باشد.')
    if '@' in name and name != current_user.name:
        return _bad('نام کاربری نباید @ داشته باشد.')
    if email and not EMAIL_RE.match(email):
        return _bad('ایمیل معتبر نیست.')
    if User.query.filter(User.id != current_user.id, func.lower(User.name) == name.lower()).first():
        return _bad('این نام کاربری قبلاً استفاده شده است.')
    if email and User.query.filter(User.id != current_user.id, func.lower(User.email) == email).first():
        return _bad('این ایمیل قبلاً استفاده شده است.')
    if email != current_user.email:
        current_user.email_verified = False
    current_user.name, current_user.email = name, email
    db.session.commit()
    return _ok()


@bp.route('/api/account/password', methods=['PUT'])
def change_password():
    d = _body()
    err = _need_password(d)
    if err:
        return err
    new = d.get('new_password') or ''
    if len(new) < 6:
        return _bad('رمز جدید باید حداقل ۶ کاراکتر باشد.')
    if new != d.get('repeat_password'):
        return _bad('تکرار رمز جدید یکسان نیست.')
    if new == (d.get('current_password') or ''):
        return _bad('رمز جدید باید با رمز فعلی فرق داشته باشد.')
    current_user.set_password(new)
    db.session.commit()
    return _ok()


# ---------------------------------------------------------------- کارگاه‌ها
@bp.route('/api/workshop/<int:workshop_id>', methods=['PUT'])
def rename_workshop(workshop_id):
    w = db.session.get(Workshop, workshop_id)
    if not w:
        return _bad('کارگاه پیدا نشد.', 404)
    name = (_body().get('name') or '').strip()
    if not name:
        return _bad('نام کارگاه را وارد کنید.')
    if len(name) > 100:
        return _bad('نام کارگاه نباید بیش از ۱۰۰ حرف باشد.')
    w.name = name
    db.session.commit()
    return _ok()


@bp.route('/api/workshop/<int:workshop_id>', methods=['DELETE'])
def delete_workshop(workshop_id):
    w = db.session.get(Workshop, workshop_id)
    if not w:
        return _bad('کارگاه پیدا نشد.', 404)
    if (_body().get('confirm_name') or '').strip() != w.name.strip():
        return _bad('نام کارگاه را دقیقاً مثل خودش بنویسید.')
    db.session.delete(w)
    db.session.commit()
    return _ok()


# ---------------------------------------------------------------- لایسنس و پلن حرفه‌ای
def _norm_code(s):
    n = re.sub(r'[^A-Z0-9]', '', (s or '').upper())
    return 'KRG' + n if n and not n.startswith('KRG') and len(n) == 12 else n


def _hash_code(norm):
    return hashlib.sha256(norm.encode()).hexdigest()


def new_license_code():
    body = ''.join(secrets.choice(ALPHABET) for _ in range(12))
    return 'KRG-%s-%s-%s' % (body[:4], body[4:8], body[8:])


@bp.route('/api/account/license', methods=['POST'])
def redeem_license():
    if _throttled('lic'):
        return _bad('تلاش ناموفق زیاد بود؛ چند دقیقه بعد دوباره امتحان کنید.', 429)
    norm = _norm_code(_body().get('code'))
    lic = License.query.filter_by(code_hash=_hash_code(norm)).first() if norm else None
    if not lic or lic.used_by:
        _record_fail('lic')
        return _bad('کد لایسنس معتبر نیست یا قبلاً استفاده شده است.')
    user, now = current_user, datetime.now()
    if user.plan == 'pro' and user.plan_expires_at is None:
        return _bad('پلن حرفه‌ای شما دائمی است و به لایسنس نیازی ندارد.')
    claimed = License.query.filter_by(id=lic.id, used_by=None).update({'used_by': user.id, 'used_at': now})
    if not claimed:
        db.session.rollback()
        return _bad('کد لایسنس معتبر نیست یا قبلاً استفاده شده است.')
    start = user.plan_expires_at if (user.plan == 'pro' and user.plan_expires_at and user.plan_expires_at > now) else now
    user.plan = 'pro'
    user.plan_expires_at = start + timedelta(days=lic.days)
    db.session.commit()
    _fails.pop(('lic', user.id), None)
    return _ok(expires=_jdate(user.plan_expires_at), days=lic.days)


@click.command('make-license')
@click.option('--days', type=int, default=365, show_default=True, help='مدت پلن حرفه‌ای (روز)')
@click.option('--count', type=int, default=1, show_default=True, help='تعداد کد')
@click.option('--note', default='', help='یادداشت (مثلاً نام خریدار)')
@with_appcontext
def make_license(days, count, note):
    """ساخت کد لایسنس یک‌بارمصرف:  flask --app app make-license --days 365 --count 5"""
    if days < 1 or not 1 <= count <= 200:
        raise click.ClickException('days باید مثبت و count بین ۱ تا ۲۰۰ باشد.')
    codes = []
    for _ in range(count):
        code = new_license_code()
        db.session.add(License(code_hash=_hash_code(_norm_code(code)), hint=code[-4:], days=days, note=note[:100]))
        codes.append(code)
    db.session.commit()
    click.echo('کدها (فقط همین یک بار نمایش داده می‌شوند؛ جایی ذخیره کنید):')
    for c in codes:
        click.echo('  ' + c)


@click.command('list-licenses')
@with_appcontext
def list_licenses():
    """فهرست لایسنس‌ها و وضعیت مصرفشان."""
    rows = License.query.order_by(License.id).all()
    if not rows:
        click.echo('هنوز لایسنسی ساخته نشده است.')
    for r in rows:
        who = ''
        if r.used_by:
            u = db.session.get(User, r.used_by)
            who = '  ← مصرف‌شده توسط «%s» در %s' % (u.name if u else r.used_by, _jdate(r.used_at))
        click.echo('#%d  ...%s  %d روز  %s%s' % (r.id, r.hint, r.days, r.note or '', who or '  (استفاده‌نشده)'))


# ---------------------------------------------------------------- پشتیبان‌گیری
def _write_backup_zip(dest):
    """یک zip شامل نسخه‌ی یکدستِ دیتابیس و همه‌ی عکس‌ها در مسیر dest می‌سازد."""
    db_path = db.engine.url.database
    with tempfile.TemporaryDirectory() as td:
        snap = os.path.join(td, 'database.db')
        src, dst = sqlite3.connect(db_path, timeout=30), sqlite3.connect(snap)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        uploads = os.path.join(os.path.dirname(db_path), 'uploads')
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(snap, 'database.db')
            for folder, _dirs, files in os.walk(uploads):
                for fn in files:
                    full = os.path.join(folder, fn)
                    z.write(full, os.path.join('uploads', os.path.relpath(full, uploads)))


@bp.route('/account/backup.zip')
def backup():
    if not is_owner():
        return _bad('فقط مالک برنامه به پشتیبان کامل دسترسی دارد.', 403)
    tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    tmp.close()
    _write_backup_zip(tmp.name)

    @after_this_request
    def _cleanup(resp):
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        return resp

    stamp = jdatetime.date.today().strftime('%Y%m%d')
    return send_file(tmp.name, as_attachment=True, download_name='kargah-backup-%s.zip' % stamp, mimetype='application/zip')


# ---------------------------------------------------------------- بازیابی
class RestoreError(Exception):
    pass


def _validate_snapshot(path):
    try:
        cn = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
        try:
            if cn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RestoreError('دیتابیس داخل بکاپ سالم نیست.')
            tables = {r[0] for r in cn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise RestoreError('این فایل، بکاپ این برنامه نیست (جدول‌های لازم را ندارد).')
            if cn.execute('SELECT COUNT(*) FROM users').fetchone()[0] < 1:
                raise RestoreError('بکاپ هیچ کاربری ندارد؛ بعد از بازیابی نمی‌توانستید وارد شوید.')
        finally:
            cn.close()
    except sqlite3.DatabaseError:
        raise RestoreError('فایل دیتابیس داخل بکاپ خراب است.')


def restore_zip(fileobj):
    """بکاپ را اعتبارسنجی می‌کند، از وضعیت فعلی یک نسخه‌ی ایمنی می‌گیرد و بعد جایگزین می‌کند."""
    try:
        z = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile:
        raise RestoreError('فایل zip معتبر نیست.')
    names = z.namelist()
    if 'database.db' not in names:
        raise RestoreError('داخل zip فایل database.db پیدا نشد.')
    if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
        raise RestoreError('حجم بکاپ بیش از حد مجاز است.')
    db_path = db.engine.url.database
    inst = os.path.dirname(db_path)
    with tempfile.TemporaryDirectory() as td:
        snap = os.path.join(td, 'database.db')
        with z.open('database.db') as s, open(snap, 'wb') as d:
            shutil.copyfileobj(s, d)
        _validate_snapshot(snap)
        stage = os.path.join(td, 'uploads')
        os.makedirs(stage)
        for n in names:
            if not n.startswith('uploads/') or n.endswith('/'):
                continue
            dest = os.path.normpath(os.path.join(stage, n[len('uploads/'):]))
            if not dest.startswith(os.path.normpath(stage) + os.sep):
                continue                                   # مسیر مشکوک (path traversal) نادیده گرفته می‌شود
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(n) as s, open(dest, 'wb') as d:
                shutil.copyfileobj(s, d)

        os.makedirs(os.path.join(inst, 'backups'), exist_ok=True)
        safety = os.path.join(inst, 'backups', 'before-restore-%s.zip' % datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        _write_backup_zip(safety)

        db.session.remove()
        src, dst = sqlite3.connect(snap), sqlite3.connect(db_path, timeout=30)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        uploads = os.path.join(inst, 'uploads')
        shutil.rmtree(uploads, ignore_errors=True)
        shutil.copytree(stage, uploads)
    db.engine.dispose()
    db.create_all()
    ensure_columns()
    seed_missing_defaults()
    adopt_orphans()
    return safety


@bp.route('/api/account/restore', methods=['POST'])
def restore_api():
    if not is_owner():
        return _bad('فقط مالک برنامه می‌تواند بکاپ را بازیابی کند.', 403)
    err = _need_password(request.form)
    if err:
        return err
    if (request.form.get('confirm') or '').strip() != 'بازیابی':
        return _bad('برای تأیید، کلمه‌ی «بازیابی» را دقیقاً بنویسید.')
    f = request.files.get('file')
    if not f or not f.filename:
        return _bad('فایل بکاپ (zip) را انتخاب کنید.')
    try:
        safety = restore_zip(f.stream)
    except RestoreError as e:
        return _bad(str(e))
    return _ok(safety=os.path.basename(safety))


@click.command('restore')
@click.argument('zipfile_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--yes', is_flag=True, help='بدون پرسش تأیید')
@with_appcontext
def restore_cmd(zipfile_path, yes):
    """بازیابی بکاپ:  flask --app app restore backup.zip"""
    if not yes:
        click.confirm('همه‌ی اطلاعات فعلی با بکاپ جایگزین می‌شود (قبلش یک نسخه‌ی ایمنی گرفته می‌شود). ادامه؟', abort=True)
    try:
        with open(zipfile_path, 'rb') as f:
            safety = restore_zip(f)
    except RestoreError as e:
        raise click.ClickException(str(e))
    click.echo('بازیابی انجام شد. نسخه‌ی ایمنیِ قبل از آن: ' + safety)


# ---------------------------------------------------------------- بازیابی رمز
@click.command('reset-password')
@click.option('--user', 'ident', default=None, help='نام یا ایمیل کاربر (اگر فقط یک کاربر هست لازم نیست)')
@click.password_option('--password', prompt='رمز جدید', confirmation_prompt=True, help='رمز جدید (حداقل ۶ کاراکتر)')
@with_appcontext
def reset_password(ident, password):
    """بازیابی رمز فراموش‌شده:  flask --app app reset-password"""
    if len(password) < 6:
        raise click.ClickException('رمز باید حداقل ۶ کاراکتر باشد.')
    if ident:
        user = (User.query.filter(func.lower(User.email) == ident.lower()).first()
                or User.query.filter_by(name=ident).first())
    else:
        users = User.query.all()
        user = users[0] if len(users) == 1 else None
    if not user:
        raise click.ClickException('کاربر مشخص نیست؛ از --user استفاده کنید.')
    user.set_password(password)
    db.session.commit()
    click.echo('رمز «%s» عوض شد.' % user.name)
