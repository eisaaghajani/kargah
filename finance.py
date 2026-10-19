# D:\kargah\finance.py  —  درآمد، هزینه، انواع و قیمت مواد
import re

import jdatetime
from flask import Blueprint, render_template, request, jsonify, abort

from extensions import db
from models import (Workshop, FarmingYear, Material, IncomeType, Income,
                    ExpenseCategory, Expense)

bp = Blueprint('finance', __name__)

KINDS = {
    'income': {'Type': IncomeType, 'Rec': Income, 'fk': 'income_type_id'},
    'expense': {'Type': ExpenseCategory, 'Rec': Expense, 'fk': 'category_id'},
}

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


# ---------------- کمکی‌ها ----------------
def _err(msg, code=400):
    return jsonify({'success': False, 'error': msg}), code


def _num(v, as_int=True):
    """عدد (با ارقام فارسی/کاما) -> int یا float؛ خالی -> None."""
    if v is None or str(v).strip() == '':
        return None
    s = str(v).translate(_DIGITS).replace(',', '').replace('،', '').replace('٫', '.').strip()
    try:
        f = float(s)
    except ValueError:
        raise ValueError('عدد واردشده معتبر نیست.')
    if f < 0:
        raise ValueError('عدد نمی‌تواند منفی باشد.')
    return int(round(f)) if as_int else f


def _date(v):
    s = str(v or '').translate(_DIGITS).strip()
    m = re.match(r'^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$', s)
    if not m:
        raise ValueError('تاریخ را مثل 1405/03/21 وارد کنید.')
    y, mo, d = map(int, m.groups())
    try:
        jdatetime.date(y, mo, d)
    except ValueError:
        raise ValueError('تاریخ معتبر نیست.')
    return '%04d/%02d/%02d' % (y, mo, d)


def _page_ctx(workshop_id, year_id):
    workshop = db.get_or_404(Workshop, workshop_id)
    year = db.get_or_404(FarmingYear, year_id)
    if year.workshop_id != workshop.id:
        abort(404)
    all_years = FarmingYear.query.filter_by(workshop_id=workshop.id).order_by(FarmingYear.id).all()
    return {'workshop': workshop, 'farming_year': year, 'all_years': all_years,
            'today': jdatetime.date.today().strftime('%Y/%m/%d')}


def _item(kind, r):
    t = r.income_type if kind == 'income' else r.category
    d = {'id': r.id, 'date': r.date_shamsi, 'type_id': t.id, 'type_name': t.name,
         'amount': r.amount or 0, 'description': r.description or ''}
    if kind == 'income':
        d.update(unit=t.unit or '', quantity=r.quantity, unit_price=r.unit_price, buyer=r.buyer or '')
    return d


def _type_json(t):
    return {'id': t.id, 'name': t.name, 'unit': getattr(t, 'unit', '') or ''}


