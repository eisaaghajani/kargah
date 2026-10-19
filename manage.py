# D:\kargah\manage.py  —  مدیریت کارگاه: سال‌ها، فعالیت‌ها، کودها و سموم
from datetime import timedelta

import jdatetime
from flask import Blueprint, render_template

from models import Activity, Material
from finance import _page_ctx

bp = Blueprint('manage', __name__)


@bp.route('/manage/<int:workshop_id>/<int:year_id>')
def manage_page(workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    return render_template(
        'manage.html', years=ctx['all_years'],
        activities=Activity.query.filter_by(workshop_id=workshop_id, is_active=True).order_by(Activity.id).all(),
        materials=Material.query.filter_by(workshop_id=workshop_id).order_by(Material.name).all(), **ctx)


@bp.app_context_processor
def _inject_dates():
    """تاریخ دیروز برای دکمه‌ی سریع «دیروز» در فرم ثبت کار."""
    return {'yesterday': (jdatetime.date.today() - timedelta(days=1)).strftime('%Y/%m/%d')}
