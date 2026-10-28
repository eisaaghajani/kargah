# D:\kargah\reports.py  —  گزارش مالی (بازه دلخواه، ماهانه، مقایسه سال‌ها، چاپ، CSV)
import csv
import io
import re
from datetime import timedelta

import jdatetime
from flask import Blueprint, render_template, request, Response

from extensions import db
from models import FarmingYear, Income, Expense, DailyWork
from services import year_totals
from finance import _date, _page_ctx

bp = Blueprint('reports', __name__)

MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
          'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']


def _presets():
    t = jdatetime.date.today()
    f = lambda d: d.strftime('%Y/%m/%d')
    return [
        ('کل سال زراعی', '', ''),
        ('این ماه', f(t.replace(day=1)), f(t)),
        ('۳۰ روز اخیر', f(t - timedelta(days=29)), f(t)),
        ('۹۰ روز اخیر', f(t - timedelta(days=89)), f(t)),
    ]


def _range():
    """(از, تا, خطا) از پارامترهای آدرس؛ در صورت خطا بازه نادیده گرفته می‌شود."""
    try:
        raw_from = (request.args.get('from') or '').strip()
        raw_to = (request.args.get('to') or '').strip()
        d_from = _date(raw_from) if raw_from else None
        d_to = _date(raw_to) if raw_to else None
        if d_from and d_to and d_from > d_to:
            raise ValueError('تاریخ شروع نباید بعد از تاریخ پایان باشد.')
        return d_from, d_to, None
    except ValueError as e:
        return None, None, str(e)


def _monthly(year_id, d_from, d_to):
    keys = set()
    for Model, extra in ((Income, Income.is_gift.isnot(True)), (Expense, None), (DailyWork, DailyWork.is_temp.is_(False))):
        q = db.session.query(Model.date_shamsi).filter(Model.farming_year_id == year_id)
        if extra is not None:
            q = q.filter(extra)
        if d_from:
            q = q.filter(Model.date_shamsi >= d_from)
        if d_to:
            q = q.filter(Model.date_shamsi <= d_to)
        keys.update(r[0][:7] for r in q.distinct() if r[0] and re.match(r'^\d{4}/\d{2}', r[0]))
    rows = []
    for k in sorted(keys):
        month = int(k[5:7])
        if not 1 <= month <= 12:
            continue
        lo = max(d_from or '', k + '/01')
        hi = min(d_to or '9999/99/99', k + '/31')
        t = year_totals(year_id, lo, hi)
        rows.append({'label': '%s %s' % (MONTHS[month - 1], k[:4]), 'income': t['income_total'],
                     'expense': t['expense_total'], 'net': t['net']})
    return rows


@bp.route('/reports/<int:workshop_id>/<int:year_id>')
def report_page(workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    d_from, d_to, error = _range()
    totals = year_totals(year_id, d_from, d_to)
    compare = []
    for y in ctx['all_years']:
        t = year_totals(y.id)
        compare.append({'id': y.id, 'year': y.year, 'income': t['income_total'],
                        'expense': t['expense_total'], 'net': t['net']})
    return render_template(
        'reports.html', totals=totals, d_from=d_from or '', d_to=d_to or '', error=error,
        presets=_presets(), months=_monthly(year_id, d_from, d_to), compare=compare, **ctx)


@bp.route('/reports/<int:workshop_id>/<int:year_id>/export.csv')
def export_csv(workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    d_from, d_to, _ = _range()
    t = year_totals(year_id, d_from, d_to)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['گزارش مالی', ctx['workshop'].name, 'سال زراعی', ctx['farming_year'].year])
    w.writerow(['از', d_from or 'ابتدا', 'تا', d_to or 'انتها'])
    w.writerow([])
    w.writerow(['درآمد', 'مبلغ (تومان)'])
    w.writerows([[i['label'], i['amount']] for i in t['income_items']])
    w.writerow(['جمع درآمد', t['income_total']])
    if t['gift_count']:
        w.writerow(['هدیه‌ها (دریافت نشده؛ جزو درآمد نیست)', t['gift_total'], '%d مورد' % t['gift_count']])
    w.writerow([])
    w.writerow(['هزینه', 'مبلغ (تومان)'])
    w.writerows([[i['label'], i['amount']] for i in t['expense_items']])
    w.writerow(['جمع هزینه', t['expense_total']])
    w.writerow([])
    w.writerow(['سود (زیان)', t['net']])
    name = re.sub(r'[^0-9A-Za-z_-]+', '', str(ctx['farming_year'].year)) or 'year'
    return Response('\ufeff' + out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=report-%s.csv' % name})
