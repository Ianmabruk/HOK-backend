from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='customer')
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    last_login_ip = db.Column(db.String(45))          # max 45 chars covers IPv6
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'email_verified': self.email_verified,
            'created_at': self.created_at.isoformat(),
        }


class EmailToken(db.Model):
    """Stores single-use tokens for email verification and password reset."""
    __tablename__ = 'email_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    # 'verify_email' | 'password_reset'
    token_type = db.Column(db.String(30), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('email_tokens', lazy=True, passive_deletes=True))


class EmailDeliveryLog(db.Model):
    __tablename__ = 'email_delivery_logs'
    __table_args__ = (
        db.Index('ix_email_delivery_logs_created_at', 'created_at'),
        db.Index('ix_email_delivery_logs_status', 'status'),
        db.Index('ix_email_delivery_logs_recipient_email', 'recipient_email'),
    )

    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    triggered_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    recipient_name = db.Column(db.String(120), nullable=True)
    recipient_email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    message_preview = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='queued', nullable=False)
    provider = db.Column(db.String(40), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)

    recipient_user = db.relationship('User', foreign_keys=[recipient_user_id])
    triggered_by_user = db.relationship('User', foreign_keys=[triggered_by_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'recipient_user_id': self.recipient_user_id,
            'triggered_by_user_id': self.triggered_by_user_id,
            'recipient_name': self.recipient_name,
            'recipient_email': self.recipient_email,
            'subject': self.subject,
            'message_preview': self.message_preview,
            'status': self.status,
            'provider': self.provider,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }


class Vendor(db.Model):
    __tablename__ = 'vendors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact = db.Column(db.String(50))
    email = db.Column(db.String(255))
    address = db.Column(db.Text)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'contact': self.contact,
                'email': self.email, 'address': self.address}


class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        db.Index('ix_products_category', 'category'),
        db.Index('ix_products_created_at', 'created_at'),
        db.Index('ix_products_price', 'price'),
    )
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    cost_price = db.Column(db.Numeric(10, 2), nullable=True)
    video_url = db.Column(db.Text)
    image_url = db.Column(db.Text)
    stock = db.Column(db.Integer, default=0)
    category = db.Column(db.String(80))
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'price': float(self.price), 'video_url': self.video_url,
            'cost_price': float(self.cost_price) if self.cost_price is not None else None,
            'image_url': self.image_url, 'stock': self.stock,
            'category': self.category, 'vendor_id': self.vendor_id,
            'created_at': self.created_at.isoformat()
        }


class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = (
        db.Index('ix_orders_user_id', 'user_id'),
        db.Index('ix_orders_status', 'status'),
        db.Index('ix_orders_created_at', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), default='pending')
    shipping_info = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)
    user = db.relationship('User', backref='orders')

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'user': self.user.to_dict() if self.user else None,
            'total_price': float(self.total_price), 'status': self.status,
            'shipping_info': self.shipping_info,
            'created_at': self.created_at.isoformat(),
            'items': [i.to_dict() for i in self.items]
        }


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=True)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=True)
    product_title = db.Column(db.String(255), nullable=True)
    product_image = db.Column(db.Text, nullable=True)
    customizations = db.Column(db.JSON, nullable=True)
    product = db.relationship('Product')

    def to_dict(self):
        return {'id': self.id, 'product_id': self.product_id,
                'quantity': self.quantity,
                'unit_price': float(self.unit_price) if self.unit_price is not None else None,
                'unit_cost': float(self.unit_cost) if self.unit_cost is not None else None,
                'product_title': self.product_title,
                'product_image': self.product_image,
                'customizations': self.customizations,
                'product': self.product.to_dict() if self.product else None}


class Chat(db.Model):
    __tablename__ = 'chats'
    __table_args__ = (
        db.Index('ix_chats_user_id', 'user_id'),
        db.Index('ix_chats_timestamp', 'timestamp'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sender = db.Column(db.String(80))
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # Product inquiry context
    product_id = db.Column(db.Integer, nullable=True)
    product_title = db.Column(db.String(200), nullable=True)
    product_price = db.Column(db.Float, nullable=True)
    product_image = db.Column(db.String(500), nullable=True)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id, 'sender': self.sender,
            'text': self.text, 'timestamp': self.timestamp.isoformat(),
            'product_id': self.product_id, 'product_title': self.product_title,
            'product_price': self.product_price, 'product_image': self.product_image,
        }


class PortfolioProject(db.Model):
    __tablename__ = 'portfolio_projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(400))
    description = db.Column(db.Text)
    image_url = db.Column(db.Text)
    room_type = db.Column(db.String(80))
    style = db.Column(db.String(80))
    year = db.Column(db.String(10))
    location = db.Column(db.String(120))
    sort_order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'summary': self.summary,
            'description': self.description,
            'image_url': self.image_url,
            'room_type': self.room_type,
            'style': self.style,
            'year': self.year,
            'location': self.location,
            'sort_order': self.sort_order,
            'is_published': self.is_published,
            'created_at': self.created_at.isoformat(),
        }


