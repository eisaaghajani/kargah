# D:\kargah\archive.py  —  آرشیو عکس و یادداشت مراحل رشد (با سقف عکس بر اساس پلن)
import os
import uuid

import click
from flask import Blueprint, render_template, request, jsonify, abort, send_file, current_app
from flask.cli import with_appcontext
from flask_login import current_user
from PIL import Image, ImageOps
from sqlalchemy import event, func
from sqlalchemy.orm import Session, object_session

from extensions import db
from models import FarmingYear, ArchiveEntry, ArchivePhoto, User
from finance import _date, _page_ctx, _err

bp = Blueprint('archive', __name__)

DEFAULT_STAGES = ['خواب زمستانی', 'هرس', 'جوانه‌زنی', 'گل‌دهی', 'غوره', 'رنگ‌گیری',
                  'برداشت', 'کشمش‌سازی', 'سم‌پاشی', 'آبیاری', 'آفت و بیماری', 'سایر']
MAX_SIDE, THUMB_SIDE = 1600, 400


@bp.record_once
def _setup(state):
    state.app.config.setdefault('MAX_CONTENT_LENGTH', 64 * 1024 * 1024)  # حداکثر حجم هر درخواست
    state.app.cli.add_command(set_plan)


# ---------------- فایل‌ها ----------------
def _root():
    return os.path.join(current_app.instance_path, 'uploads')


def _path(rel):
    root = os.path.normpath(_root())
    p = os.path.normpath(os.path.join(root, rel))
    if not p.startswith(root + os.sep):
        abort(404)
    return p


def _save_image(storage, year_id):
    try:
        img = Image.open(storage.stream)
        img.load()
    except Exception:
        raise ValueError('یکی از فایل‌ها عکس معتبر نیست.')
    img = ImageOps.exif_transpose(img)
    if img.mode != 'RGB':
        if 'A' in img.getbands() or img.mode == 'P':
            rgba = img.convert('RGBA')
            bg = Image.new('RGB', rgba.size, 'white')
            bg.paste(rgba, mask=rgba.split()[3])
            img = bg
        else:
            img = img.convert('RGB')
    big, thumb = img.copy(), img.copy()
    big.thumbnail((MAX_SIDE, MAX_SIDE))
    thumb.thumbnail((THUMB_SIDE, THUMB_SIDE))
    name = uuid.uuid4().hex
    os.makedirs(os.path.join(_root(), str(year_id)), exist_ok=True)
    rel, rel_t = '%s/%s.jpg' % (year_id, name), '%s/%s_t.jpg' % (year_id, name)
    big.save(_path(rel), 'JPEG', quality=82, optimize=True)
    thumb.save(_path(rel_t), 'JPEG', quality=75)
    return rel, rel_t, os.path.getsize(_path(rel))


def _remove_files(rels):
    for rel in rels:
        try:
            os.remove(_path(rel))
        except Exception:
            pass


@event.listens_for(ArchivePhoto, 'after_delete')
def _queue_files(mapper, connection, target):
    s = object_session(target)
    if s is not None:
        s.info.setdefault('trash', []).extend([target.filename, target.thumb])


@event.listens_for(Session, 'after_commit')
def _purge_files(session):
    _remove_files(session.info.pop('trash', []))


@event.listens_for(Session, 'after_rollback')
def _forget_files(session):
    session.info.pop('trash', None)


# ---------------- پلن / سقف عکس ----------------
def _limit_error(adding, removing=0):
    limit = current_user.photo_limit
    if limit is None or adding <= 0:
        return None
    used = ArchivePhoto.query.count() - removing
    if used + adding > limit:
        return ('سقف پلن رایگان %d عکس است و %d جای خالی دارید. '
                'برای عکس نامحدود، پلن حرفه‌ای را فعال کنید.' % (limit, max(limit - used, 0)))
    return None


@click.command('set-plan')
@click.argument('plan', type=click.Choice(['free', 'pro']))
@click.option('--user', 'ident', default=None, help='نام یا ایمیل کاربر (اگر فقط یک کاربر هست لازم نیست)')
@with_appcontext
def set_plan(plan, ident):
    """تغییر پلن کاربر:  flask --app app set-plan pro"""
    if ident:
        user = (User.query.filter(func.lower(User.email) == ident.lower()).first()
                or User.query.filter_by(name=ident).first())
    else:
        users = User.query.all()
        user = users[0] if len(users) == 1 else None
    if not user:
        raise click.ClickException('کاربر مشخص نیست؛ از --user استفاده کنید.')
    user.plan = plan
    user.plan_expires_at = None   # [patch10] تنظیم دستی = دائمی
    db.session.commit()
    click.echo('پلن %s روی «%s» تنظیم شد.' % (plan, user.name))


