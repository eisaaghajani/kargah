# D:\kargah\inventory.py  —  انبار سم و کود: فاکتور خرید، موجودی، تنظیم انبار
#
# موجودی هر ماده = خریدها (فاکتورها، همه‌ی سال‌ها) + تنظیم‌های انبار − مصرف در کارهای روزانه.
# موجودی «محاسبه می‌شود» و ذخیره نمی‌شود؛ پس ویرایش یا حذف یک کار، موجودی را خودکار درست می‌کند.
# هزینه‌ی مواد همچنان هنگام مصرف حساب می‌شود؛ خرید فقط انبار را پر می‌کند (تا هزینه دوبار حساب نشود).
import jdatetime
from flask import Blueprint, g, has_request_context, jsonify, render_template, request
from sqlalchemy import func

from extensions import db
from finance import _date, _err, _num, _page_ctx
from models import (Activity, DailyWork, FarmingYear, Material, MaterialInvoice, MaterialPurchase,
                    StockAdjustment, WorkMaterial)

bp = Blueprint('inventory', __name__)
REASONS = ['شمارش انبار', 'موجودی اول دوره', 'ضایعات / خرابی', 'هدیه یا قرض دادن', 'سایر']


def _ok(**kw):
    return jsonify(dict(success=True, **kw))


def _body():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


# ---------------------------------------------------------------- محاسبه‌ی موجودی
def stock_map(workshop_id):
    """{material_id: {purchased, adjusted, used, stock}} برای همه‌ی مواد کارگاه (انبار بین سال‌ها مشترک است)."""
    mids = [m.id for m in Material.query.filter_by(workshop_id=workshop_id)]
    if not mids:
        return {}
    def agg(col, val, *joins_filters):
        q = db.session.query(col, func.coalesce(func.sum(val), 0)).filter(col.in_(mids))
        for f in joins_filters:
            q = q.filter(f)
        return dict(q.group_by(col).all())
    purchased = agg(MaterialPurchase.material_id, MaterialPurchase.quantity)
    adjusted = agg(StockAdjustment.material_id, StockAdjustment.quantity)
    used = dict(db.session.query(WorkMaterial.material_id, func.coalesce(func.sum(WorkMaterial.quantity), 0))
                .join(DailyWork, WorkMaterial.work_id == DailyWork.id)
                .filter(WorkMaterial.material_id.in_(mids), DailyWork.is_temp.isnot(True))
                .group_by(WorkMaterial.material_id).all())
    out = {}
    for mid in mids:
        p, a, u = float(purchased.get(mid, 0)), float(adjusted.get(mid, 0)), float(used.get(mid, 0))
        out[mid] = {'purchased': p, 'adjusted': a, 'used': u, 'stock': round(p + a - u, 6)}
    return out


@bp.app_context_processor
def _inject_stock():
    def stock_of(material_id):
        wid = (request.view_args or {}).get('workshop_id') if has_request_context() else None
        if wid is None:
            return 0
        cache = g.get('_stock_cache')
        if cache is None or cache[0] != wid:
            cache = (wid, stock_map(wid))
            g._stock_cache = cache
        return round(cache[1].get(material_id, {}).get('stock', 0.0), 3)
    return {'stock_of': stock_of}


def _year_stats(workshop_id, year_id):
    bought = {r[0]: (float(r[1]), int(r[2])) for r in
              db.session.query(MaterialPurchase.material_id, func.sum(MaterialPurchase.quantity), func.sum(MaterialPurchase.amount))
              .join(MaterialInvoice, MaterialPurchase.invoice_id == MaterialInvoice.id)
              .filter(MaterialInvoice.farming_year_id == year_id).group_by(MaterialPurchase.material_id)}
    used = {r[0]: float(r[1]) for r in
            db.session.query(WorkMaterial.material_id, func.sum(WorkMaterial.quantity))
            .join(DailyWork, WorkMaterial.work_id == DailyWork.id)
            .filter(DailyWork.farming_year_id == year_id, DailyWork.is_temp.isnot(True)).group_by(WorkMaterial.material_id)}
    return bought, used


def _state(m, s):
    if not (s['purchased'] or s['adjusted']):
        return 'none'
    if s['stock'] < -1e-9:
        return 'neg'
    if m.min_stock and s['stock'] <= m.min_stock + 1e-9:
        return 'low'
    return 'ok'


