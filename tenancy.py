# D:\kargah\tenancy.py  —  جداسازی داده‌ی کاربران (هر کاربر فقط کارگاه‌های خودش را می‌بیند)
#
# به‌جای وصله‌کردن تک‌تک مسیرها، یک فیلتر مرکزی روی «همه‌ی» کوئری‌های ORM داخل درخواست‌ها گذاشته می‌شود:
# هر کوئری روی کارگاه، سال، کار، درآمد، هزینه، آرشیو و... فقط ردیف‌های کاربر واردشده را برمی‌گرداند.
# اگر کاربری شناخته نشود، هیچ داده‌ای دیده نمی‌شود (fail-closed).
from contextlib import contextmanager

from flask import g, has_request_context, session
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, with_loader_criteria

from extensions import db
from models import (Activity, ArchiveEntry, ArchivePhoto, DailyWork, Expense, ExpenseCategory, FarmingYear,
                    Income, IncomeType, Material, User, WorkMaterial, Workshop)

_installed = False


def current_uid():
    """شناسه‌ی کاربر درخواست جاری؛ اگر وارد نشده باشد -1 (یعنی هیچ داده‌ای)."""
    if not has_request_context():
        return -1
    if '_login_user' in g:                       # Flask-Login پس از بارگذاری کاربر این را می‌گذارد
        user = g._login_user
        return user.id if getattr(user, 'is_authenticated', False) else -1
    raw = session.get('_user_id')                # پشتیبان: نشست امضاشده (قبل از بارگذاری کاربر)
    try:
        return int(raw) if raw is not None else -1
    except (TypeError, ValueError):
        return -1


def _criteria(uid):
    t = lambda m: m.__table__.c            # زیرکوئری‌ها با Core ساخته می‌شوند تا فیلتر دوباره روی آن‌ها اعمال نشود
    ws = select(t(Workshop).id).where(t(Workshop).user_id == uid)
    yr = select(t(FarmingYear).id).where(t(FarmingYear).workshop_id.in_(ws))
    wk = select(t(DailyWork).id).where(t(DailyWork).farming_year_id.in_(yr))
    en = select(t(ArchiveEntry).id).where(t(ArchiveEntry).farming_year_id.in_(yr))
    return [
        (Workshop, Workshop.user_id == uid),
        (FarmingYear, FarmingYear.workshop_id.in_(ws)),
        (Activity, Activity.workshop_id.in_(ws)),
        (Material, Material.workshop_id.in_(ws)),
        (IncomeType, IncomeType.workshop_id.in_(ws)),
        (ExpenseCategory, ExpenseCategory.workshop_id.in_(ws)),
        (DailyWork, DailyWork.farming_year_id.in_(yr)),
        (Income, Income.farming_year_id.in_(yr)),
        (Expense, Expense.farming_year_id.in_(yr)),
        (ArchiveEntry, ArchiveEntry.farming_year_id.in_(yr)),
        (WorkMaterial, WorkMaterial.work_id.in_(wk)),
        (ArchivePhoto, ArchivePhoto.entry_id.in_(en)),
    ]


@contextmanager
def bypass():
    """فقط برای کارهای سیستمی (مثل تحویل کارگاه‌های بدون مالک)؛ فیلتر را موقتاً خاموش می‌کند."""
    if not has_request_context():
        yield
        return
    old = g.get('_tenant_off')
    g._tenant_off = True
    try:
        yield
    finally:
        g._tenant_off = old


def adopt_orphans(user_id=None):
    """کارگاه‌های بدون مالک (داده‌ی قبل از چندکاربره) را به کاربر مشخص‌شده یا قدیمی‌ترین کاربر می‌دهد."""
    if user_id is None:
        user_id = db.session.query(func.min(User.id)).scalar()
    if user_id is None:
        return 0
    with bypass():
        n = Workshop.query.filter(Workshop.user_id.is_(None)).update({'user_id': user_id}, synchronize_session=False)
        db.session.commit()
    return n


def install():
    global _installed
    if _installed:
        return
    _installed = True

    @event.listens_for(Session, 'do_orm_execute')
    def _scope(state):
        if state.is_column_load or state.is_relationship_load:
            return
        if not (state.is_select or state.is_update or state.is_delete):
            return
        if not has_request_context() or g.get('_tenant_off'):
            return
        opts = [with_loader_criteria(cls, cond, include_aliases=True) for cls, cond in _criteria(current_uid())]
        state.statement = state.statement.options(*opts)

    @event.listens_for(Workshop, 'before_insert')
    def _set_owner(mapper, connection, target):
        if target.user_id is None:
            uid = current_uid()
            if uid != -1:
                target.user_id = uid
