# D:\kargah\app.py

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

from dotenv import load_dotenv
from extensions import db, login_manager
import secrets
from datetime import datetime
import jdatetime
import os

app = Flask(__name__)

# تنظیمات دیتابیس
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
load_dotenv()


def _ensure_secret_key():
    """SECRET_KEY را از .env می‌خواند؛ اگر نبود می‌سازد و در .env ذخیره می‌کند."""
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    key = secrets.token_hex(32)
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    with open(env_path, 'a', encoding='utf-8') as f:
        f.write('\nSECRET_KEY=%s\n' % key)
    return key


app.config['SECRET_KEY'] = _ensure_secret_key()
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# ==================== مدل‌های دیتابیس ====================

from models import (Workshop, FarmingYear, Activity, Material, DailyWork, WorkMaterial,
                    ensure_columns, seed_missing_defaults)

# ==================== توابع کمکی ====================
def get_today_shamsi():
    now = jdatetime.datetime.now()
    return now.strftime("%Y/%m/%d")

# ==================== Routes اصلی ====================
@app.route('/')
def index():
    """صفحه اصلی لیست کارگاه‌ها"""
    workshops = Workshop.query.all()
    return render_template('index.html', workshops=workshops)

@app.route('/workshop/<int:workshop_id>/<int:year_id>')
def workshop_dashboard(workshop_id, year_id):
    """داشبورد یک کارگاه خاص با سال کاری مشخص"""
    workshop = db.get_or_404(Workshop, workshop_id)
    farming_year = db.get_or_404(FarmingYear, year_id)
    if farming_year.workshop_id != workshop.id:
        abort(404)
    all_years = FarmingYear.query.filter_by(workshop_id=workshop_id).all()
    
    today = get_today_shamsi()
    activities = Activity.query.filter_by(workshop_id=workshop_id, is_active=True).all()
    works = DailyWork.query.filter_by(farming_year_id=year_id, is_temp=False).order_by(DailyWork.id.desc()).all()
    materials = Material.query.filter_by(workshop_id=workshop_id).all()
    
    return render_template('workshop.html', 
                         workshop=workshop,
                         farming_year=farming_year,
                         all_years=all_years,
                         today=today, 
                         activities=activities, 
                         works=works,
                         materials=materials)

# ==================== [patch4] ایمنی، اعتبارسنجی و APIهای اصلاح‌شده ====================
# [patch4]
import functools
import re
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException

from models import Income, Expense, ArchiveEntry
from finance import _date as _fdate, _num as _fnum

app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
if os.environ.get('COOKIE_SECURE') == '1':          # بعد از رفتن روی HTTPS
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = True
if os.environ.get('BEHIND_PROXY') == '1':           # پشت nginx
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


@event.listens_for(Engine, 'connect')
def _sqlite_foreign_keys_on(dbapi_conn, _record):
    """SQLite به‌طور پیش‌فرض کلید خارجی را اجرا نمی‌کند."""
    if dbapi_conn.__class__.__module__.split('.')[0] == 'sqlite3':
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA foreign_keys=ON')
        cur.close()


# ---------- محافظ CSRF (بررسی مبدأ درخواست‌های تغییردهنده) ----------
_UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
_EXTRA_HOSTS = {h.strip() for h in os.environ.get('ALLOWED_ORIGINS', '').split(',') if h.strip()}


@app.before_request
def _origin_guard():
    if request.method not in _UNSAFE_METHODS:
        return None
    src = request.headers.get('Origin') or request.headers.get('Referer') or ''
    src_host = urlparse(src).netloc if src else ''
    if src_host and src_host in _EXTRA_HOSTS:
        return None
    site = request.headers.get('Sec-Fetch-Site')
    if site in ('same-origin', 'none'):
        return None
    if site is None and (not src or src_host == request.host):
        return None
    msg = 'درخواست از مبدأ نامعتبر رد شد.'
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': msg}), 403
    return msg, 403


# ---------- ابزارهای مشترک APIها ----------
class _NotFound(LookupError):
    pass


