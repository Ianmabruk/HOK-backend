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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email,
                'role': self.role, 'created_at': self.created_at.isoformat()}


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
    product = db.relationship('Product')

    def to_dict(self):
        return {'id': self.id, 'product_id': self.product_id,
                'quantity': self.quantity,
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