class BeforeAfterProject(db.Model):
    __tablename__ = 'before_after_projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    room_type = db.Column(db.String(80))
    style = db.Column(db.String(80))
    before_video_url = db.Column(db.Text)
    after_video_url = db.Column(db.Text)
    before_poster_url = db.Column(db.Text)
    after_poster_url = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'room_type': self.room_type,
            'style': self.style,
            'before_video_url': self.before_video_url,
            'after_video_url': self.after_video_url,
            'before_poster_url': self.before_poster_url,
            'after_poster_url': self.after_poster_url,
            'sort_order': self.sort_order,
            'is_published': self.is_published,
            'created_at': self.created_at.isoformat(),
        }


class SiteSetting(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.JSON, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class WishlistItem(db.Model):
    __tablename__ = 'wishlist_items'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_wishlist_user_product'),
        db.Index('ix_wishlist_items_user_id', 'user_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product')

    def to_dict(self):
        return {'product_id': self.product_id}


class VirtualConsultation(db.Model):
    __tablename__ = 'virtual_consultations'
    __table_args__ = (
        db.Index('ix_virtual_consultations_user_id', 'user_id'),
        db.Index('ix_virtual_consultations_status', 'status'),
        db.Index('ix_virtual_consultations_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    client_name = db.Column(db.String(120), nullable=False)
    client_email = db.Column(db.String(255), nullable=False)
    client_phone = db.Column(db.String(60), nullable=True)
    service_type = db.Column(db.String(120), nullable=False)
    design_category = db.Column(db.String(120), nullable=True)
    style_preferences = db.Column(db.Text, nullable=True)
    preferred_color_theme = db.Column(db.String(120), nullable=True)
    room_dimensions = db.Column(db.String(255), nullable=True)
    project_summary = db.Column(db.Text, nullable=True)
    preferred_meeting_date = db.Column(db.String(40), nullable=True)
    preferred_meeting_time = db.Column(db.String(40), nullable=True)
    status = db.Column(db.String(40), default='pending', nullable=False)
    progress_percent = db.Column(db.Integer, default=0, nullable=False)
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'client_name': self.client_name,
            'client_email': self.client_email,
            'client_phone': self.client_phone,
            'service_type': self.service_type,
            'design_category': self.design_category,
            'style_preferences': self.style_preferences,
            'preferred_color_theme': self.preferred_color_theme,
            'room_dimensions': self.room_dimensions,
            'project_summary': self.project_summary,
            'preferred_meeting_date': self.preferred_meeting_date,
            'preferred_meeting_time': self.preferred_meeting_time,
            'status': self.status,
            'progress_percent': self.progress_percent,
            'admin_notes': self.admin_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ClientRoomUpload(db.Model):
    __tablename__ = 'client_room_uploads'
    __table_args__ = (
        db.Index('ix_client_room_uploads_consultation_id', 'consultation_id'),
        db.Index('ix_client_room_uploads_user_id', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('virtual_consultations.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    file_url = db.Column(db.Text, nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    file_label = db.Column(db.String(120), nullable=True)
    provider = db.Column(db.String(40), nullable=True)
    file_size_kb = db.Column(db.Integer, nullable=True)
    is_floor_plan = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    consultation = db.relationship('VirtualConsultation', backref=db.backref('uploads', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'consultation_id': self.consultation_id,
            'user_id': self.user_id,
            'file_url': self.file_url,
            'file_type': self.file_type,
            'file_label': self.file_label,
            'provider': self.provider,
            'file_size_kb': self.file_size_kb,
            'is_floor_plan': self.is_floor_plan,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class VirtualProject(db.Model):
    __tablename__ = 'virtual_projects'
    __table_args__ = (
        db.Index('ix_virtual_projects_consultation_id', 'consultation_id'),
        db.Index('ix_virtual_projects_status', 'status'),
        db.Index('ix_virtual_projects_archived', 'is_archived'),
    )

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('virtual_consultations.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    design_style = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(40), default='planning', nullable=False)
    progress_percent = db.Column(db.Integer, default=0, nullable=False)
    milestones = db.Column(db.JSON, nullable=True)
    assigned_designer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    consultation = db.relationship('VirtualConsultation', backref=db.backref('projects', lazy=True))
    assigned_designer = db.relationship('User', foreign_keys=[assigned_designer_id])

    def to_dict(self):
        return {
            'id': self.id,
            'consultation_id': self.consultation_id,
            'title': self.title,
            'description': self.description,
            'design_style': self.design_style,
            'status': self.status,
            'progress_percent': self.progress_percent,
            'milestones': self.milestones or [],
            'assigned_designer_id': self.assigned_designer_id,
            'is_archived': self.is_archived,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ProjectProgress(db.Model):
    __tablename__ = 'project_progress'
    __table_args__ = (
        db.Index('ix_project_progress_project_id', 'project_id'),
        db.Index('ix_project_progress_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('virtual_projects.id', ondelete='CASCADE'), nullable=False)
    milestone = db.Column(db.String(180), nullable=False)
    progress_percent = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(40), default='in_progress', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    project = db.relationship('VirtualProject', backref=db.backref('progress_updates', lazy=True, cascade='all, delete-orphan'))
    updated_by_user = db.relationship('User', foreign_keys=[updated_by_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'milestone': self.milestone,
            'progress_percent': self.progress_percent,
            'status': self.status,
            'notes': self.notes,
            'updated_by_user_id': self.updated_by_user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AppointmentBooking(db.Model):
    __tablename__ = 'appointment_bookings'
    __table_args__ = (
        db.Index('ix_appointment_bookings_consultation_id', 'consultation_id'),
        db.Index('ix_appointment_bookings_user_id', 'user_id'),
        db.Index('ix_appointment_bookings_start_at', 'start_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('virtual_consultations.id', ondelete='SET NULL'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('virtual_projects.id', ondelete='SET NULL'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    designer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    meeting_link = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), default='scheduled', nullable=False)
    reminder_sent = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    consultation = db.relationship('VirtualConsultation', backref=db.backref('bookings', lazy=True))
    project = db.relationship('VirtualProject', backref=db.backref('bookings', lazy=True))
    user = db.relationship('User', foreign_keys=[user_id])
    designer = db.relationship('User', foreign_keys=[designer_id])

    def to_dict(self):
        return {
            'id': self.id,
            'consultation_id': self.consultation_id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'designer_id': self.designer_id,
            'start_at': self.start_at.isoformat() if self.start_at else None,
            'end_at': self.end_at.isoformat() if self.end_at else None,
            'meeting_link': self.meeting_link,
            'status': self.status,
            'reminder_sent': self.reminder_sent,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class DesignerAssignment(db.Model):
    __tablename__ = 'designer_assignments'
    __table_args__ = (
        db.Index('ix_designer_assignments_project_id', 'project_id'),
        db.Index('ix_designer_assignments_designer_id', 'designer_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('virtual_projects.id', ondelete='CASCADE'), nullable=False)
    designer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    project = db.relationship('VirtualProject', backref=db.backref('designer_assignments', lazy=True, cascade='all, delete-orphan'))
    designer = db.relationship('User', foreign_keys=[designer_id])
    assigned_by_user = db.relationship('User', foreign_keys=[assigned_by_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'designer_id': self.designer_id,
            'assigned_by_user_id': self.assigned_by_user_id,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class InspirationGallery(db.Model):
    __tablename__ = 'inspiration_galleries'
    __table_args__ = (
        db.Index('ix_inspiration_galleries_category', 'category'),
        db.Index('ix_inspiration_galleries_published', 'is_published'),
        db.Index('ix_inspiration_galleries_sort_order', 'sort_order'),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(120), nullable=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'image_url': self.image_url,
            'category': self.category,
            'sort_order': self.sort_order,
            'is_published': self.is_published,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class VirtualDesignPreview(db.Model):
    __tablename__ = 'virtual_design_previews'
    __table_args__ = (
        db.Index('ix_virtual_design_previews_project_id', 'project_id'),
        db.Index('ix_virtual_design_previews_consultation_id', 'consultation_id'),
        db.Index('ix_virtual_design_previews_published', 'is_published'),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('virtual_projects.id', ondelete='SET NULL'), nullable=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('virtual_consultations.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    before_image_url = db.Column(db.Text, nullable=True)
    after_image_url = db.Column(db.Text, nullable=True)
    mockup_image_url = db.Column(db.Text, nullable=True)
    layout_data = db.Column(db.JSON, nullable=True)
    style_variant = db.Column(db.String(120), nullable=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = db.relationship('VirtualProject', backref=db.backref('design_previews', lazy=True))
    consultation = db.relationship('VirtualConsultation', backref=db.backref('design_previews', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'consultation_id': self.consultation_id,
            'title': self.title,
            'before_image_url': self.before_image_url,
            'after_image_url': self.after_image_url,
            'mockup_image_url': self.mockup_image_url,
            'layout_data': self.layout_data or {},
            'style_variant': self.style_variant,
            'is_published': self.is_published,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