# ---------------- صفحات ----------------
def _ledger(kind, workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    cfg = KINDS[kind]
    Rec, Type, fk = cfg['Rec'], cfg['Type'], cfg['fk']
    all_types = Type.query.filter_by(workshop_id=workshop_id).order_by(Type.id).all()
    filter_type = request.args.get('type', type=int)
    q = Rec.query.filter_by(farming_year_id=year_id)
    if filter_type:
        q = q.filter(getattr(Rec, fk) == filter_type)
    items = [_item(kind, r) for r in q.order_by(Rec.date_shamsi.desc(), Rec.id.desc()).all()]
    return render_template(
        'finance_ledger.html', kind=kind, is_income=(kind == 'income'), items=items,
        total=sum(i['amount'] for i in items), filter_type=filter_type,
        all_types=[_type_json(t) for t in all_types],
        types=[_type_json(t) for t in all_types if t.is_active], **ctx)


@bp.route('/finance/<int:workshop_id>/<int:year_id>/income')
def income_page(workshop_id, year_id):
    return _ledger('income', workshop_id, year_id)


@bp.route('/finance/<int:workshop_id>/<int:year_id>/expense')
def expense_page(workshop_id, year_id):
    return _ledger('expense', workshop_id, year_id)


@bp.route('/finance/<int:workshop_id>/<int:year_id>/settings')
def settings_page(workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    return render_template(
        'finance_settings.html',
        income_types=IncomeType.query.filter_by(workshop_id=workshop_id).order_by(IncomeType.id).all(),
        expense_cats=ExpenseCategory.query.filter_by(workshop_id=workshop_id).order_by(ExpenseCategory.id).all(),
        materials=Material.query.filter_by(workshop_id=workshop_id).order_by(Material.name).all(), **ctx)


# ---------------- API: ثبت‌ها ----------------
def _apply(kind, rec, data, year):
    cfg = KINDS[kind]
    rec.date_shamsi = _date(data.get('date'))
    t = db.session.get(cfg['Type'], _num(data.get('type_id')) or 0)
    if not t or t.workshop_id != year.workshop_id:
        raise ValueError('نوع انتخاب‌شده معتبر نیست.')
    setattr(rec, cfg['fk'], t.id)
    rec.description = (data.get('description') or '').strip()
    amount = _num(data.get('amount'))
    if kind == 'income':
        q, p = _num(data.get('quantity'), False), _num(data.get('unit_price'))
        if amount is None and q is not None and p is not None:
            amount = int(round(q * p))
        rec.quantity, rec.unit_price = q, p
        rec.buyer = (data.get('buyer') or '').strip()[:100]
    if not amount:
        raise ValueError('مبلغ را وارد کنید.')
    rec.amount = amount


@bp.route('/api/finance/<kind>', methods=['POST'])
def api_create(kind):
    if kind not in KINDS:
        abort(404)
    data = request.get_json(silent=True) or {}
    try:
        year = db.session.get(FarmingYear, _num(data.get('year_id')) or 0)
        if not year:
            return _err('سال زراعی پیدا نشد.', 404)
        rec = KINDS[kind]['Rec'](farming_year_id=year.id)
        _apply(kind, rec, data, year)
    except ValueError as e:
        return _err(str(e))
    db.session.add(rec)
    db.session.commit()
    return jsonify({'success': True, 'id': rec.id})


@bp.route('/api/finance/<kind>/<int:rec_id>', methods=['PUT', 'DELETE'])
def api_update(kind, rec_id):
    if kind not in KINDS:
        abort(404)
    rec = db.session.get(KINDS[kind]['Rec'], rec_id)
    if not rec:
        return _err('مورد پیدا نشد.', 404)
    if request.method == 'DELETE':
        db.session.delete(rec)
        db.session.commit()
        return jsonify({'success': True})
    try:
        _apply(kind, rec, request.get_json(silent=True) or {}, db.session.get(FarmingYear, rec.farming_year_id))
    except ValueError as e:
        db.session.rollback()
        return _err(str(e))
    db.session.commit()
    return jsonify({'success': True})


# ---------------- API: انواع درآمد / دسته‌های هزینه ----------------
@bp.route('/api/finance/types/<kind>', methods=['POST'])
def api_type_create(kind):
    if kind not in KINDS:
        abort(404)
    Type = KINDS[kind]['Type']
    data = request.get_json(silent=True) or {}
    try:
        wid = _num(data.get('workshop_id')) or 0
    except ValueError as e:
        return _err(str(e))
    name = (data.get('name') or '').strip()[:100]
    if not db.session.get(Workshop, wid):
        return _err('کارگاه پیدا نشد.', 404)
    if not name:
        return _err('نام را وارد کنید.')
    if Type.query.filter_by(workshop_id=wid, name=name).first():
        return _err('این نام قبلاً وجود دارد.')
    t = Type(name=name, workshop_id=wid)
    if kind == 'income':
        t.unit = (data.get('unit') or 'کیلوگرم').strip()[:20]
    db.session.add(t)
    db.session.commit()
    return jsonify({'success': True, 'id': t.id})


@bp.route('/api/finance/types/<kind>/<int:type_id>', methods=['PUT', 'DELETE'])
def api_type_update(kind, type_id):
    if kind not in KINDS:
        abort(404)
    cfg = KINDS[kind]
    t = db.session.get(cfg['Type'], type_id)
    if not t:
        return _err('مورد پیدا نشد.', 404)
    if request.method == 'DELETE':
        used = cfg['Rec'].query.filter(getattr(cfg['Rec'], cfg['fk']) == t.id).count()
        if used:
            return _err('این مورد در %d ثبت استفاده شده؛ به‌جای حذف، غیرفعالش کنید.' % used)
        db.session.delete(t)
        db.session.commit()
        return jsonify({'success': True})
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()[:100]
    if not name:
        return _err('نام را وارد کنید.')
    clash = cfg['Type'].query.filter_by(workshop_id=t.workshop_id, name=name).first()
    if clash and clash.id != t.id:
        return _err('این نام قبلاً وجود دارد.')
    t.name = name
    t.is_active = bool(data.get('is_active', True))
    if kind == 'income':
        t.unit = (data.get('unit') or t.unit or 'کیلوگرم').strip()[:20]
    db.session.commit()
    return jsonify({'success': True})


# ---------------- API: قیمت مواد ----------------
@bp.route('/api/finance/material-price/<int:material_id>', methods=['PUT'])
def api_material_price(material_id):
    m = db.session.get(Material, material_id)
    if not m:
        return _err('ماده پیدا نشد.', 404)
    try:
        m.default_price = _num((request.get_json(silent=True) or {}).get('price')) or 0
    except ValueError as e:
        return _err(str(e))
    db.session.commit()
    return jsonify({'success': True})
