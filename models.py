# D:\kargah\models.py
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import event, inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

class Workshop(db.Model):
    __tablename__ = 'workshops'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)   # مالک کارگاه
    farming_years = db.relationship('FarmingYear', backref='workshop', cascade='all, delete-orphan')
    activities = db.relationship('Activity', backref='workshop', cascade='all, delete-orphan')
    materials = db.relationship('Material', backref='workshop', cascade='all, delete-orphan')

class FarmingYear(db.Model):
    __tablename__ = 'farming_years'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(10), nullable=False)
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    daily_works = db.relationship('DailyWork', backref='farming_year', cascade='all, delete-orphan')

class Activity(db.Model):
    __tablename__ = 'activities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    has_material = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50))
    unit = db.Column(db.String(20), default='لیتر')
    default_price = db.Column(db.Integer, nullable=True)
    min_stock = db.Column(db.Float, nullable=True)   # حداقل موجودی برای هشدار
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)

class DailyWork(db.Model):
    __tablename__ = 'daily_works'
    id = db.Column(db.Integer, primary_key=True)
    date_shamsi = db.Column(db.String(10), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'))
    worker_count = db.Column(db.Integer, default=0)
    total_wage = db.Column(db.Integer, default=0)
    food_cost = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, default='')
    farming_year_id = db.Column(db.Integer, db.ForeignKey('farming_years.id'), nullable=False)
    is_temp = db.Column(db.Boolean, default=False)  # برای کارهای موقت
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    activity = db.relationship('Activity', backref='works')

class WorkMaterial(db.Model):
    __tablename__ = 'work_materials'
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('daily_works.id'))
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'))
    quantity = db.Column(db.Float, default=0)
    unit_price = db.Column(db.Integer, nullable=True)  # قیمت واحد در لحظه ثبت (تومان)
    
    work = db.relationship('DailyWork', backref=db.backref('materials_used', cascade='all, delete-orphan'))
    material = db.relationship('Material', backref='used_in')


# ==================== تنظیمات پلن‌ها ====================
# سقف تعداد کل عکس‌های آرشیو؛ None یعنی نامحدود
PLAN_PHOTO_LIMITS = {'free': 30, 'pro': None}

DEFAULT_INCOME_TYPES = [
    ('انگور تازه', 'کیلوگرم'),
    ('کشمش', 'کیلوگرم'),
    ('آبغوره', 'لیتر'),
    ('شیره', 'کیلوگرم'),
]
DEFAULT_EXPENSE_CATEGORIES = ['آبیاری', 'کارگر', 'گرد و روغن', 'سوخت', 'تعمیرات و ابزار', 'سایر']


# ==================== کاربر ====================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)  # برای ورود با ایمیل (بعد از رفتن روی دامنه)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(20), default='free')
    plan_expires_at = db.Column(db.DateTime, nullable=True)   # خالی = دائمی
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def effective_plan(self):
        """پلن واقعی با در نظر گرفتن انقضا (بعد از انقضا به رایگان برمی‌گردد؛ داده‌ها پاک نمی‌شوند)."""
        if self.plan == 'pro' and self.plan_expires_at and self.plan_expires_at < datetime.now():
            return 'free'
        return self.plan or 'free'

    @property
    def photo_limit(self):
        return PLAN_PHOTO_LIMITS.get(self.effective_plan, PLAN_PHOTO_LIMITS['free'])


# ==================== لایسنس ====================
class License(db.Model):
    __tablename__ = 'licenses'
    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(64), unique=True, nullable=False)   # خودِ کد ذخیره نمی‌شود، فقط hash
    hint = db.Column(db.String(8))
    days = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now)
    used_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    used_at = db.Column(db.DateTime)