# ---------------- صفحه ----------------
@bp.route('/archive/<int:workshop_id>/<int:year_id>')
def archive_page(workshop_id, year_id):
    ctx = _page_ctx(workshop_id, year_id)
    stage = (request.args.get('stage') or '').strip()
    base = ArchiveEntry.query.filter_by(farming_year_id=year_id)
    used_stages = [s for (s,) in db.session.query(ArchiveEntry.stage)
                   .filter(ArchiveEntry.farming_year_id == year_id).distinct() if s]
    q = base.filter_by(stage=stage) if stage else base
    entries = q.order_by(ArchiveEntry.date_shamsi.desc(), ArchiveEntry.id.desc()).all()
    items = [{'id': e.id, 'title': e.title, 'stage': e.stage or '', 'date': e.date_shamsi,
              'description': e.description or '', 'photos': [p.id for p in e.photos]} for e in entries]
    return render_template(
        'archive.html', items=items, stage=stage, used_stages=used_stages,
        suggestions=list(dict.fromkeys(DEFAULT_STAGES + used_stages)),
        used=ArchivePhoto.query.count(), limit=current_user.photo_limit, plan=current_user.effective_plan, **ctx)


@bp.route('/media/<int:photo_id>')
def media(photo_id):
    return _send(photo_id, False)


@bp.route('/media/<int:photo_id>/thumb')
def media_thumb(photo_id):
    return _send(photo_id, True)


def _send(photo_id, thumb):
    p = db.session.get(ArchivePhoto, photo_id)
    if not p:
        abort(404)
    resp = send_file(_path(p.thumb if thumb else p.filename), mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'private, max-age=86400'
    return resp


# ---------------- API ----------------
def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def _fill(entry, f):
    entry.date_shamsi = _date(f.get('date'))
    title = (f.get('title') or '').strip()
    if not title:
        raise ValueError('عنوان را وارد کنید.')
    entry.title = title[:150]
    entry.stage = (f.get('stage') or '').strip()[:60]
    entry.description = (f.get('description') or '').strip()


def _uploads():
    return [x for x in request.files.getlist('photos') if x and x.filename]


def _store(files, year_id):
    saved = []
    try:
        for fs in files:
            saved.append(_save_image(fs, year_id))
    except ValueError:
        _remove_files([r for r, _, _ in saved] + [t for _, t, _ in saved])
        raise
    return saved


@bp.route('/api/archive/entries', methods=['POST'])
def api_create():
    year = db.session.get(FarmingYear, _int(request.form.get('year_id')))
    if not year:
        return _err('سال زراعی پیدا نشد.', 404)
    entry = ArchiveEntry(farming_year_id=year.id)
    files = _uploads()
    try:
        _fill(entry, request.form)
        limit_msg = _limit_error(len(files))
        if limit_msg:
            return _err(limit_msg, 403)
        saved = _store(files, year.id)
    except ValueError as e:
        return _err(str(e))
    try:
        db.session.add(entry)
        for rel, rel_t, size in saved:
            entry.photos.append(ArchivePhoto(filename=rel, thumb=rel_t, size_bytes=size))
        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_files([r for r, _, _ in saved] + [t for _, t, _ in saved])
        return _err('ذخیره نشد.', 500)
    return jsonify({'success': True, 'id': entry.id})


@bp.route('/api/archive/entries/<int:entry_id>', methods=['POST', 'DELETE'])
def api_entry(entry_id):
    entry = db.session.get(ArchiveEntry, entry_id)
    if not entry:
        return _err('مورد پیدا نشد.', 404)
    if request.method == 'DELETE':
        db.session.delete(entry)
        db.session.commit()
        return jsonify({'success': True})
    remove_ids = {_int(x) for x in (request.form.get('remove_ids') or '').split(',') if x.strip()}
    to_remove = [p for p in entry.photos if p.id in remove_ids]
    files = _uploads()
    try:
        _fill(entry, request.form)
        limit_msg = _limit_error(len(files), removing=len(to_remove))
        if limit_msg:
            db.session.rollback()
            return _err(limit_msg, 403)
        saved = _store(files, entry.farming_year_id)
    except ValueError as e:
        db.session.rollback()
        return _err(str(e))
    try:
        for p in to_remove:
            db.session.delete(p)
        for rel, rel_t, size in saved:
            entry.photos.append(ArchivePhoto(filename=rel, thumb=rel_t, size_bytes=size))
        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_files([r for r, _, _ in saved] + [t for _, t, _ in saved])
        return _err('ذخیره نشد.', 500)
    return jsonify({'success': True})
