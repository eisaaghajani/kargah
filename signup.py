# D:\kargah\signup.py  —  ثبت‌نام کاربر جدید (به‌صورت پیش‌فرض خاموش؛ با ALLOW_REGISTER=1 روشن می‌شود)
import os
import re
import time
from collections import defaultdict

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_user
from sqlalchemy import func

from extensions import db
from models import User

bp = Blueprint('signup', __name__)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_hits = defaultdict(list)       # ip -> زمان ثبت‌نام‌های اخیر


def enabled():
    return os.environ.get('ALLOW_REGISTER') == '1'


@bp.app_context_processor
def _inject():
    return {'allow_register': enabled()}


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if User.query.first() is None:
        return redirect(url_for('auth.setup'))
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if not enabled():
        return render_template('register.html', error=None, form={}, disabled=True), 403
    error, form = None, request.form
    if request.method == 'POST':
        ip = request.remote_addr or '-'
        now = time.time()
        _hits[ip] = [t for t in _hits[ip] if now - t < 3600]
        name = (form.get('name') or '').strip()
        email = (form.get('email') or '').strip().lower() or None
        pw = form.get('password') or ''
        if len(_hits[ip]) >= 5:
            error = 'ثبت‌نام‌های این دستگاه زیاد بود؛ بعداً دوباره امتحان کنید.'
        elif not name:
            error = 'نام کاربری را وارد کنید.'
        elif len(name) > 100 or '@' in name:
            error = 'نام کاربری نباید @ داشته باشد و باید کوتاه‌تر از ۱۰۰ حرف باشد.'
        elif email and not EMAIL_RE.match(email):
            error = 'ایمیل معتبر نیست.'
        elif len(pw) < 6:
            error = 'رمز عبور باید حداقل ۶ کاراکتر باشد.'
        elif pw != form.get('password2'):
            error = 'تکرار رمز عبور یکسان نیست.'
        elif User.query.filter(func.lower(User.name) == name.lower()).first():
            error = 'این نام کاربری قبلاً استفاده شده است.'
        elif email and User.query.filter(func.lower(User.email) == email).first():
            error = 'این ایمیل قبلاً ثبت شده است.'
        else:
            user = User(name=name, email=email)
            user.set_password(pw)
            db.session.add(user)
            db.session.commit()
            _hits[ip].append(now)
            login_user(user, remember=True)
            return redirect(url_for('index'))
    return render_template('register.html', error=error, form=form, disabled=False)