# ==================== انبار سم و کود ====================
class MaterialInvoice(db.Model):
    __tablename__ = 'material_invoices'
    id = db.Column(db.Integer, primary_key=True)
    date_shamsi = db.Column(db.String(10), nullable=False)
    seller = db.Column(db.String(100), default='')
    invoice_no = db.Column(db.String(50), default='')
    description = db.Column(db.Text, default='')
    farming_year_id = db.Column(db.Integer, db.ForeignKey('farming_years.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    farming_year = db.relationship('FarmingYear', backref=db.backref('material_invoices', cascade='all, delete-orphan'))
    items = db.relationship('MaterialPurchase', backref='invoice', cascade='all, delete-orphan')


class MaterialPurchase(db.Model):
    __tablename__ = 'material_purchases'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('material_invoices.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit_price = db.Column(db.Integer, nullable=True)
    amount = db.Column(db.Integer, default=0)

    material = db.relationship('Material', backref=db.backref('purchases', cascade='all, delete-orphan'))


class StockAdjustment(db.Model):
    """تغییر دستی موجودی (شمارش انبار، ضایعات، موجودی اول دوره...)؛ quantity می‌تواند منفی باشد."""
    __tablename__ = 'stock_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    date_shamsi = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)

    material = db.relationship('Material', backref=db.backref('adjustments', cascade='all, delete-orphan'))


# ==================== درآمد ====================
class IncomeType(db.Model):
    __tablename__ = 'income_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(20), default='کیلوگرم')
    is_active = db.Column(db.Boolean, default=True)
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)
    workshop = db.relationship('Workshop', backref=db.backref('income_types', cascade='all, delete-orphan'))


class Income(db.Model):
    __tablename__ = 'incomes'
    id = db.Column(db.Integer, primary_key=True)
    date_shamsi = db.Column(db.String(10), nullable=False)
    income_type_id = db.Column(db.Integer, db.ForeignKey('income_types.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=True)
    unit_price = db.Column(db.Integer, nullable=True)   # تومان
    amount = db.Column(db.Integer, nullable=False, default=0)  # تومان
    buyer = db.Column(db.String(100), default='')
    is_gift = db.Column(db.Boolean, default=False)   # هدیه: ارزش ثبت می‌شود ولی در درآمد حساب نمی‌شود
    description = db.Column(db.Text, default='')
    farming_year_id = db.Column(db.Integer, db.ForeignKey('farming_years.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    income_type = db.relationship('IncomeType', backref='incomes')
    farming_year = db.relationship('FarmingYear', backref=db.backref('incomes', cascade='all, delete-orphan'))


# ==================== هزینه ====================
class ExpenseCategory(db.Model):
    __tablename__ = 'expense_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)
    workshop = db.relationship('Workshop', backref=db.backref('expense_categories', cascade='all, delete-orphan'))


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    date_shamsi = db.Column(db.String(10), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False, default=0)  # تومان
    description = db.Column(db.Text, default='')
    farming_year_id = db.Column(db.Integer, db.ForeignKey('farming_years.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    category = db.relationship('ExpenseCategory', backref='expenses')
    farming_year = db.relationship('FarmingYear', backref=db.backref('expenses', cascade='all, delete-orphan'))


# ==================== آرشیو عکس و یادداشت ====================
class ArchiveEntry(db.Model):
    __tablename__ = 'archive_entries'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    stage = db.Column(db.String(60), default='')   # مثلا: غوره، گل‌دهی، برداشت
    date_shamsi = db.Column(db.String(10), nullable=False)
    description = db.Column(db.Text, default='')
    farming_year_id = db.Column(db.Integer, db.ForeignKey('farming_years.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    farming_year = db.relationship('FarmingYear', backref=db.backref('archive_entries', cascade='all, delete-orphan'))
    photos = db.relationship('ArchivePhoto', backref='entry', cascade='all, delete-orphan')


class ArchivePhoto(db.Model):
    __tablename__ = 'archive_photos'
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('archive_entries.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    thumb = db.Column(db.String(200), nullable=False)
    size_bytes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)


# ==================== داده‌های پیش‌فرض ====================
@event.listens_for(Workshop, 'after_insert')
def _seed_workshop_defaults(mapper, connection, target):
    """هر کارگاه جدید با انواع درآمد و هزینه پیش‌فرض ساخته می‌شود."""
    connection.execute(IncomeType.__table__.insert(), [
        {'name': n, 'unit': u, 'is_active': True, 'workshop_id': target.id}
        for n, u in DEFAULT_INCOME_TYPES
    ])
    connection.execute(ExpenseCategory.__table__.insert(), [
        {'name': n, 'is_active': True, 'workshop_id': target.id}
        for n in DEFAULT_EXPENSE_CATEGORIES
    ])


def seed_missing_defaults():
    """برای هر کارگاهی که انواع درآمد یا دسته‌های هزینه ندارد، پیش‌فرض‌ها را می‌سازد."""
    changed = False
    for w in Workshop.query.all():
        if not IncomeType.query.filter_by(workshop_id=w.id).first():
            for n, u in DEFAULT_INCOME_TYPES:
                db.session.add(IncomeType(name=n, unit=u, workshop_id=w.id))
            changed = True
        if not ExpenseCategory.query.filter_by(workshop_id=w.id).first():
            for n in DEFAULT_EXPENSE_CATEGORIES:
                db.session.add(ExpenseCategory(name=n, workshop_id=w.id))
            changed = True
    if changed:
        db.session.commit()


def ensure_columns():
    """ستون‌های جدیدِ جدول‌های قدیمی (create_all این‌ها را اضافه نمی‌کند)."""
    cols = {c['name'] for c in inspect(db.engine).get_columns('work_materials')}
    if 'unit_price' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE work_materials ADD COLUMN unit_price INTEGER'))
    for table, col, ddl in (('workshops', 'user_id', 'INTEGER'), ('users', 'plan_expires_at', 'DATETIME'), ('materials', 'min_stock', 'FLOAT'), ('incomes', 'is_gift', 'BOOLEAN DEFAULT 0')):
        have = {c['name'] for c in inspect(db.engine).get_columns(table)}
        if col not in have:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE %s ADD COLUMN %s %s' % (table, col, ddl)))