def _api(fn):
    """خطاها را به JSON فارسی تبدیل می‌کند و متن خطای داخلی را لو نمی‌دهد."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HTTPException:
            raise
        except _NotFound as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 404
        except ValueError as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception:
            db.session.rollback()
            app.logger.exception('خطا در %s', fn.__name__)
            return jsonify({'success': False, 'error': 'خطای داخلی سرور؛ دوباره تلاش کنید.'}), 500
    return wrapper


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('اطلاعات ارسال‌شده معتبر نیست.')
    return data


def _need_id(value, label):
    n = _fnum(value)
    if not n:
        raise ValueError('%s مشخص نیست.' % label)
    return n


def _get(model, ident, label):
    obj = db.session.get(model, ident)
    if obj is None:
        raise _NotFound('%s پیدا نشد.' % label)
    return obj


def _text(value, label, max_len, required=True):
    s = str(value).strip() if value is not None else ''
    if required and not s:
        raise ValueError('%s را وارد کنید.' % label)
    if len(s) > max_len:
        raise ValueError('%s نباید بیش از %d حرف باشد.' % (label, max_len))
    return s


def _bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ('1', 'true', 'on', 'yes')
    return bool(v)


def _work_values(data, year):
    """مقادیر اعتبارسنجی‌شده‌ی کار روزانه؛ تاریخ همیشه به YYYY/MM/DD صفر‌دار تبدیل می‌شود."""
    act = _get(Activity, _need_id(data.get('activity_id'), 'فعالیت'), 'فعالیت')
    if act.workshop_id != year.workshop_id:
        raise ValueError('فعالیت انتخاب‌شده معتبر نیست.')
    return dict(
        date_shamsi=_fdate(data.get('date')),
        activity_id=act.id,
        worker_count=_fnum(data.get('worker_count')) or 0,
        total_wage=_fnum(data.get('total_wage')) or 0,
        food_cost=_fnum(data.get('food_cost')) or 0,
        description=_text(data.get('description'), 'توضیحات', 2000, required=False),
    )


def _normalize_old_dates():
    """تاریخ‌های قدیمیِ کار روزانه (ارقام فارسی / بدون صفر ابتدایی) را یک‌بار اصلاح می‌کند."""
    fixed = bad = 0
    for wid, d in db.session.query(DailyWork.id, DailyWork.date_shamsi).all():
        if d and re.match(r'^[0-9]{4}/[0-9]{2}/[0-9]{2}$', d):
            continue
        try:
            n = _fdate(d)
        except ValueError:
            bad += 1
            continue
        DailyWork.query.filter_by(id=wid).update({'date_shamsi': n})
        fixed += 1
    if fixed:
        db.session.commit()
    if fixed or bad:
        print('[patch4] تاریخ کار روزانه: %d مورد اصلاح شد، %d مورد نامعتبر ماند.' % (fixed, bad))


# ==================== APIهای کارگاه ====================
@app.route('/api/create_workshop', methods=['POST'])
@_api
def create_workshop():
    """ایجاد کارگاه جدید با چند سال کاری"""
    data = _body()
    name = _text(data.get('name'), 'نام کارگاه', 100)
    raw_years = data.get('years')
    if not isinstance(raw_years, list):
        raise ValueError('سال زراعی را وارد کنید.')
    years = []
    for y in raw_years:
        y = _text(y, 'سال زراعی', 10, required=False)
        if y and y not in years:
            years.append(y)
    if not years:
        raise ValueError('حداقل یک سال زراعی وارد کنید.')

    workshop = Workshop(name=name)
    db.session.add(workshop)
    db.session.flush()

    first_year_id = None
    for year_str in years:
        year = FarmingYear(year=year_str, workshop_id=workshop.id)
        db.session.add(year)
        db.session.flush()
        if first_year_id is None:
            first_year_id = year.id

    for n, has_mat in [('هرس', False), ('محلول‌پاشی', True), ('آبیاری', False),
                       ('سم‌پاشی', True), ('کوددهی', True), ('تزریق کود', True)]:
        db.session.add(Activity(name=n, has_material=has_mat, workshop_id=workshop.id))

    for n, t, u in [('کود اوره', 'کود', 'کیلوگرم'), ('کود پتاس', 'کود', 'کیلوگرم'),
                    ('کود مایع', 'کود مایع', 'لیتر'), ('سم قارچ‌کش', 'سم', 'لیتر'),
                    ('سم حشره‌کش', 'سم', 'لیتر')]:
        db.session.add(Material(name=n, type=t, unit=u, workshop_id=workshop.id))

    db.session.commit()
    return jsonify({'success': True, 'workshop_id': workshop.id, 'first_year_id': first_year_id})


@app.route('/api/add_farming_year', methods=['POST'])
@_api
def add_farming_year():
    """اضافه کردن سال کاری جدید"""
    data = _body()
    workshop = _get(Workshop, _need_id(data.get('workshop_id'), 'کارگاه'), 'کارگاه')
    name = _text(data.get('year'), 'سال زراعی', 10)
    if FarmingYear.query.filter_by(workshop_id=workshop.id, year=name).first():
        raise ValueError('این سال زراعی قبلاً ثبت شده است.')
    year = FarmingYear(year=name, workshop_id=workshop.id)
    db.session.add(year)
    db.session.commit()
    return jsonify({'success': True, 'year_id': year.id})


@app.route('/api/delete_year/<int:year_id>', methods=['DELETE'])
@_api
def delete_year(year_id):
    """حذف سال زراعی؛ اگر داده دارد فقط با confirm=1 (تأیید کاربر) حذف می‌شود."""
    year = _get(FarmingYear, year_id, 'سال زراعی')
    counts = [('کار روزانه', DailyWork.query.filter_by(farming_year_id=year.id).count()),
              ('درآمد', Income.query.filter_by(farming_year_id=year.id).count()),
              ('هزینه', Expense.query.filter_by(farming_year_id=year.id).count()),
              ('آرشیو', ArchiveEntry.query.filter_by(farming_year_id=year.id).count())]
    total = sum(c for _, c in counts)
    if total and request.args.get('confirm') != '1':
        detail = '، '.join('%d %s' % (c, n) for n, c in counts if c)
        raise ValueError('این سال شامل %s است؛ برای حذف نهایی باید تأیید شود.' % detail)
    db.session.delete(year)
    db.session.commit()
    return jsonify({'success': True})


# ==================== APIهای کار ====================
def _new_work(is_temp):
    data = _body()
    year = _get(FarmingYear, _need_id(data.get('farming_year_id'), 'سال زراعی'), 'سال زراعی')
    work = DailyWork(farming_year_id=year.id, is_temp=is_temp, **_work_values(data, year))
    db.session.add(work)
    db.session.commit()
    return work


@app.route('/api/save_work_temp', methods=['POST'])
@_api
def save_work_temp():
    """ذخیره موقت کار جدید قبل از انتخاب مواد"""
    work = _new_work(True)
    return jsonify({'success': True, 'work_id': work.id})


@app.route('/api/save_work_final', methods=['POST'])
@_api
def save_work_final():
    """ذخیره نهایی کار بدون مواد"""
    _new_work(False)
    return jsonify({'success': True})


@app.route('/api/save_material_usage', methods=['POST'])
@_api
def save_material_usage():
    """ذخیره مواد مصرفی یک کار و نهایی‌سازی آن"""
    data = _body()
    work = _get(DailyWork, _need_id(data.get('work_id'), 'کار'), 'کار')
    year = db.session.get(FarmingYear, work.farming_year_id)
    items = data.get('materials')
    if not isinstance(items, list):
        raise ValueError('فهرست مواد معتبر نیست.')

    # قیمتِ لحظه ثبت برای موادی که از قبل در این کار بوده‌اند حفظ می‌شود (هنگام ویرایش)
    old_prices = {m.material_id: m.unit_price for m in WorkMaterial.query.filter_by(work_id=work.id)}
    rows = []
    for it in items:
        if not isinstance(it, dict):
            raise ValueError('فهرست مواد معتبر نیست.')
        mat = _get(Material, _need_id(it.get('material_id'), 'ماده'), 'ماده')
        if mat.workshop_id != year.workshop_id:
            raise ValueError('ماده انتخاب‌شده معتبر نیست.')
        qty = _fnum(it.get('quantity'), False) or 0.0
        # قیمت صفر/خالی ذخیره نمی‌شود تا با تعیین قیمت بعدی، هزینه محاسبه شود
        price = old_prices[mat.id] if mat.id in old_prices else (mat.default_price or None)
        rows.append(WorkMaterial(work_id=work.id, material_id=mat.id, quantity=qty, unit_price=price))

    WorkMaterial.query.filter_by(work_id=work.id).delete()
    db.session.add_all(rows)
    work.is_temp = False
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/finalize_work', methods=['POST'])
@_api
def finalize_work():
    """نهایی‌سازی کار بدون مواد"""
    work = _get(DailyWork, _need_id(_body().get('work_id'), 'کار'), 'کار')
    work.is_temp = False
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/delete_temp_work/<int:work_id>', methods=['DELETE'])
@_api
def delete_temp_work(work_id):
    """حذف کار موقت در صورت انصراف"""
    work = DailyWork.query.filter_by(id=work_id, is_temp=True).first()
    if work:
        db.session.delete(work)
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/update_work', methods=['POST'])
@_api
def update_work():
    """ویرایش یک کار"""
    data = _body()
    work = _get(DailyWork, _need_id(data.get('work_id'), 'کار'), 'کار')
    year = db.session.get(FarmingYear, work.farming_year_id)
    for k, v in _work_values(data, year).items():
        setattr(work, k, v)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/delete_work/<int:work_id>', methods=['DELETE'])
@_api
def delete_work(work_id):
    """حذف یک کار"""
    work = db.session.get(DailyWork, work_id)
    if work:
        WorkMaterial.query.filter_by(work_id=work_id).delete()
        db.session.delete(work)
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/get_work_materials/<int:work_id>')
@_api
def get_work_materials(work_id):
    """گرفتن لیست مواد مصرفی یک کار"""
    materials = WorkMaterial.query.filter_by(work_id=work_id).all()
    return jsonify([{
        'id': m.id,
        'material_id': m.material_id,
        'name': m.material.name,
        'type': m.material.type,
        'unit': m.material.unit,
        'quantity': m.quantity
    } for m in materials if m.material])


# ==================== APIهای فعالیت ====================
@app.route('/api/get_activities')
@_api
def get_activities():
    """گرفتن لیست فعالیت‌ها با قابلیت جستجو"""
    workshop_id = request.args.get('workshop_id', type=int)
    search = request.args.get('search', '')
    query = Activity.query.filter_by(workshop_id=workshop_id, is_active=True)
    if search:
        query = query.filter(Activity.name.contains(search))
    return jsonify([{'id': a.id, 'name': a.name, 'has_material': a.has_material}
                    for a in query.all()])


@app.route('/api/add_activity', methods=['POST'])
@_api
def add_activity():
    """اضافه کردن فعالیت جدید"""
    data = _body()
    workshop = _get(Workshop, _need_id(data.get('workshop_id'), 'کارگاه'), 'کارگاه')
    name = _text(data.get('name'), 'نام فعالیت', 100)
    if Activity.query.filter_by(workshop_id=workshop.id, name=name, is_active=True).first():
        raise ValueError('این فعالیت قبلاً وجود دارد.')
    activity = Activity(name=name, has_material=_bool(data.get('has_material')), workshop_id=workshop.id)
    db.session.add(activity)
    db.session.commit()
    return jsonify({'success': True, 'id': activity.id, 'name': activity.name})


@app.route('/api/update_activity/<int:activity_id>', methods=['PUT'])
@_api
def update_activity(activity_id):
    """ویرایش فعالیت"""
    data = _body()
    activity = _get(Activity, activity_id, 'فعالیت')
    name = _text(data.get('name'), 'نام فعالیت', 100)
    clash = Activity.query.filter_by(workshop_id=activity.workshop_id, name=name, is_active=True).first()
    if clash and clash.id != activity.id:
        raise ValueError('این فعالیت قبلاً وجود دارد.')
    activity.name = name
    activity.has_material = _bool(data.get('has_material'))
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/delete_activity/<int:activity_id>', methods=['DELETE'])
@_api
def delete_activity(activity_id):
    """حذف فعالیت؛ اگر در کارهای ثبت‌شده استفاده شده، به‌جای حذف غیرفعال می‌شود."""
    activity = _get(Activity, activity_id, 'فعالیت')
    used = DailyWork.query.filter_by(activity_id=activity.id).count()
    if used:
        activity.is_active = False
        db.session.commit()
        return jsonify({'success': True, 'deactivated': True,
                        'message': 'این فعالیت در %d کار استفاده شده؛ به‌جای حذف، غیرفعال شد.' % used})
    db.session.delete(activity)
    db.session.commit()
    return jsonify({'success': True})


# ==================== APIهای مواد ====================
@app.route('/api/get_materials')
@_api
def get_materials():
    """گرفتن لیست مواد با قابلیت جستجو"""
    workshop_id = request.args.get('workshop_id', type=int)
    search = request.args.get('search', '')
    query = Material.query.filter_by(workshop_id=workshop_id)
    if search:
        query = query.filter(Material.name.contains(search))
    return jsonify([{'id': m.id, 'name': m.name, 'type': m.type, 'unit': m.unit,
                     'default_price': m.default_price} for m in query.all()])


@app.route('/api/add_material', methods=['POST'])
@_api
def add_material():
    """اضافه کردن ماده جدید"""
    data = _body()
    workshop = _get(Workshop, _need_id(data.get('workshop_id'), 'کارگاه'), 'کارگاه')
    name = _text(data.get('name'), 'نام ماده', 100)
    if Material.query.filter_by(workshop_id=workshop.id, name=name).first():
        raise ValueError('این ماده قبلاً وجود دارد.')
    material = Material(
        name=name,
        type=_text(data.get('type') or 'کود', 'نوع ماده', 50),
        unit=_text(data.get('unit') or 'لیتر', 'واحد', 20),
        default_price=_fnum(data.get('default_price')) or 0,
        workshop_id=workshop.id)
    db.session.add(material)
    db.session.commit()
    return jsonify({'success': True, 'id': material.id, 'name': material.name})


@app.route('/api/update_material/<int:material_id>', methods=['PUT'])
@_api
def update_material(material_id):
    """ویرایش ماده (نام، نوع، واحد و در صورت ارسال، قیمت)"""
    data = _body()
    material = _get(Material, material_id, 'ماده')
    name = _text(data.get('name'), 'نام ماده', 100)
    clash = Material.query.filter_by(workshop_id=material.workshop_id, name=name).first()
    if clash and clash.id != material.id:
        raise ValueError('این ماده قبلاً وجود دارد.')
    material.name = name
    material.type = _text(data.get('type') or material.type or 'کود', 'نوع ماده', 50)
    material.unit = _text(data.get('unit') or material.unit or 'لیتر', 'واحد', 20)
    if 'default_price' in data:
        material.default_price = _fnum(data.get('default_price')) or 0
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/delete_material/<int:material_id>', methods=['DELETE'])
@_api
def delete_material(material_id):
    """حذف ماده (فرانت این مسیر را صدا می‌زد ولی وجود نداشت)؛ ماده‌ی استفاده‌شده حذف نمی‌شود."""
    material = _get(Material, material_id, 'ماده')
    used = WorkMaterial.query.filter_by(material_id=material.id).count()
    if used:
        raise ValueError('این ماده در %d مصرف ثبت‌شده استفاده شده و قابل حذف نیست.' % used)
    db.session.delete(material)
    db.session.commit()
    return jsonify({'success': True})


# ==================== ایجاد دیتابیس ====================
# ==================== ماژول‌ها (Blueprint) ====================
from auth import bp as auth_bp
from dashboard import bp as dashboard_bp
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
from finance import bp as finance_bp
app.register_blueprint(finance_bp)
from reports import bp as reports_bp
from archive import bp as archive_bp
app.register_blueprint(reports_bp)
app.register_blueprint(archive_bp)
from manage import bp as manage_bp
app.register_blueprint(manage_bp)
from account import bp as account_bp
app.register_blueprint(account_bp)
import tenancy
tenancy.install()   # هر کاربر فقط داده‌ی خودش را می‌بیند
from signup import bp as signup_bp
app.register_blueprint(signup_bp)
# [next-blueprints] پچ‌های بعدی ماژول‌های جدید را اینجا ثبت می‌کنند

with app.app_context():
    db.create_all()
    ensure_columns()
    seed_missing_defaults()
    _normalize_old_dates()
    from tenancy import adopt_orphans
    adopt_orphans()

if __name__ == '__main__':
    _debug = os.environ.get('FLASK_DEBUG', '0') == '1'   # [patch4] پیش‌فرض خاموش
    app.run(host=os.environ.get('FLASK_HOST', '127.0.0.1' if _debug else '0.0.0.0'),
            port=5011, debug=_debug)