def _inv_json(inv):
    return {'id': inv.id, 'date': inv.date_shamsi, 'seller': inv.seller or '', 'invoice_no': inv.invoice_no or '',
            'description': inv.description or '',
            'items': [{'material_id': i.material_id, 'name': i.material.name if i.material else '', 'unit': i.material.unit if i.material else '',
                       'quantity': i.quantity, 'unit_price': i.unit_price, 'amount': i.amount or 0} for i in inv.items]}


# ---------------------------------------------------------------- صفحه
@bp.route('/inventory/<int:workshop_id>/<int:year_id>')
def inventory_page(workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    mats = Material.query.filter_by(workshop_id=workshop_id).order_by(Material.name).all()
    sm = stock_map(workshop_id)
    bought, used = _year_stats(workshop_id, year_id)
    rows = []
    for m in mats:
        s = sm.get(m.id, {'purchased': 0, 'adjusted': 0, 'used': 0, 'stock': 0})
        b = bought.get(m.id, (0.0, 0))
        rows.append({'id': m.id, 'name': m.name, 'type': m.type or '', 'unit': m.unit or '', 'price': m.default_price or 0,
                     'min_stock': m.min_stock, 'stock': round(s['stock'], 3), 'purchased': round(s['purchased'], 3),
                     'used': round(s['used'], 3), 'year_bought': round(b[0], 3), 'year_amount': b[1],
                     'year_used': round(used.get(m.id, 0.0), 3), 'state': _state(m, s)})
    rows.sort(key=lambda r: ({'neg': 0, 'low': 1, 'ok': 2, 'none': 3}[r['state']], r['name']))   # اول کسری/کم‌موجودی
    invoices = (MaterialInvoice.query.filter_by(farming_year_id=year_id)
                .order_by(MaterialInvoice.date_shamsi.desc(), MaterialInvoice.id.desc()).all())
    inv_json = [_inv_json(i) for i in invoices]
    year_total = sum(i['amount'] for inv in inv_json for i in inv['items'])
    return render_template('inventory.html', rows=rows, invoices=inv_json, year_total=year_total,
                           alerts=sum(1 for r in rows if r['state'] in ('low', 'neg')), reasons=REASONS, **ctx)


# ---------------------------------------------------------------- فاکتور خرید
def _parse_invoice(data, year):
    date = _date(data.get('date'))
    seller = (data.get('seller') or '').strip()[:100]
    number = (data.get('invoice_no') or '').strip()[:50]
    desc = (data.get('description') or '').strip()[:1000]
    items = data.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('حداقل یک ردیف کالا وارد کنید.')
    if len(items) > 60:
        raise ValueError('تعداد ردیف‌های فاکتور زیاد است.')
    rows = []
    for it in items:
        if not isinstance(it, dict):
            raise ValueError('ردیف‌های فاکتور معتبر نیست.')
        mat = db.session.get(Material, _num(it.get('material_id')) or 0)
        if not mat or mat.workshop_id != year.workshop_id:
            raise ValueError('ماده‌ی انتخاب‌شده معتبر نیست.')
        q = _num(it.get('quantity'), False)
        if not q or q <= 0:
            raise ValueError('مقدار هر ردیف را وارد کنید.')
        p, a = _num(it.get('unit_price')), _num(it.get('amount'))
        if a:
            p = int(round(a / q))
        elif p:
            a = int(round(q * p))
        else:
            a, p = 0, None
        rows.append((mat, q, p, a))
    return date, seller, number, desc, rows


def _truthy(v, default=True):
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ('1', 'true', 'on', 'yes')
    return bool(v)


def _save_invoice(inv, data, year):
    date, seller, number, desc, rows = _parse_invoice(data, year)
    inv.date_shamsi, inv.seller, inv.invoice_no, inv.description = date, seller, number, desc
    inv.items = [MaterialPurchase(material_id=m.id, quantity=q, unit_price=p, amount=a) for m, q, p, a in rows]
    if _truthy(data.get('update_prices')):
        for m, q, p, a in rows:
            if p:
                m.default_price = p        # قیمتِ آخرین خرید، قیمت جاری ماده می‌شود


@bp.route('/api/inventory/invoices', methods=['POST'])
def invoice_create():
    data = _body()
    try:
        year = db.session.get(FarmingYear, _num(data.get('year_id')) or 0)
        if not year:
            return _err('سال زراعی پیدا نشد.', 404)
        inv = MaterialInvoice(farming_year_id=year.id)
        _save_invoice(inv, data, year)
    except ValueError as e:
        db.session.rollback()
        return _err(str(e))
    db.session.add(inv)
    db.session.commit()
    return _ok(id=inv.id)


@bp.route('/api/inventory/invoices/<int:inv_id>', methods=['PUT', 'DELETE'])
def invoice_update(inv_id):
    inv = db.session.get(MaterialInvoice, inv_id)
    if not inv:
        return _err('فاکتور پیدا نشد.', 404)
    if request.method == 'DELETE':
        db.session.delete(inv)
        db.session.commit()
        return _ok()
    try:
        _save_invoice(inv, _body(), db.session.get(FarmingYear, inv.farming_year_id))
    except ValueError as e:
        db.session.rollback()
        return _err(str(e))
    db.session.commit()
    return _ok()


# ---------------------------------------------------------------- تنظیم انبار و هشدار
@bp.route('/api/inventory/adjust', methods=['POST'])
def adjust():
    d = _body()
    mat = db.session.get(Material, _num(d.get('material_id')) or 0)
    if not mat:
        return _err('ماده پیدا نشد.', 404)
    try:
        new_qty = _num(d.get('new_quantity'), False)
        date = _date(d.get('date') or jdatetime.date.today().strftime('%Y/%m/%d'))
    except ValueError as e:
        return _err(str(e))
    if new_qty is None:
        return _err('موجودی شمارش‌شده را وارد کنید.')
    cur = stock_map(mat.workshop_id).get(mat.id, {}).get('stock', 0.0)
    delta = round(new_qty - cur, 6)
    if abs(delta) < 1e-9:
        return _err('موجودی همین مقدار است؛ تغییری لازم نیست.')
    reason = (d.get('reason') or 'شمارش انبار').strip()[:100]
    db.session.add(StockAdjustment(material_id=mat.id, date_shamsi=date, quantity=delta, reason=reason))
    db.session.commit()
    return _ok(delta=delta, stock=round(new_qty, 6))


@bp.route('/api/inventory/material/<int:material_id>', methods=['PUT'])
def material_settings(material_id):
    mat = db.session.get(Material, material_id)
    if not mat:
        return _err('ماده پیدا نشد.', 404)
    try:
        mat.min_stock = _num(_body().get('min_stock'), False) or None
    except ValueError as e:
        return _err(str(e))
    db.session.commit()
    return _ok()


@bp.route('/api/inventory/material/<int:material_id>/movements')
def movements(material_id):
    mat = db.session.get(Material, material_id)
    if not mat:
        return _err('ماده پیدا نشد.', 404)
    rows = []
    for p in MaterialPurchase.query.filter_by(material_id=mat.id):
        inv = p.invoice
        rows.append({'date': inv.date_shamsi, 'kind': 'purchase', 'qty': p.quantity,
                     'note': ' · '.join(x for x in (inv.seller, inv.invoice_no) if x) or 'فاکتور خرید'})
    q = (db.session.query(WorkMaterial.quantity, DailyWork.date_shamsi, Activity.name)
         .join(DailyWork, WorkMaterial.work_id == DailyWork.id)
         .outerjoin(Activity, DailyWork.activity_id == Activity.id)
         .filter(WorkMaterial.material_id == mat.id, DailyWork.is_temp.isnot(True)))
    for qty, date, act in q:
        rows.append({'date': date, 'kind': 'use', 'qty': -(qty or 0), 'note': act or 'کار روزانه'})
    for a in StockAdjustment.query.filter_by(material_id=mat.id):
        rows.append({'date': a.date_shamsi, 'kind': 'adjust', 'qty': a.quantity, 'note': a.reason or 'تنظیم انبار'})
    rows.sort(key=lambda r: r['date'] or '', reverse=True)
    s = stock_map(mat.workshop_id).get(mat.id, {})
    return jsonify({'success': True, 'name': mat.name, 'unit': mat.unit or '', 'stock': s.get('stock', 0), 'rows': rows[:300]})
