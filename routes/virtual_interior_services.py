from datetime import datetime, timedelta
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from auth_utils import current_user_id, current_user_role
from models.models import (
    AppointmentBooking,
    ClientRoomUpload,
    DesignerAssignment,
    InspirationGallery,
    ProjectProgress,
    VirtualConsultation,
    VirtualDesignPreview,
    VirtualProject,
    db,
)

virtual_interior_services_bp = Blueprint('virtual_interior_services', __name__)


CONSULTATION_STATUSES = {'pending', 'approved', 'in_progress', 'completed', 'rejected'}
BOOKING_STATUSES = {'scheduled', 'confirmed', 'completed', 'cancelled'}
PROJECT_STATUSES = {'planning', 'concept', 'review', 'finalizing', 'published', 'completed', 'archived'}


def _admin_required_response():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


def _safe_text(value, max_len=2000):
    text = (value or '').strip()
    if not text:
        return ''
    return text[:max_len]


def _safe_int(value, default=0, min_value=None, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None:
        parsed = max(min_value, parsed)
    if max_value is not None:
        parsed = min(max_value, parsed)
    return parsed


def _safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _safe_json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = __import__('json').loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _generate_slug(title):
    """Generate a URL-safe slug from a title."""
    if not title:
        return f"project-{uuid.uuid4().hex[:8]}"
    slug = str(title).strip().lower()
    slug = ''.join(c if c.isalnum() or c in '-_' else '-' for c in slug)
    slug = '-'.join(part for part in slug.split('-') if part).strip('-')
    return slug[:160] if slug else f"project-{uuid.uuid4().hex[:8]}"


def _pagination(default_limit=12, max_limit=100):
    page = _safe_int(request.args.get('page', 1), default=1, min_value=1)
    limit = _safe_int(request.args.get('limit', default_limit), default=default_limit, min_value=1, max_value=max_limit)
    return page, limit


def _paginated_response(query, serializer, page, limit):
    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()
    return jsonify({
        'items': [serializer(item) for item in items],
        'total': total,
        'page': page,
        'limit': limit,
    })


def _parse_datetime(date_str, time_str):
    date_clean = _safe_text(date_str, max_len=20)
    time_clean = _safe_text(time_str, max_len=20)
    if not date_clean or not time_clean:
        return None

    try:
        return datetime.strptime(f'{date_clean} {time_clean}', '%Y-%m-%d %H:%M')
    except ValueError:
        return None


@virtual_interior_services_bp.get('/virtual-interior/overview')
def public_virtual_interior_overview():
    featured_previews = VirtualDesignPreview.query.filter_by(is_published=True).order_by(VirtualDesignPreview.created_at.desc()).limit(8).all()
    galleries = InspirationGallery.query.filter_by(is_published=True).order_by(InspirationGallery.sort_order.asc(), InspirationGallery.id.desc()).limit(10).all()

    return jsonify({
        'service_sections': [
            'Virtual Room Design',
            'Online Consultation',
            '3D Room Visualization',
            'Space Planning',
            'Furniture Placement Planning',
            'Color Scheme Consultation',
            'Lighting Design Assistance',
            'Renovation Visualization',
            'Home Office Design',
            'Commercial Interior Planning',
        ],
        'featured_previews': [item.to_dict() for item in featured_previews],
        'inspiration_gallery': [item.to_dict() for item in galleries],
    }), 200


@virtual_interior_services_bp.get('/virtual-interior/inspiration')
def public_virtual_inspiration():
    category = _safe_text(request.args.get('category'), max_len=120)
    page, limit = _pagination(default_limit=12)

    query = InspirationGallery.query.filter_by(is_published=True)
    if category:
        query = query.filter(InspirationGallery.category.ilike(category))

    query = query.order_by(InspirationGallery.sort_order.asc(), InspirationGallery.id.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.get('/projects/stats')
def public_projects_stats():
    """Get project statistics for dashboard."""
    try:
        total = VirtualProject.query.filter(
            VirtualProject.is_published.isnot(False),
            VirtualProject.is_archived.isnot(True),
        ).count()
        return jsonify({ 'total': total })
    except Exception:
        return jsonify({ 'total': 0 })


@virtual_interior_services_bp.get('/projects')
def public_projects():
    """Public endpoint for homepage hero videos - returns VirtualProject data."""
    page, limit = _pagination(default_limit=20, max_limit=100)
    query = VirtualProject.query.filter(
        VirtualProject.is_published.isnot(False),
        VirtualProject.is_archived.isnot(True),
    )
    query = query.order_by(VirtualProject.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.get('/virtual-interior/projects')
def public_virtual_projects():
    page, limit = _pagination(default_limit=20, max_limit=100)
    query = VirtualProject.query.filter(
        VirtualProject.is_published.isnot(False),
        VirtualProject.is_archived.isnot(True),
    )
    query = query.order_by(VirtualProject.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.get('/virtual-interior/previews')
def public_virtual_previews():
    page, limit = _pagination(default_limit=12)
    style = _safe_text(request.args.get('style_variant'), max_len=120)

    query = VirtualDesignPreview.query.filter_by(is_published=True)
    if style:
        query = query.filter(VirtualDesignPreview.style_variant.ilike(style))

    query = query.order_by(VirtualDesignPreview.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.post('/virtual-interior/consultations')
def create_virtual_consultation():
    data = request.get_json(silent=True) or {}

    client_name = _safe_text(data.get('client_name'), max_len=120)
    client_email = _safe_text(data.get('client_email'), max_len=255).lower()
    service_type = _safe_text(data.get('service_type'), max_len=120)

    if not client_name or not client_email or not service_type:
        return jsonify({'message': 'client_name, client_email, and service_type are required'}), 400

    consultation = VirtualConsultation(
        user_id=None,
        client_name=client_name,
        client_email=client_email,
        client_phone=_safe_text(data.get('client_phone'), max_len=60) or None,
        service_type=service_type,
        design_category=_safe_text(data.get('design_category'), max_len=120) or None,
        style_preferences=_safe_text(data.get('style_preferences'), max_len=2000) or None,
        preferred_color_theme=_safe_text(data.get('preferred_color_theme'), max_len=120) or None,
        room_dimensions=_safe_text(data.get('room_dimensions'), max_len=255) or None,
        project_summary=_safe_text(data.get('project_summary'), max_len=4000) or None,
        preferred_meeting_date=_safe_text(data.get('preferred_meeting_date'), max_len=40) or None,
        preferred_meeting_time=_safe_text(data.get('preferred_meeting_time'), max_len=40) or None,
        status='pending',
        progress_percent=0,
    )
    db.session.add(consultation)
    db.session.commit()

    return jsonify(consultation.to_dict()), 201


@virtual_interior_services_bp.post('/virtual-interior/consultations/<int:consultation_id>/uploads')
def upload_virtual_consultation_media(consultation_id):
    consultation = db.session.get(VirtualConsultation, consultation_id)
    if not consultation:
        return jsonify({'message': 'Consultation not found'}), 404

    data = request.get_json(silent=True) or {}

    media_kind = _safe_text(data.get('type', 'image'), max_len=20).lower()
    if media_kind not in {'image', 'video'}:
        return jsonify({'message': 'Invalid media type'}), 400

    file_path = _safe_text(data.get('file_path'), max_len=1000)
    if not file_path:
        return jsonify({'message': 'file_path is required'}), 400

    record = ClientRoomUpload(
        consultation_id=consultation_id,
        user_id=None,
        file_url=file_path,
        file_type=media_kind,
        file_label=_safe_text(data.get('file_label'), max_len=120) or None,
        provider='supabase-storage',
        file_size_kb=_safe_int(data.get('file_size_kb'), default=0, min_value=0) or None,
        is_floor_plan=_safe_bool(data.get('is_floor_plan'), default=False),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify(record.to_dict()), 201


@virtual_interior_services_bp.post('/virtual-interior/bookings')
def create_virtual_booking():
    data = request.get_json(silent=True) or {}

    consultation_id = _safe_int(data.get('consultation_id'), default=0, min_value=0)
    if consultation_id <= 0:
        return jsonify({'message': 'consultation_id is required'}), 400

    consultation = db.session.get(VirtualConsultation, consultation_id)
    if not consultation:
        return jsonify({'message': 'Consultation not found'}), 404

    start_at = _parse_datetime(data.get('date'), data.get('time'))
    if not start_at:
        return jsonify({'message': 'A valid date and time are required (YYYY-MM-DD and HH:MM)'}), 400

    duration_minutes = _safe_int(data.get('duration_minutes'), default=60, min_value=30, max_value=180)
    end_at = start_at + timedelta(minutes=duration_minutes)

    booking = AppointmentBooking(
        consultation_id=consultation_id,
        project_id=None,
        user_id=None,
        designer_id=None,
        start_at=start_at,
        end_at=end_at,
        status='scheduled',
        meeting_link=_safe_text(data.get('meeting_link'), max_len=500) or None,
        notes=_safe_text(data.get('notes'), max_len=2000) or None,
    )
    db.session.add(booking)
    db.session.commit()

    return jsonify(booking.to_dict()), 201


@virtual_interior_services_bp.get('/virtual-interior/consultations/<int:consultation_id>/progress')
def get_consultation_progress(consultation_id):
    consultation = db.session.get(VirtualConsultation, consultation_id)
    if not consultation:
        return jsonify({'message': 'Consultation not found'}), 404

    email = _safe_text(request.args.get('email'), max_len=255).lower()
    if not email or email != (consultation.client_email or '').lower():
        return jsonify({'message': 'Matching consultation email is required'}), 403

    projects = [project.to_dict() for project in consultation.projects]
    bookings = [booking.to_dict() for booking in consultation.bookings]
    uploads = [upload.to_dict() for upload in consultation.uploads]

    return jsonify({
        'consultation': consultation.to_dict(),
        'projects': projects,
        'bookings': bookings,
        'uploads': uploads,
    }), 200


@virtual_interior_services_bp.get('/admin/virtual-interior/consultations')
@jwt_required()
def admin_list_virtual_consultations():
    err = _admin_required_response()
    if err:
        return err

    status = _safe_text(request.args.get('status'), max_len=40)
    search = _safe_text(request.args.get('search'), max_len=120)
    page, limit = _pagination(default_limit=10)

    query = VirtualConsultation.query
    if status:
        query = query.filter(VirtualConsultation.status == status)
    if search:
        query = query.filter(
            or_(
                VirtualConsultation.client_name.ilike(f'%{search}%'),
                VirtualConsultation.client_email.ilike(f'%{search}%'),
                VirtualConsultation.service_type.ilike(f'%{search}%'),
            )
        )

    query = query.order_by(VirtualConsultation.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.put('/admin/virtual-interior/consultations/<int:consultation_id>')
@jwt_required()
def admin_update_virtual_consultation(consultation_id):
    err = _admin_required_response()
    if err:
        return err

    consultation = db.session.get(VirtualConsultation, consultation_id)
    if not consultation:
        return jsonify({'message': 'Consultation not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'status' in data:
        status = _safe_text(data.get('status'), max_len=40)
        if status not in CONSULTATION_STATUSES:
            return jsonify({'message': 'Invalid consultation status'}), 400
        consultation.status = status

    if 'progress_percent' in data:
        consultation.progress_percent = _safe_int(data.get('progress_percent'), default=0, min_value=0, max_value=100)

    if 'admin_notes' in data:
        consultation.admin_notes = _safe_text(data.get('admin_notes'), max_len=4000) or None

    db.session.commit()
    return jsonify(consultation.to_dict()), 200


@virtual_interior_services_bp.get('/admin/virtual-interior/uploads')
@jwt_required()
def admin_list_virtual_uploads():
    err = _admin_required_response()
    if err:
        return err

    consultation_id = _safe_int(request.args.get('consultation_id'), default=0, min_value=0)
    page, limit = _pagination(default_limit=12)

    query = ClientRoomUpload.query
    if consultation_id > 0:
        query = query.filter(ClientRoomUpload.consultation_id == consultation_id)

    query = query.order_by(ClientRoomUpload.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.get('/admin/virtual-interior/projects')
@jwt_required()
def admin_list_virtual_projects():
    err = _admin_required_response()
    if err:
        return err

    status = _safe_text(request.args.get('status'), max_len=40)
    search = _safe_text(request.args.get('search'), max_len=120)
    page, limit = _pagination(default_limit=10)

    query = VirtualProject.query
    if status:
        query = query.filter(VirtualProject.status == status)
    if search:
        query = query.filter(
            or_(
                VirtualProject.title.ilike(f'%{search}%'),
                VirtualProject.description.ilike(f'%{search}%'),
            )
        )

    query = query.order_by(VirtualProject.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.post('/admin/virtual-interior/projects')
@jwt_required()
def admin_create_virtual_project():
    err = _admin_required_response()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = _safe_text(data.get('title'), max_len=200)

    if not title:
        return jsonify({'message': 'title is required'}), 400

    consultation_id = _safe_int(data.get('consultation_id'), default=0, min_value=0)
    if consultation_id and not db.session.get(VirtualConsultation, consultation_id):
        return jsonify({'message': 'Consultation not found'}), 404

    status = _safe_text(data.get('status'), max_len=40) or 'planning'
    if status not in PROJECT_STATUSES:
        return jsonify({'message': 'Invalid project status'}), 400

    project = VirtualProject(
        consultation_id=consultation_id or None,
        slug=_generate_slug(title),
        title=title,
        description=_safe_text(data.get('description'), max_len=4000) or None,
        design_style=_safe_text(data.get('design_style', data.get('category')), max_len=120) or None,
        thumbnail=_safe_text(data.get('thumbnail'), max_len=2000),
        gallery=_safe_json_list(data.get('gallery')),
        video_url=_safe_text(data.get('video_url'), max_len=2000),
        video_thumbnail=_safe_text(data.get('video_thumbnail'), max_len=2000),
        before_image_url=_safe_text(data.get('before_image_url', data.get('beforeImage')), max_len=2000),
        after_image_url=_safe_text(data.get('after_image_url', data.get('afterImage')), max_len=2000),
        designer=_safe_text(data.get('designer'), max_len=120),
        date=_safe_text(data.get('date'), max_len=20),
        featured=_safe_bool(data.get('featured'), False),
        tags=_safe_json_list(data.get('tags')),
        ai_tags=_safe_json_list(data.get('ai_tags', data.get('aiTags'))),
        views=_safe_int(data.get('views'), default=0, min_value=0),
        favorites=_safe_int(data.get('favorites'), default=0, min_value=0),
        status=status,
        progress_percent=_safe_int(data.get('progress_percent'), default=0, min_value=0, max_value=100),
        milestones=data.get('milestones') if isinstance(data.get('milestones'), list) else [],
        assigned_designer_id=_safe_uuid(data.get('assigned_designer_id')),
        is_archived=_safe_bool(data.get('is_archived'), default=False),
        is_published=_safe_bool(data.get('is_published', data.get('published')), default=status in {'published', 'completed'}),
    )
    db.session.add(project)
    db.session.commit()

    return jsonify(project.to_dict()), 201


@virtual_interior_services_bp.put('/admin/virtual-interior/projects/<int:project_id>')
@jwt_required()
def admin_update_virtual_project(project_id):
    err = _admin_required_response()
    if err:
        return err

    project = db.session.get(VirtualProject, project_id)
    if not project:
        return jsonify({'message': 'Project not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = _safe_text(data.get('title'), max_len=200)
        if not title:
            return jsonify({'message': 'title is required'}), 400
        project.title = title
        # Update slug when title changes
        if 'slug' not in data or not project.slug:
            project.slug = _generate_slug(title)

    if 'description' in data:
        project.description = _safe_text(data.get('description'), max_len=4000) or None
    if 'design_style' in data or 'category' in data:
        project.design_style = _safe_text(data.get('design_style', data.get('category')), max_len=120) or None
    if 'thumbnail' in data:
        project.thumbnail = _safe_text(data.get('thumbnail'), max_len=2000)
    if 'gallery' in data:
        project.gallery = _safe_json_list(data.get('gallery'))
    if 'video_url' in data:
        project.video_url = _safe_text(data.get('video_url'), max_len=2000)
    if 'video_thumbnail' in data:
        project.video_thumbnail = _safe_text(data.get('video_thumbnail'), max_len=2000)
    if 'before_image_url' in data or 'beforeImage' in data:
        project.before_image_url = _safe_text(data.get('before_image_url', data.get('beforeImage')), max_len=2000)
    if 'after_image_url' in data or 'afterImage' in data:
        project.after_image_url = _safe_text(data.get('after_image_url', data.get('afterImage')), max_len=2000)
    if 'designer' in data:
        project.designer = _safe_text(data.get('designer'), max_len=120) or None
    if 'date' in data:
        project.date = _safe_text(data.get('date'), max_len=20) or None
    if 'featured' in data:
        project.featured = _safe_bool(data.get('featured'), False)
    if 'tags' in data:
        project.tags = _safe_json_list(data.get('tags'))
    if 'ai_tags' in data or 'aiTags' in data:
        project.ai_tags = _safe_json_list(data.get('ai_tags', data.get('aiTags')))
    if 'views' in data:
        project.views = _safe_int(data.get('views'), default=project.views, min_value=0)
    if 'favorites' in data:
        project.favorites = _safe_int(data.get('favorites'), default=project.favorites, min_value=0)

    if 'status' in data:
        status = _safe_text(data.get('status'), max_len=40)
        if status not in PROJECT_STATUSES:
            return jsonify({'message': 'Invalid project status'}), 400
        project.status = status

    if 'progress_percent' in data:
        project.progress_percent = _safe_int(data.get('progress_percent'), default=0, min_value=0, max_value=100)
    if 'is_published' in data or 'published' in data:
        project.is_published = _safe_bool(data.get('is_published', data.get('published')), default=project.is_published)
    if 'is_archived' in data:
        project.is_archived = _safe_bool(data.get('is_archived'), default=project.is_archived)

    db.session.commit()
    return jsonify(project.to_dict()), 200


@virtual_interior_services_bp.delete('/admin/virtual-interior/projects/<int:project_id>')
@jwt_required()
def admin_delete_virtual_project(project_id):
    err = _admin_required_response()
    if err:
        return err

    project = db.session.get(VirtualProject, project_id)
    if not project:
        return jsonify({'message': 'Project not found'}), 404

    db.session.delete(project)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200


@virtual_interior_services_bp.post('/admin/virtual-interior/projects/<int:project_id>/progress')
@jwt_required()
def admin_add_virtual_project_progress(project_id):
    err = _admin_required_response()
    if err:
        return err

    project = db.session.get(VirtualProject, project_id)
    if not project:
        return jsonify({'message': 'Project not found'}), 404

    data = request.get_json(silent=True) or {}
    milestone = _safe_text(data.get('milestone'), max_len=180)
    if not milestone:
        return jsonify({'message': 'milestone is required'}), 400

    status = _safe_text(data.get('status'), max_len=40) or 'in_progress'
    progress = _safe_int(data.get('progress_percent'), default=project.progress_percent, min_value=0, max_value=100)

    update = ProjectProgress(
        project_id=project_id,
        milestone=milestone,
        progress_percent=progress,
        status=status,
        notes=_safe_text(data.get('notes'), max_len=3000) or None,
        updated_by_user_id=current_user_id(),
    )
    db.session.add(update)

    project.progress_percent = progress
    db.session.commit()

    return jsonify(update.to_dict()), 201


@virtual_interior_services_bp.post('/admin/virtual-interior/assignments')
@jwt_required()
def admin_create_designer_assignment():
    err = _admin_required_response()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    project_id = _safe_int(data.get('project_id'), default=0, min_value=0)
    designer_id = _safe_uuid(data.get('designer_id'))

    if project_id <= 0 or not db.session.get(VirtualProject, project_id):
        return jsonify({'message': 'Valid project_id is required'}), 400

    assignment = DesignerAssignment(
        project_id=project_id,
        designer_id=designer_id,
        assigned_by_user_id=current_user_id(),
        notes=_safe_text(data.get('notes'), max_len=2000) or None,
    )
    db.session.add(assignment)
    db.session.commit()

    return jsonify(assignment.to_dict()), 201


@virtual_interior_services_bp.get('/admin/virtual-interior/bookings')
@jwt_required()
def admin_list_virtual_bookings():
    err = _admin_required_response()
    if err:
        return err

    status = _safe_text(request.args.get('status'), max_len=40)
    page, limit = _pagination(default_limit=10)

    query = AppointmentBooking.query
    if status:
        query = query.filter(AppointmentBooking.status == status)

    query = query.order_by(AppointmentBooking.start_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.put('/admin/virtual-interior/bookings/<int:booking_id>')
@jwt_required()
def admin_update_virtual_booking(booking_id):
    err = _admin_required_response()
    if err:
        return err

    booking = db.session.get(AppointmentBooking, booking_id)
    if not booking:
        return jsonify({'message': 'Booking not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'status' in data:
        status = _safe_text(data.get('status'), max_len=40)
        if status not in BOOKING_STATUSES:
            return jsonify({'message': 'Invalid booking status'}), 400
        booking.status = status

    if 'designer_id' in data:
        booking.designer_id = _safe_uuid(data.get('designer_id'))
    if 'meeting_link' in data:
        booking.meeting_link = _safe_text(data.get('meeting_link'), max_len=500) or None
    if 'notes' in data:
        booking.notes = _safe_text(data.get('notes'), max_len=3000) or None
    if 'reminder_sent' in data:
        booking.reminder_sent = _safe_bool(data.get('reminder_sent'), default=False)

    db.session.commit()
    return jsonify(booking.to_dict()), 200


@virtual_interior_services_bp.get('/admin/virtual-interior/inspiration')
@jwt_required()
def admin_list_virtual_inspiration():
    err = _admin_required_response()
    if err:
        return err

    page, limit = _pagination(default_limit=12)
    query = InspirationGallery.query.order_by(InspirationGallery.sort_order.asc(), InspirationGallery.id.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.post('/admin/virtual-interior/inspiration')
@jwt_required()
def admin_create_virtual_inspiration():
    err = _admin_required_response()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = _safe_text(data.get('title'), max_len=180)
    image_url = _safe_text(data.get('image_url'), max_len=1000)

    if not title or not image_url:
        return jsonify({'message': 'title and image_url are required'}), 400

    item = InspirationGallery(
        title=title,
        description=_safe_text(data.get('description'), max_len=2000) or None,
        image_url=image_url,
        category=_safe_text(data.get('category'), max_len=120) or None,
        sort_order=_safe_int(data.get('sort_order'), default=0),
        is_published=_safe_bool(data.get('is_published'), default=True),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@virtual_interior_services_bp.put('/admin/virtual-interior/inspiration/<int:item_id>')
@jwt_required()
def admin_update_virtual_inspiration(item_id):
    err = _admin_required_response()
    if err:
        return err

    item = db.session.get(InspirationGallery, item_id)
    if not item:
        return jsonify({'message': 'Inspiration item not found'}), 404

    data = request.get_json(silent=True) or {}
    if 'title' in data:
        title = _safe_text(data.get('title'), max_len=180)
        if not title:
            return jsonify({'message': 'title cannot be empty'}), 400
        item.title = title
    if 'description' in data:
        item.description = _safe_text(data.get('description'), max_len=2000) or None
    if 'image_url' in data:
        image_url = _safe_text(data.get('image_url'), max_len=1000)
        if not image_url:
            return jsonify({'message': 'image_url cannot be empty'}), 400
        item.image_url = image_url
    if 'category' in data:
        item.category = _safe_text(data.get('category'), max_len=120) or None
    if 'sort_order' in data:
        item.sort_order = _safe_int(data.get('sort_order'), default=0)
    if 'is_published' in data:
        item.is_published = _safe_bool(data.get('is_published'), default=True)

    db.session.commit()
    return jsonify(item.to_dict()), 200


@virtual_interior_services_bp.delete('/admin/virtual-interior/inspiration/<int:item_id>')
@jwt_required()
def admin_delete_virtual_inspiration(item_id):
    err = _admin_required_response()
    if err:
        return err

    item = db.session.get(InspirationGallery, item_id)
    if not item:
        return jsonify({'message': 'Inspiration item not found'}), 404

    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200


@virtual_interior_services_bp.get('/admin/virtual-interior/previews')
@jwt_required()
def admin_list_virtual_previews():
    err = _admin_required_response()
    if err:
        return err

    page, limit = _pagination(default_limit=12)
    query = VirtualDesignPreview.query.order_by(VirtualDesignPreview.created_at.desc())
    return _paginated_response(query, lambda item: item.to_dict(), page, limit)


@virtual_interior_services_bp.post('/admin/virtual-interior/previews')
@jwt_required()
def admin_create_virtual_preview():
    err = _admin_required_response()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = _safe_text(data.get('title'), max_len=180)
    if not title:
        return jsonify({'message': 'title is required'}), 400

    preview = VirtualDesignPreview(
        project_id=_safe_int(data.get('project_id'), default=0, min_value=0) or None,
        consultation_id=_safe_int(data.get('consultation_id'), default=0, min_value=0) or None,
        title=title,
        before_image_url=_safe_text(data.get('before_image_url'), max_len=1000) or None,
        after_image_url=_safe_text(data.get('after_image_url'), max_len=1000) or None,
        mockup_image_url=_safe_text(data.get('mockup_image_url'), max_len=1000) or None,
        layout_data=data.get('layout_data') if isinstance(data.get('layout_data'), dict) else {},
        style_variant=_safe_text(data.get('style_variant'), max_len=120) or None,
        is_published=_safe_bool(data.get('is_published'), default=True),
    )
    db.session.add(preview)
    db.session.commit()

    return jsonify(preview.to_dict()), 201


@virtual_interior_services_bp.put('/admin/virtual-interior/previews/<int:preview_id>')
@jwt_required()
def admin_update_virtual_preview(preview_id):
    err = _admin_required_response()
    if err:
        return err

    preview = db.session.get(VirtualDesignPreview, preview_id)
    if not preview:
        return jsonify({'message': 'Preview not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = _safe_text(data.get('title'), max_len=180)
        if not title:
            return jsonify({'message': 'title cannot be empty'}), 400
        preview.title = title

    if 'project_id' in data:
        preview.project_id = _safe_int(data.get('project_id'), default=0, min_value=0) or None
    if 'consultation_id' in data:
        preview.consultation_id = _safe_int(data.get('consultation_id'), default=0, min_value=0) or None
    if 'before_image_url' in data:
        preview.before_image_url = _safe_text(data.get('before_image_url'), max_len=1000) or None
    if 'after_image_url' in data:
        preview.after_image_url = _safe_text(data.get('after_image_url'), max_len=1000) or None
    if 'mockup_image_url' in data:
        preview.mockup_image_url = _safe_text(data.get('mockup_image_url'), max_len=1000) or None
    if 'layout_data' in data and isinstance(data.get('layout_data'), dict):
        preview.layout_data = data.get('layout_data')
    if 'style_variant' in data:
        preview.style_variant = _safe_text(data.get('style_variant'), max_len=120) or None
    if 'is_published' in data:
        preview.is_published = _safe_bool(data.get('is_published'), default=True)

    db.session.commit()
    return jsonify(preview.to_dict()), 200


@virtual_interior_services_bp.delete('/admin/virtual-interior/previews/<int:preview_id>')
@jwt_required()
def admin_delete_virtual_preview(preview_id):
    err = _admin_required_response()
    if err:
        return err

    preview = db.session.get(VirtualDesignPreview, preview_id)
    if not preview:
        return jsonify({'message': 'Preview not found'}), 404

    db.session.delete(preview)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200


