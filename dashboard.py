# D:\kargah\dashboard.py  —  داشبورد + ناوبری مشترک صفحات جدید
import jdatetime
from flask import Blueprint, render_template, request, current_app, url_for, abort

from extensions import db
from models import Workshop, FarmingYear
from services import year_totals, recent_items

bp = Blueprint('dashboard', __name__)

# (endpoint, عنوان کوتاه, توضیح, آیکون, رنگ)
NAV = [
    ('dashboard.dashboard', 'داشبورد', 'نمای کلی سال زراعی', 'fa-th-large', 'green'),
    ('workshop_dashboard', 'کار روزانه', 'ثبت کار، کارگر و مواد مصرفی', 'fa-seedling', 'green'),
    ('finance.income_page', 'درآمد', 'ثبت فروش انگور، کشمش، آبغوره و...', 'fa-coins', 'orange'),
    ('finance.expense_page', 'هزینه', 'آبیاری، کارگر، گرد و روغن و...', 'fa-receipt', 'red'),
    ('reports.report_page', 'گزارش مالی', 'سود و زیان در بازه دلخواه', 'fa-chart-pie', 'blue'),
    ('archive.archive_page', 'آرشیو', 'عکس و یادداشت مراحل رشد', 'fa-images', 'purple'),
    ('inventory.inventory_page', 'انبار', 'موجودی و فاکتور خرید سم و کود', 'fa-warehouse', 'blue'),
    ('finance.settings_page', 'تنظیمات مالی', 'انواع درآمد و هزینه، قیمت مواد', 'fa-sliders-h', 'gray'),
    ('manage.manage_page', 'مدیریت کارگاه', 'سال‌ها، فعالیت‌ها، کودها و سموم', 'fa-cog', 'gray'),
]


def build_nav(workshop_id, year_id):
    """صفحاتی که هنوز نصب نشده‌اند href=None می‌گیرند و در داشبورد «به‌زودی» دیده می‌شوند."""
    out = []
    for ep, short, desc, icon, tone in NAV:
        href = (url_for(ep, workshop_id=workshop_id, year_id=year_id)
                if ep in current_app.view_functions else None)
        out.append({'endpoint': ep, 'short': short, 'desc': desc, 'icon': icon,
                    'tone': tone, 'href': href})
    return out


@bp.app_context_processor
def inject_nav():
    va = request.view_args or {}
    if 'workshop_id' in va and 'year_id' in va:
        return {'nav_items': build_nav(va['workshop_id'], va['year_id'])}
    return {'nav_items': []}


@bp.app_template_filter('toman')
def toman(value):
    return '{:,}'.format(int(value or 0))


@bp.route('/dashboard/<int:workshop_id>/<int:year_id>')
def dashboard(workshop_id, year_id):
    workshop = db.get_or_404(Workshop, workshop_id)
    year = db.get_or_404(FarmingYear, year_id)
    if year.workshop_id != workshop.id:
        abort(404)
    all_years = FarmingYear.query.filter_by(workshop_id=workshop.id).order_by(FarmingYear.id).all()
    totals = year_totals(year.id)
    max_exp = max([i['amount'] for i in totals['expense_items']] or [1])
    return render_template(
        'dashboard.html', workshop=workshop, farming_year=year, all_years=all_years,
        today=jdatetime.date.today().strftime('%Y/%m/%d'),
        totals=totals, max_exp=max_exp, recent=recent_items(year.id))
