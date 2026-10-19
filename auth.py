# D:\kargah\auth.py  —  ورود / خروج / راه‌اندازی اولیه
import re
import time
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_user, logout_user, current_user
from sqlalchemy import func

from extensions import db, login_manager
from models import User

bp = Blueprint('auth', __name__)

# endpointهایی که بدون ورود در دسترس‌اند (patchهای بعدی مثل manifest اینجا اضافه می‌کنند)
OPEN_ENDPOINTS = {'auth.login', 'auth.setup', 'signup.register', 'static'}

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_fails = defaultdict(list)  # ip -> زمان تلاش‌های ناموفق (پشت nginx باید ProxyFix اضافه شود)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@bp.before_app_request
def require_login():
    if request.endpoint is None or request.endpoint in OPEN_ENDPOINTS:
        return None
    if current_user.is_authenticated:
        return None
    if User.query.first() is None:
        return redirect(url_for('auth.setup'))
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'ابتدا وارد شوید'}), 401
    return redirect(url_for('auth.login', next=request.path))


def _safe_next(target):
    if target and target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return url_for('index')


@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """فقط وقتی هیچ کاربری وجود ندارد: ساخت حساب مالک برنامه."""
    if User.query.first() is not None:
        return redirect(url_for('auth.login'))
    error = None
    form = request.form
    if request.method == 'POST':
        name = (form.get('name') or '').strip()
        email = (form.get('email') or '').strip().lower() or None
        pw = form.get('password') or ''
        if not name:
            error = 'نام را وارد کنید.'
        elif email and not EMAIL_RE.match(email):
            error = 'ایمیل معتبر نیست.'
        elif len(pw) < 6:
            error = 'رمز عبور باید حداقل ۶ کاراکتر باشد.'
        elif pw != form.get('password2'):
            error = 'تکرار رمز عبور یکسان نیست.'
        else:
            user = User(name=name, email=email)
            user.set_password(pw)
            db.session.add(user)
            db.session.commit()
            from tenancy import adopt_orphans
            adopt_orphans(user.id)   # کارگاه‌های قدیمی به مالک می‌رسد
            login_user(user, remember=True)
            return redirect(url_for('index'))
    return render_template('setup.html', error=error, form=form)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if User.query.first() is None:
        return redirect(url_for('auth.setup'))
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        ip = request.remote_addr or '-'
        now = time.time()
        _fails[ip] = [t for t in _fails[ip] if now - t < 600]
        if len(_fails[ip]) >= 5:
            error = 'تلاش ناموفق زیاد بود؛ چند دقیقه بعد دوباره امتحان کنید.'
        else:
            ident = (request.form.get('identifier') or '').strip()
            user = (User.query.filter(func.lower(User.email) == ident.lower()).first()
                    or User.query.filter_by(name=ident).first())
            if user and user.check_password(request.form.get('password') or ''):
                _fails.pop(ip, None)
                login_user(user, remember=True)
                return redirect(_safe_next(request.args.get('next')))
            _fails[ip].append(now)
            error = 'نام/ایمیل یا رمز عبور درست نیست.'
    return render_template('login.html', error=error)


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# TODO (بعد از رفتن روی دامنه): تایید ایمیل و بازیابی رمز با SMTP — ستون email_verified آماده است.
