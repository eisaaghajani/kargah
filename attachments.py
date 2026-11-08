# D:\kargah\attachments.py  —  پیوست فاکتور/رسید برای هزینه و درآمد (عکس یا PDF)، با پیش‌نمایش و دانلود
import io
import os
import uuid

import jdatetime
from flask import Blueprint, g, jsonify, request, send_file
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.orm import object_session

from archive import _path, _remove_files, _save_image
from extensions import db
from finance import _err
from models import ArchivePhoto, Expense, FinanceFile, Income

bp = Blueprint('attach', __name__)
KINDS = {'expense': Expense, 'income': Income}
MAX_FILES = 10                       # حداکثر پیوست برای هر هزینه/درآمد
MAX_BYTES = 8 * 1024 * 1024          # حداکثر حجم هر فایل


@event.listens_for(FinanceFile, 'after_delete')
def _queue_delete(mapper, connection, target):
    """فایل‌های روی دیسک بعد از commit پاک می‌شوند (همان سازوکار آرشیو)."""
    s = object_session(target)
    if s is not None:
        s.info.setdefault('trash', []).extend([x for x in (target.filename, target.thumb) if x])


def _fj(f):
    return {'id': f.id, 'name': f.orig_name or 'پیوست', 'kind': f.kind, 'size': f.size_bytes or 0}


def _quota_error(adding):
    limit = current_user.photo_limit
    if limit is None:
        return None
    used = ArchivePhoto.query.count() + FinanceFile.query.count()
    if used + adding > limit:
        return 'سقف فضای عکس و پیوست پلن رایگان (%d فایل) پر می‌شود. برای حذف سقف، پلن حرفه‌ای بگیرید.' % limit
    return None


@bp.app_context_processor
def _inject():
    def files_of(kind, rec_id):
        """پیوست‌های هر ردیفِ لیست (یک‌بار برای کل صفحه از دیتابیس خوانده می‌شود)."""
        cache = g.get('_files_cache')
        if cache is None:
            cache = {'expense': {}, 'income': {}}
            yid = (request.view_args or {}).get('year_id')
            if yid:
                for model, col, key in ((Expense, FinanceFile.expense_id, 'expense'), (Income, FinanceFile.income_id, 'income')):
                    q = FinanceFile.query.join(model, col == model.id).filter(model.farming_year_id == yid).order_by(FinanceFile.id)
                    for f in q:
                        cache[key].setdefault(f.expense_id if key == 'expense' else f.income_id, []).append(_fj(f))
            g._files_cache = cache
        return cache.get(kind, {}).get(rec_id, [])
    return {'files_of': files_of, 'copyright_year': jdatetime.date.today().year}


@bp.route('/api/attachments/<kind>/<int:rec_id>', methods=['GET', 'POST'])
def attachments(kind, rec_id):
    model = KINDS.get(kind)
    if not model:
        return _err('نوع پیوست نامعتبر است.', 404)
    rec = db.session.get(model, rec_id)
    if not rec:
        return _err('ثبت پیدا نشد.', 404)
    if request.method == 'GET':
        return jsonify(success=True, files=[_fj(f) for f in rec.files])

    ups = [u for u in request.files.getlist('files') if u and u.filename]
    if not ups:
        return _err('فایلی انتخاب نشده است.')
    if len(rec.files) + len(ups) > MAX_FILES:
        return _err('حداکثر %d پیوست برای هر ثبت مجاز است.' % MAX_FILES)
    quota = _quota_error(len(ups))
    if quota:
        return _err(quota, 403)

    sub = 'f%d' % rec.farming_year_id          # پوشه‌ی جدا از عکس‌های آرشیو
    written, rows = [], []
    try:
        for u in ups:
            data = u.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('«%s» بزرگ‌تر از ۸ مگابایت است.' % u.filename[:40])
            name = os.path.basename(u.filename)[:150]
            if data[:5] == b'%PDF-':
                rel = '%s/%s.pdf' % (sub, uuid.uuid4().hex)
                os.makedirs(os.path.dirname(_path(rel)), exist_ok=True)
                with open(_path(rel), 'wb') as fh:
                    fh.write(data)
                written.append(rel)
                rows.append(FinanceFile(filename=rel, thumb=None, orig_name=name, kind='pdf', mime='application/pdf', size_bytes=len(data)))
            else:
                u.stream = io.BytesIO(data)
                rel, thumb, size = _save_image(u, sub)      # اعتبارسنجی با Pillow، کوچک‌سازی و بندانگشتی
                written += [rel, thumb]
                rows.append(FinanceFile(filename=rel, thumb=thumb, orig_name=name, kind='image', mime='image/jpeg', size_bytes=size))
        for r in rows:
            setattr(r, 'expense_id' if kind == 'expense' else 'income_id', rec.id)
            db.session.add(r)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        _remove_files(written)
        return _err(str(e))
    return jsonify(success=True, files=[_fj(f) for f in rec.files])


@bp.route('/api/attachments/file/<int:fid>', methods=['DELETE'])
def delete_file(fid):
    f = db.session.get(FinanceFile, fid)
    if not f:
        return _err('پیوست پیدا نشد.', 404)
    db.session.delete(f)
    db.session.commit()
    return jsonify(success=True)


def _serve(fid, thumb):
    f = db.session.get(FinanceFile, fid)
    rel = (f.thumb if thumb else f.filename) if f else None
    if not rel:
        return _err('پیدا نشد.', 404)
    inline_pdf = f.kind == 'pdf' and not thumb
    resp = send_file(_path(rel), mimetype='application/pdf' if inline_pdf else 'image/jpeg',
                     as_attachment=request.args.get('download') == '1',
                     download_name=(f.orig_name or 'attachment') + ('' if (f.orig_name or '').lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.webp')) else ('.pdf' if inline_pdf else '.jpg')))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.cache_control.private = True
    resp.cache_control.max_age = 3600
    return resp


@bp.route('/media/file/<int:fid>')
def file_media(fid):
    return _serve(fid, False)


@bp.route('/media/file/<int:fid>/thumb')
def file_thumb(fid):
    return _serve(fid, True)
