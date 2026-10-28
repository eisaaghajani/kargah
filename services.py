# D:\kargah\services.py  —  محاسبات مالی مشترک (داشبورد، گزارش‌ها)
from datetime import datetime
from sqlalchemy import func
from extensions import db
from models import (DailyWork, WorkMaterial, Material, Income, IncomeType,
                    Expense, ExpenseCategory)


def _rng(q, col, d_from, d_to):
    """فیلتر بازه تاریخ شمسی (رشته‌های YYYY/MM/DD با صفر ابتدایی قابل مقایسه‌اند)."""
    if d_from:
        q = q.filter(col >= d_from)
    if d_to:
        q = q.filter(col <= d_to)
    return q


def year_totals(year_id, d_from=None, d_to=None):
    inc_rows = _rng(
        db.session.query(IncomeType.name, func.sum(Income.amount))
        .join(Income, Income.income_type_id == IncomeType.id)
        .filter(Income.farming_year_id == year_id, Income.is_gift.isnot(True)),
        Income.date_shamsi, d_from, d_to).group_by(IncomeType.id).all()
    income_items = sorted(
        [{'label': n, 'amount': int(a or 0)} for n, a in inc_rows if a],
        key=lambda i: -i['amount'])

    exp_rows = _rng(
        db.session.query(ExpenseCategory.name, func.sum(Expense.amount))
        .join(Expense, Expense.category_id == ExpenseCategory.id)
        .filter(Expense.farming_year_id == year_id),
        Expense.date_shamsi, d_from, d_to).group_by(ExpenseCategory.id).all()
    manual = [{'label': n, 'amount': int(a or 0)} for n, a in exp_rows]

    wage, food = _rng(
        db.session.query(func.coalesce(func.sum(DailyWork.total_wage), 0),
                         func.coalesce(func.sum(DailyWork.food_cost), 0))
        .filter(DailyWork.farming_year_id == year_id, DailyWork.is_temp.is_(False)),
        DailyWork.date_shamsi, d_from, d_to).one()

    mat_rows = _rng(
        db.session.query(WorkMaterial.quantity, WorkMaterial.unit_price, Material.default_price)
        .join(DailyWork, WorkMaterial.work_id == DailyWork.id)
        .join(Material, WorkMaterial.material_id == Material.id)
        .filter(DailyWork.farming_year_id == year_id, DailyWork.is_temp.is_(False)),
        DailyWork.date_shamsi, d_from, d_to).all()
    materials = int(round(sum((q or 0) * (up if up is not None else (dp or 0))
                              for q, up, dp in mat_rows)))

    auto = [
        {'label': 'دستمزد کارگران (کار روزانه)', 'amount': int(wage or 0), 'auto': True},
        {'label': 'غذای کارگران', 'amount': int(food or 0), 'auto': True},
        {'label': 'مواد مصرفی (کود و سم)', 'amount': materials, 'auto': True},
    ]
    expense_items = sorted([i for i in auto + manual if i['amount']], key=lambda i: -i['amount'])

    g_total, g_count = _rng(
        db.session.query(func.coalesce(func.sum(Income.amount), 0), func.count(Income.id))
        .filter(Income.farming_year_id == year_id, Income.is_gift.is_(True)),
        Income.date_shamsi, d_from, d_to).one()
    income_total = sum(i['amount'] for i in income_items)
    expense_total = sum(i['amount'] for i in expense_items)
    return {
        'income_items': income_items,
        'expense_items': expense_items,
        'income_total': income_total,
        'expense_total': expense_total,
        'net': income_total - expense_total,
        'gift_total': int(g_total or 0),
        'gift_count': int(g_count or 0),
    }


def recent_items(year_id, limit=6):
    items = []
    for w in (DailyWork.query.filter_by(farming_year_id=year_id, is_temp=False)
              .order_by(DailyWork.id.desc()).limit(limit)):
        items.append({'icon': 'fa-seedling', 'sign': 'minus',
                      'title': w.activity.name if w.activity else 'کار روزانه',
                      'amount': (w.total_wage or 0) + (w.food_cost or 0),
                      'date': w.date_shamsi, 'ts': w.created_at or datetime.min})
    for i in (Income.query.filter_by(farming_year_id=year_id).filter(Income.is_gift.isnot(True))
              .order_by(Income.id.desc()).limit(limit)):
        items.append({'icon': 'fa-coins', 'sign': 'plus', 'title': i.income_type.name,
                      'amount': i.amount or 0, 'date': i.date_shamsi,
                      'ts': i.created_at or datetime.min})
    for e in (Expense.query.filter_by(farming_year_id=year_id)
              .order_by(Expense.id.desc()).limit(limit)):
        items.append({'icon': 'fa-receipt', 'sign': 'minus', 'title': e.category.name,
                      'amount': e.amount or 0, 'date': e.date_shamsi,
                      'ts': e.created_at or datetime.min})
    items.sort(key=lambda x: x['ts'], reverse=True)
    return items[:limit]
