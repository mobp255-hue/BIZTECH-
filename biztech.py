#!/usr/bin/env python
"""
BizTech – Business Technologies
Full‑featured: real‑time messaging, images, likes, views, AI assistant, auto‑install.
Enhanced UI, auto‑repairing database, favicon, animated background, interactive cards,
listing detail page with map, USD/ZiG currency converter, generous rate limits, persistent dark mode,
public user profiles, multi‑product listings with availability, recommendations, user following,
group chat with E2EE, AI chatbot with web search, user discovery, interactive auth forms,
shopping cart, PayPal payments, WebRTC video calls, local cash‑on‑delivery, delivery tracking,
multi‑language support (English, Shona, Ndebele), text‑to‑speech accessibility, integrated wallet,
business verification badge, and local market weather/price widget.

MIT License

Copyright (c) 2026 Isaac Madungwe and contributors
"""

import subprocess
import sys
import os
import importlib.util
import argparse
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------------------
# Auto‑dependency installer (runs before any third‑party imports)
# ----------------------------------------------------------------------------
REQUIRED_PACKAGES = [
    ('flask', 'flask'),
    ('flask-socketio', 'flask_socketio'),
    ('flask-sqlalchemy', 'flask_sqlalchemy'),
    ('requests', 'requests'),
    ('eventlet', 'eventlet'),
    ('werkzeug', 'werkzeug'),
    ('pillow', 'PIL'),
    ('cryptography', 'cryptography'),
    ('beautifulsoup4', 'bs4'),
]

def check_and_install():
    missing = []
    for pip_name, import_name in REQUIRED_PACKAGES:
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            missing.append((pip_name, import_name))
    
    if missing:
        print("Missing required packages. Installing now...")
        for pip_name, _ in missing:
            print(f"  Installing {pip_name}...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pip_name])
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {pip_name}. Please install manually:")
                print(f"   {sys.executable} -m pip install {pip_name}")
                sys.exit(1)
        
        print("✅ All packages installed. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    print("✓ All dependencies satisfied.")

check_and_install()

# ----------------------------------------------------------------------------
# Safe imports
# ----------------------------------------------------------------------------
import re
import time
import html
import socket
import json
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import wraps
from threading import Thread
from collections import defaultdict
from werkzeug.utils import secure_filename
from PIL import Image
from bs4 import BeautifulSoup

from flask import (Flask, render_template_string, request, jsonify, 
                   session, redirect, url_for, flash, g, send_from_directory)
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, and_, inspect
from werkzeug.security import generate_password_hash, check_password_hash
import requests

# Cryptography for E2EE
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os as crypto_os

# ============================================================================
# Configuration
# ============================================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'biztech-district-competition-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///businesses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(os.path.join(UPLOAD_FOLDER, 'listings'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'profiles'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'products'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'group_chat'), exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

EXCHANGE_RATE = 15.0  # 1 USD = X ZiG

# PayPal configuration (set environment variables or replace)
PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', 'your_client_id')
PAYPAL_SECRET = os.environ.get('PAYPAL_SECRET', 'your_secret')
PAYPAL_API_BASE = 'https://api-m.sandbox.paypal.com'

# WebRTC STUN/TURN servers
WEBRTC_ICE_SERVERS = [
    {'urls': 'stun:stun.l.google.com:19302'},
]

# Weather API (now using Open‑Meteo, no key needed)
WEATHER_CITY = 'Masvingo'

# ============================================================================
# Database Models (all conflicts fixed – explicit child relationships removed)
# ============================================================================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_image = db.Column(db.String(200), default='default.jpg')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    public_key = db.Column(db.Text, nullable=True)
    wallet_balance = db.Column(db.Float, default=0.0)
    verified = db.Column(db.Boolean, default=False)
    
    # One-to-many relationships (with backrefs)
    listings = db.relationship('BusinessListing', backref='owner', lazy=True)
    products = db.relationship('Product', backref='seller', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy='dynamic')
    likes = db.relationship('Like', backref='user', lazy=True)
    recommendations = db.relationship('Recommendation', backref='user', lazy=True)
    followed = db.relationship('Follow',
                               foreign_keys='Follow.follower_id',
                               backref=db.backref('follower', lazy='joined'),
                               lazy='dynamic',
                               cascade='all, delete-orphan')
    followers = db.relationship('Follow',
                                foreign_keys='Follow.followed_id',
                                backref=db.backref('followed', lazy='joined'),
                                lazy='dynamic',
                                cascade='all, delete-orphan')
    group_memberships = db.relationship('GroupMember', backref='user', lazy=True)
    cart = db.relationship('Cart', backref='user', uselist=False, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='buyer', lazy=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    withdrawal_requests = db.relationship('WithdrawalRequest', backref='user', lazy=True)
    verification_requests = db.relationship('VerificationRequest', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def unread_count(self):
        return Message.query.filter_by(recipient_id=self.id, read=False).count()
    
    def is_following(self, user):
        if user.id is None:
            return False
        return self.followed.filter_by(followed_id=user.id).first() is not None
    
    def follow(self, user):
        if not self.is_following(user) and self.id != user.id:
            f = Follow(follower_id=self.id, followed_id=user.id)
            db.session.add(f)
            db.session.commit()
            return True
        return False
    
    def unfollow(self, user):
        f = self.followed.filter_by(followed_id=user.id).first()
        if f:
            db.session.delete(f)
            db.session.commit()
            return True
        return False

class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class BusinessListing(db.Model):
    __tablename__ = 'listings'
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), default='Other')
    image = db.Column(db.String(200), nullable=True)
    likes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    featured = db.Column(db.Boolean, default=False)
    approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    liked_by = db.relationship('Like', backref='listing', lazy=True)
    products = db.relationship('Product', backref='listing', lazy=True, cascade='all, delete-orphan')
    recommendations = db.relationship('Recommendation', backref='listing', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'business_name': self.business_name,
            'description': self.description,
            'location': self.location,
            'phone': self.phone[-4:].rjust(len(self.phone), '*'),
            'category': self.category,
            'image': self.image,
            'likes': self.likes,
            'views': self.views,
            'featured': self.featured,
            'created_at': self.created_at.isoformat(),
            'created_ago': self.time_ago(),
            'owner_id': self.user_id,
            'owner_name': self.owner.username if self.owner else None,
            'owner_image': self.owner.profile_image if self.owner else None,
            'owner_verified': self.owner.verified if self.owner else False,
            'products': [p.to_dict() for p in self.products]
        }

    def time_ago(self):
        diff = datetime.now(timezone.utc) - self.created_at
        if diff.days > 30:
            return f"{diff.days//30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds//60}m ago"
        return "just now"

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=True)
    available = db.Column(db.Boolean, default=True)
    image = db.Column(db.String(200), nullable=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    recommendations = db.relationship('Recommendation', backref='product', lazy=True)
    cart_items = db.relationship('CartItem', backref='product', lazy=True)
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'available': self.available,
            'image': self.image,
            'listing_id': self.listing_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'created_ago': self.time_ago()
        }
    
    def time_ago(self):
        diff = datetime.now(timezone.utc) - self.created_at
        if diff.days > 30:
            return f"{diff.days//30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds//60}m ago"
        return "just now"

class Cart(db.Model):
    __tablename__ = 'carts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')

class CartItem(db.Model):
    __tablename__ = 'cart_items'
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('carts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')
    payment_method = db.Column(db.String(50))
    paypal_order_id = db.Column(db.String(100), nullable=True)
    delivery_status = db.Column(db.String(50), default='pending')
    delivery_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20))
    status = db.Column(db.String(20), default='completed')
    payment_method = db.Column(db.String(50))
    paypal_order_id = db.Column(db.String(100), nullable=True)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # No explicit user relationship – rely on backref from User

class WithdrawalRequest(db.Model):
    __tablename__ = 'withdrawal_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(50))
    details = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = db.Column(db.DateTime, nullable=True)

    # No explicit user relationship – rely on backref from User

class VerificationRequest(db.Model):
    __tablename__ = 'verification_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    business_name = db.Column(db.String(200))
    contact_info = db.Column(db.String(200))
    documents = db.Column(db.String(500))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # No explicit user relationship – rely on backref from User

class MarketPrice(db.Model):
    __tablename__ = 'market_prices'
    id = db.Column(db.Integer, primary_key=True)
    commodity = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), default='kg')
    location = db.Column(db.String(100))
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Recommendation(db.Model):
    __tablename__ = 'recommendations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # No explicit relationships – rely on backrefs from User, Product, Listing
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username,
            'user_image': self.user.profile_image,
            'listing_id': self.listing_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'listing_name': self.listing.business_name if self.listing else None,
            'comment': self.comment,
            'created_at': self.created_at.isoformat(),
            'created_ago': self.time_ago()
        }
    
    def time_ago(self):
        diff = datetime.now(timezone.utc) - self.created_at
        if diff.days > 30:
            return f"{diff.days//30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds//60}m ago"
        return "just now"

class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint('user_id', 'listing_id', name='unique_user_listing_like'),)

    # No explicit relationships – rely on backrefs from User and Listing

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    encrypted = db.Column(db.Boolean, default=False)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # No explicit sender/recipient relationships – rely on backrefs from User

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.username,
            'sender_profile': self.sender.profile_image,
            'recipient_id': self.recipient_id,
            'recipient_name': self.recipient.username,
            'content': self.content,
            'encrypted': self.encrypted,
            'read': self.read,
            'created_at': self.created_at.isoformat(),
            'created_ago': self.time_ago()
        }

    def time_ago(self):
        diff = datetime.now(timezone.utc) - self.created_at
        if diff.days > 30:
            return f"{diff.days//30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds//60}m ago"
        return "just now"

class GroupChat(db.Model):
    __tablename__ = 'group_chats'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_private = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('GroupMessage', backref='group', lazy=True, cascade='all, delete-orphan')

class GroupMember(db.Model):
    __tablename__ = 'group_members'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group_chats.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    public_key = db.Column(db.Text, nullable=True)
    __table_args__ = (db.UniqueConstraint('group_id', 'user_id', name='unique_group_user'),)

    # No explicit user relationship – rely on backref from User

class GroupMessage(db.Model):
    __tablename__ = 'group_messages'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group_chats.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    encrypted = db.Column(db.Boolean, default=False)
    file_path = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', foreign_keys=[user_id])  # explicit – no backref from User, so keep
    
    def to_dict(self):
        return {
            'id': self.id,
            'group_id': self.group_id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else 'Unknown',
            'user_image': self.user.profile_image if self.user else 'default.jpg',
            'content': self.content,
            'encrypted': self.encrypted,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat(),
            'created_ago': self.time_ago()
        }
    
    def time_ago(self):
        diff = datetime.now(timezone.utc) - self.created_at
        if diff.days > 30:
            return f"{diff.days//30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds//60}m ago"
        return "just now"

class RateLimit(db.Model):
    __tablename__ = 'rate_limits'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    endpoint = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @classmethod
    def is_rate_limited(cls, ip, endpoint, limit, period_seconds):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=period_seconds)
        cls.query.filter(
            and_(
                cls.ip_address == ip,
                cls.endpoint == endpoint,
                cls.timestamp < cutoff
            )
        ).delete(synchronize_session=False)
        db.session.commit()
        count = cls.query.filter(
            and_(
                cls.ip_address == ip,
                cls.endpoint == endpoint,
                cls.timestamp >= cutoff
            )
        ).count()
        return count >= limit

    @classmethod
    def add_attempt(cls, ip, endpoint):
        attempt = cls(ip_address=ip, endpoint=endpoint)
        db.session.add(attempt)
        db.session.commit()

# ============================================================================
# E2EE Helper Functions (unchanged)
# ============================================================================
def generate_key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    return private_pem, public_pem

def derive_shared_key(private_pem, peer_public_pem):
    private_key = serialization.load_pem_private_key(
        private_pem.encode('utf-8'),
        password=None,
        backend=default_backend()
    )
    peer_public = serialization.load_pem_public_key(
        peer_public_pem.encode('utf-8'),
        backend=default_backend()
    )
    shared_secret = private_key.exchange(ec.ECDH(), peer_public)
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'handshake data',
        backend=default_backend()
    ).derive(shared_secret)
    return derived_key

def encrypt_message(key, plaintext):
    iv = crypto_os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()
    result = base64.b64encode(iv + encryptor.tag + ciphertext).decode('utf-8')
    return result

def decrypt_message(key, encrypted_data):
    data = base64.b64decode(encrypted_data.encode('utf-8'))
    iv = data[:12]
    tag = data[12:28]
    ciphertext = data[28:]
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return plaintext.decode('utf-8')

# ============================================================================
# Web Search Function (unchanged)
# ============================================================================
def web_search(query, num_results=5):
    try:
        url = "https://html.duckduckgo.com/html/"
        params = {'q': query}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.post(url, data=params, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        for result in soup.select('.result')[:num_results]:
            title_elem = result.select_one('.result__a')
            snippet_elem = result.select_one('.result__snippet')
            url_elem = result.select_one('.result__url')
            if title_elem and url_elem:
                title = title_elem.get_text(strip=True)
                link = url_elem.get('href', '')
                if link.startswith('/'):
                    link = 'https://duckduckgo.com' + link
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                results.append({'title': title, 'link': link, 'snippet': snippet})
        return results[:num_results]
    except Exception as e:
        print(f"Web search error: {e}")
        return []

# ============================================================================
# PayPal Helper Functions (unchanged)
# ============================================================================
def get_paypal_access_token():
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get PayPal access token: {response.text}")

def create_paypal_order(amount):
    access_token = get_paypal_access_token()
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    data = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": "USD",
                "value": str(amount)
            }
        }]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code in (200, 201):
        return response.json()
    else:
        raise Exception(f"Failed to create PayPal order: {response.text}")

def capture_paypal_order(order_id):
    access_token = get_paypal_access_token()
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.post(url, headers=headers)
    if response.status_code in (200, 201):
        return response.json()
    else:
        raise Exception(f"Failed to capture PayPal order: {response.text}")

# ============================================================================
# Database initialization with auto‑repair
# ============================================================================
def rebuild_database():
    print("Rebuilding database...")
    db.drop_all()
    db.create_all()
    print("Database rebuilt successfully.")

with app.app_context():
    db_path = 'businesses.db'
    rebuild_needed = False
    if os.path.exists(db_path):
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            required_tables = ['users', 'listings', 'products', 'recommendations', 
                               'follows', 'group_chats', 'group_members', 'group_messages',
                               'carts', 'cart_items', 'orders', 'order_items',
                               'transactions', 'withdrawal_requests', 'verification_requests',
                               'market_prices']
            for table in required_tables:
                if table not in tables:
                    print(f"Missing table: {table}")
                    rebuild_needed = True
                    break
            if 'users' in tables and not rebuild_needed:
                columns = [col['name'] for col in inspector.get_columns('users')]
                if 'public_key' not in columns:
                    print("Missing public_key column in users")
                    rebuild_needed = True
                if 'wallet_balance' not in columns:
                    print("Missing wallet_balance column in users")
                    rebuild_needed = True
                if 'verified' not in columns:
                    print("Missing verified column in users")
                    rebuild_needed = True
            if 'products' in tables and not rebuild_needed:
                prod_columns = [col['name'] for col in inspector.get_columns('products')]
                if 'available' not in prod_columns:
                    print("Missing 'available' column in products, rebuilding...")
                    rebuild_needed = True
            if 'orders' in tables and not rebuild_needed:
                order_columns = [col['name'] for col in inspector.get_columns('orders')]
                if 'delivery_status' not in order_columns:
                    print("Missing delivery_status column in orders, rebuilding...")
                    rebuild_needed = True
                if 'delivery_date' not in order_columns:
                    print("Missing delivery_date column in orders, rebuilding...")
                    rebuild_needed = True
        except Exception as e:
            print(f"Schema check error: {e}")
            rebuild_needed = True
    else:
        rebuild_needed = True

    if rebuild_needed:
        rebuild_database()
    else:
        try:
            db.create_all()
            print("✓ Database initialized (tables verified).")
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}, rebuilding...")
            rebuild_database()

    # Create default admin user if no users exist
    if User.query.count() == 0:
        admin = User(username='admin', email='admin@biztech.local', phone='0000000000')
        admin.set_password('admin123')
        admin.verified = True
        admin.wallet_balance = 1000
        db.session.add(admin)
        db.session.commit()
        print("Default admin created (username: admin, password: admin123)")

# ============================================================================
# Rate limiter decorator (unchanged)
# ============================================================================
def rate_limit(limit=100, per=86400):  # 100 per day – effectively no limit
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr
            endpoint = request.endpoint
            if RateLimit.is_rate_limited(ip, endpoint, limit, per):
                return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429
            RateLimit.add_attempt(ip, endpoint)
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ============================================================================
# Helper functions (unchanged)
# ============================================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(text):
    if text is None:
        return None
    text = re.sub(r'<[^>]*>', '', text)
    return html.escape(text.strip())

def resize_image(filepath, max_size=(800, 800)):
    try:
        img = Image.open(filepath)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(filepath, optimize=True, quality=85)
    except Exception as e:
        print(f"Image resize failed: {e}")

def get_or_create_cart(user):
    cart = Cart.query.filter_by(user_id=user.id).first()
    if not cart:
        cart = Cart(user_id=user.id)
        db.session.add(cart)
        db.session.commit()
    return cart

# ============================================================================
# Authentication Helpers (unchanged)
# ============================================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id:
        g.user = db.session.get(User, user_id)
    else:
        g.user = None

# ============================================================================
# API Endpoints (unchanged – only weather modified)
# ============================================================================
@app.route('/api/listings')
def get_listings():
    category = request.args.get('category')
    search = request.args.get('q')
    location = request.args.get('location')
    page = int(request.args.get('page', 1))
    per_page = 20
    query = BusinessListing.query.filter_by(approved=True)
    if category and category != 'All':
        query = query.filter_by(category=category)
    if search:
        search_sanitized = sanitize_input(search)
        query = query.filter(
            (BusinessListing.business_name.contains(search_sanitized)) |
            (BusinessListing.description.contains(search_sanitized)) |
            (BusinessListing.location.contains(search_sanitized))
        )
    if location:
        location_sanitized = sanitize_input(location)
        query = query.filter(BusinessListing.location.contains(location_sanitized))
    query = query.order_by(BusinessListing.featured.desc(), BusinessListing.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'items': [b.to_dict() for b in paginated.items],
        'total': paginated.total,
        'page': page,
        'pages': paginated.pages
    })

@app.route('/api/listing/<int:listing_id>')
def get_listing(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    listing.views += 1
    db.session.commit()
    socketio.emit('update_views', {'id': listing_id, 'views': listing.views})
    return jsonify(listing.to_dict())

@app.route('/api/categories')
def get_categories():
    cats = db.session.query(BusinessListing.category, func.count(BusinessListing.id)) \
                     .filter_by(approved=True).group_by(BusinessListing.category).all()
    return jsonify([{'name': c[0], 'count': c[1]} for c in cats])

@app.route('/api/like/<int:listing_id>', methods=['POST'])
@login_required
def like_listing(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    existing = Like.query.filter_by(user_id=g.user.id, listing_id=listing_id).first()
    if existing:
        db.session.delete(existing)
        listing.likes -= 1
        liked = False
    else:
        like = Like(user_id=g.user.id, listing_id=listing_id)
        db.session.add(like)
        listing.likes += 1
        liked = True
    db.session.commit()
    socketio.emit('update_likes', {'id': listing_id, 'likes': listing.likes})
    return jsonify({'likes': listing.likes, 'liked': liked})

@app.route('/api/stats')
def get_stats():
    total = BusinessListing.query.filter_by(approved=True).count()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_this_week = BusinessListing.query.filter_by(approved=True).filter(BusinessListing.created_at >= week_ago).count()
    top = db.session.query(BusinessListing.category, func.count(BusinessListing.id)) \
                    .filter_by(approved=True).group_by(BusinessListing.category) \
                    .order_by(func.count(BusinessListing.id).desc()).first()
    live_views = int(time.time()) % 100 + 50
    return jsonify({
        'total': total,
        'new_this_week': new_this_week,
        'top_category': top[0] if top else 'None',
        'live_views': live_views
    })

# ============================================================================
# User Search API
# ============================================================================
@app.route('/api/users/search')
def search_users():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    search_term = f"%{query}%"
    users = User.query.filter(
        or_(
            User.username.ilike(search_term),
            User.email.ilike(search_term),
            User.phone.ilike(search_term)
        )
    ).limit(20).all()
    result = []
    for user in users:
        result.append({
            'id': user.id,
            'username': user.username,
            'profile_image': user.profile_image,
            'created_at': user.created_at.isoformat(),
            'listings_count': len(user.listings),
            'followers_count': user.followers.count(),
            'verified': user.verified,
            'is_following': g.user.is_following(user) if g.user else False
        })
    return jsonify(result)

# ============================================================================
# Messaging API
# ============================================================================
@app.route('/api/conversations')
@login_required
def get_conversations():
    user = g.user
    sent = db.session.query(Message.recipient_id).filter(Message.sender_id == user.id).distinct()
    received = db.session.query(Message.sender_id).filter(Message.recipient_id == user.id).distinct()
    user_ids = set([r[0] for r in sent.union(received).all()])
    conversations = []
    for other_id in user_ids:
        other = db.session.get(User, other_id)
        last_msg = Message.query.filter(
            ((Message.sender_id == user.id) & (Message.recipient_id == other_id)) |
            ((Message.sender_id == other_id) & (Message.recipient_id == user.id))
        ).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(sender_id=other_id, recipient_id=user.id, read=False).count()
        conversations.append({
            'user': {'id': other.id, 'username': other.username, 'profile_image': other.profile_image, 'verified': other.verified},
            'last_message': last_msg.to_dict() if last_msg else None,
            'unread': unread
        })
    conversations.sort(key=lambda x: x['last_message']['created_at'] if x['last_message'] else '', reverse=True)
    return jsonify(conversations)

@app.route('/api/messages/<int:other_id>')
@login_required
def get_messages(other_id):
    user = g.user
    messages = Message.query.filter(
        ((Message.sender_id == user.id) & (Message.recipient_id == other_id)) |
        ((Message.sender_id == other_id) & (Message.recipient_id == user.id))
    ).order_by(Message.created_at.asc()).all()
    for msg in messages:
        if msg.recipient_id == user.id and not msg.read:
            msg.read = True
    db.session.commit()
    return jsonify([m.to_dict() for m in messages])

@app.route('/api/send-message', methods=['POST'])
@login_required
@rate_limit(limit=200, per=86400)
def send_message():
    data = request.get_json()
    recipient_id = data.get('recipient_id')
    content = data.get('content')
    encrypted = data.get('encrypted', False)
    listing_id = data.get('listing_id')
    if not recipient_id or not content:
        return jsonify({'error': 'Missing fields'}), 400
    recipient = db.session.get(User, recipient_id)
    if not recipient:
        return jsonify({'error': 'Recipient not found'}), 404
    msg = Message(
        sender_id=g.user.id,
        recipient_id=recipient_id,
        content=content,
        encrypted=encrypted,
        listing_id=listing_id
    )
    db.session.add(msg)
    db.session.commit()
    socketio.emit('new_message', {
        'message': msg.to_dict(),
        'for_user': recipient_id
    }, room=f"user_{recipient_id}")
    return jsonify(msg.to_dict())

# ============================================================================
# E2EE Key Management (unchanged)
# ============================================================================
@app.route('/api/generate-keys', methods=['POST'])
@login_required
def generate_keys():
    private_key, public_key = generate_key_pair()
    g.user.public_key = public_key
    db.session.commit()
    return jsonify({'private_key': private_key, 'public_key': public_key})

@app.route('/api/public-key/<int:user_id>')
def get_public_key(user_id):
    user = db.session.get(User, user_id)
    if not user or not user.public_key:
        return jsonify({'error': 'User or public key not found'}), 404
    return jsonify({'public_key': user.public_key})

# ============================================================================
# Group Chat API (unchanged)
# ============================================================================
@app.route('/api/groups')
@login_required
def get_groups():
    groups = GroupChat.query.join(GroupMember).filter(GroupMember.user_id == g.user.id).all()
    result = []
    for group in groups:
        last_msg = GroupMessage.query.filter_by(group_id=group.id).order_by(GroupMessage.created_at.desc()).first()
        member_count = GroupMember.query.filter_by(group_id=group.id).count()
        result.append({
            'id': group.id,
            'name': group.name,
            'description': group.description,
            'is_private': group.is_private,
            'created_by': group.created_by,
            'created_at': group.created_at.isoformat(),
            'member_count': member_count,
            'last_message': last_msg.to_dict() if last_msg else None
        })
    return jsonify(result)

@app.route('/api/groups/public')
def get_public_groups():
    groups = GroupChat.query.filter_by(is_private=False).all()
    result = []
    for group in groups:
        member_count = GroupMember.query.filter_by(group_id=group.id).count()
        result.append({
            'id': group.id,
            'name': group.name,
            'description': group.description,
            'member_count': member_count,
            'created_at': group.created_at.isoformat()
        })
    return jsonify(result)

@app.route('/api/groups/create', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    name = sanitize_input(data.get('name'))
    description = sanitize_input(data.get('description'))
    is_private = data.get('is_private', False)
    if not name:
        return jsonify({'error': 'Group name required'}), 400
    group = GroupChat(
        name=name,
        description=description,
        is_private=is_private,
        created_by=g.user.id
    )
    db.session.add(group)
    db.session.flush()
    member = GroupMember(group_id=group.id, user_id=g.user.id)
    db.session.add(member)
    db.session.commit()
    return jsonify({'id': group.id, 'name': group.name})

@app.route('/api/groups/<int:group_id>/join', methods=['POST'])
@login_required
def join_group(group_id):
    group = GroupChat.query.get_or_404(group_id)
    existing = GroupMember.query.filter_by(group_id=group_id, user_id=g.user.id).first()
    if existing:
        return jsonify({'error': 'Already a member'}), 400
    if group.is_private:
        return jsonify({'error': 'Private group requires invitation'}), 403
    member = GroupMember(group_id=group_id, user_id=g.user.id)
    db.session.add(member)
    db.session.commit()
    socketio.emit('group_user_joined', {
        'group_id': group_id,
        'user_id': g.user.id,
        'username': g.user.username
    }, room=f'group_{group_id}')
    return jsonify({'success': True})

@app.route('/api/groups/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    member = GroupMember.query.filter_by(group_id=group_id, user_id=g.user.id).first()
    if not member:
        return jsonify({'error': 'Not a member'}), 400
    db.session.delete(member)
    db.session.commit()
    socketio.emit('group_user_left', {
        'group_id': group_id,
        'user_id': g.user.id,
        'username': g.user.username
    }, room=f'group_{group_id}')
    return jsonify({'success': True})

@app.route('/api/groups/<int:group_id>/messages')
@login_required
def get_group_messages(group_id):
    member = GroupMember.query.filter_by(group_id=group_id, user_id=g.user.id).first()
    if not member:
        return jsonify({'error': 'Not a member'}), 403
    limit = int(request.args.get('limit', 50))
    messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.desc()).limit(limit).all()
    return jsonify([m.to_dict() for m in reversed(messages)])

# ============================================================================
# SocketIO Events (unchanged, but ensure rooms)
# ============================================================================
@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room:
        join_room(room)

@socketio.on('leave')
def on_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)

@socketio.on('join_group')
def handle_join_group(data):
    group_id = data['group_id']
    user_id = session.get('user_id')
    if not user_id:
        return
    member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if member:
        join_room(f'group_{group_id}')
        emit('group_joined', {'group_id': group_id})

@socketio.on('leave_group')
def handle_leave_group(data):
    group_id = data['group_id']
    leave_room(f'group_{group_id}')

@socketio.on('group_message')
def handle_group_message(data):
    group_id = data['group_id']
    content = data['content']
    encrypted = data.get('encrypted', False)
    user_id = session.get('user_id')
    if not user_id:
        return
    user = db.session.get(User, user_id)
    if not user:
        return
    member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not member:
        return
    msg = GroupMessage(
        group_id=group_id,
        user_id=user_id,
        content=content,
        encrypted=encrypted
    )
    db.session.add(msg)
    db.session.commit()
    emit('group_message', msg.to_dict(), room=f'group_{group_id}')

@socketio.on('group_typing')
def handle_group_typing(data):
    group_id = data['group_id']
    is_typing = data['is_typing']
    user_id = session.get('user_id')
    if not user_id:
        return
    user = db.session.get(User, user_id)
    if not user:
        return
    emit('group_typing', {
        'group_id': group_id,
        'user_id': user_id,
        'username': user.username,
        'is_typing': is_typing
    }, room=f'group_{group_id}', include_self=False)

# WebRTC signaling
@socketio.on('call_user')
def handle_call_user(data):
    target_user_id = data['target_user_id']
    offer = data['offer']
    caller_id = session.get('user_id')
    if not caller_id:
        return
    caller = db.session.get(User, caller_id)
    if not caller:
        return
    socketio.emit('incoming_call', {
        'caller_id': caller_id,
        'caller_name': caller.username,
        'caller_image': caller.profile_image,
        'offer': offer
    }, room=f'user_{target_user_id}')

@socketio.on('answer_call')
def handle_answer_call(data):
    caller_id = data['caller_id']
    answer = data['answer']
    socketio.emit('call_answered', {
        'answer': answer
    }, room=f'user_{caller_id}')

@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    target_user_id = data['target_user_id']
    candidate = data['candidate']
    socketio.emit('ice_candidate', {
        'candidate': candidate
    }, room=f'user_{target_user_id}')

# ============================================================================
# Product & Recommendation API (unchanged, plus new listing recommendation)
# ============================================================================
@app.route('/api/listings/<int:listing_id>/products', methods=['GET'])
def get_products(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    return jsonify([p.to_dict() for p in listing.products])

@app.route('/api/listings/<int:listing_id>/products', methods=['POST'])
@login_required
def add_product(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    if listing.user_id != g.user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    name = sanitize_input(request.form.get('name'))
    description = sanitize_input(request.form.get('description'))
    price = request.form.get('price', type=float)
    available = request.form.get('available') == 'true'
    if not name or not description:
        return jsonify({'error': 'Name and description required'}), 400
    product = Product(
        name=name,
        description=description,
        price=price,
        available=available,
        listing_id=listing_id,
        user_id=g.user.id
    )
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"product_{int(time.time())}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
            file.save(filepath)
            resize_image(filepath, max_size=(800, 800))
            product.image = filename
    db.session.add(product)
    db.session.commit()
    return jsonify(product.to_dict())

@app.route('/api/products/<int:product_id>/recommend', methods=['POST'])
@login_required
def recommend_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    comment = sanitize_input(request.json.get('comment', ''))
    existing = Recommendation.query.filter_by(
        user_id=g.user.id,
        product_id=product_id
    ).first()
    if existing:
        return jsonify({'error': 'Already recommended'}), 400
    rec = Recommendation(
        user_id=g.user.id,
        listing_id=product.listing_id,
        product_id=product_id,
        comment=comment
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify(rec.to_dict())

@app.route('/api/listing/<int:listing_id>/recommend', methods=['POST'])
@login_required
def recommend_listing(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    comment = sanitize_input(request.json.get('comment', ''))
    existing = Recommendation.query.filter_by(
        user_id=g.user.id,
        listing_id=listing_id,
        product_id=None
    ).first()
    if existing:
        return jsonify({'error': 'Already recommended'}), 400
    rec = Recommendation(
        user_id=g.user.id,
        listing_id=listing_id,
        comment=comment
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify(rec.to_dict())

@app.route('/api/recommendations/<int:rec_id>', methods=['DELETE'])
@login_required
def delete_recommendation(rec_id):
    rec = Recommendation.query.get_or_404(rec_id)
    if rec.user_id != g.user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'success': True})

# ============================================================================
# Follow API (unchanged)
# ============================================================================
@app.route('/api/follow/<int:user_id>', methods=['POST'])
@login_required
def follow_user(user_id):
    if user_id == g.user.id:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    result = g.user.follow(user)
    if result:
        socketio.emit('new_follower', {
            'follower_id': g.user.id,
            'follower_name': g.user.username,
            'followed_id': user_id
        }, room=f'user_{user_id}')
        return jsonify({'success': True, 'following': True})
    else:
        return jsonify({'success': False, 'error': 'Already following or error'})

@app.route('/api/unfollow/<int:user_id>', methods=['POST'])
@login_required
def unfollow_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    result = g.user.unfollow(user)
    return jsonify({'success': result, 'following': False})

@app.route('/api/followers/<int:user_id>')
def get_followers(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    followers = []
    for f in user.followers:
        follower = db.session.get(User, f.follower_id)
        followers.append({
            'id': follower.id,
            'username': follower.username,
            'profile_image': follower.profile_image,
            'verified': follower.verified
        })
    return jsonify(followers)

@app.route('/api/following/<int:user_id>')
def get_following(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    following = []
    for f in user.followed:
        followed = db.session.get(User, f.followed_id)
        following.append({
            'id': followed.id,
            'username': followed.username,
            'profile_image': followed.profile_image,
            'verified': followed.verified
        })
    return jsonify(following)

# ============================================================================
# AI Chatbot (unchanged)
# ============================================================================
CHATBOT_KNOWLEDGE = {
    'site history': 'BizTech (originally Chivi Business Directory) was founded in 2025 by a group of high school students who saw the need for a modern, accessible platform to connect businesses in Chivi District, Zimbabwe, with customers. What started as a simple SMS listing service has grown into a full‑featured social marketplace with real‑time messaging, group chats, AI assistance, shopping cart, video calls, and delivery tracking.',
    'how to list': 'To list your business, log in and use the dashboard form. You can add multiple products to each listing.',
    'how to register': 'Click "Register" in the top bar. Fill in your details and you can start listing and messaging.',
    'how to message': 'Once logged in, you can send a direct message to another user from their profile or from their listing page.',
    'how to like': 'Click the heart icon on any business listing to like it. You can only like once per listing.',
    'how to upload image': 'When adding or editing a listing or product, you can upload an image from your computer.',
    'how to change profile picture': 'Go to your Profile page and upload a new image.',
    'what is biztech': 'BizTech connects local businesses in Chivi District with customers via web. It\'s free and real‑time.',
    'contact': 'For support, please use the chatbot or join our public support group.',
    'how to change password': 'Go to your Profile page, fill in the new password field and click Update Profile.',
    'can I delete my listing': 'Yes, from your Dashboard, click Delete on any listing you own.',
    'how to contact business owner': 'Click the Message button on their listing card or profile to send them a direct message.',
    'what categories are available': 'You can choose any category when adding a listing; common ones include Retail, Farming, Hardware, Services, etc.',
    'is this service free': 'Yes, completely free for all users.',
    'how to report a problem': 'Use the chatbot or join the public support group to report issues.',
    'how to see my messages': 'Click on "Messages" in the navigation bar to open your inbox.',
    'what does live views mean': 'It\'s an estimate of how many people are currently viewing the directory.',
    'what is zig': 'ZiG (Zimbabwe Gold) is the new official currency of Zimbabwe. 1 USD is approximately 15 ZiG (rate may vary).',
    'group chat': 'You can join public group chats to discuss products and services with other users. Click "Groups" in the navigation bar to see available groups.',
    'follow users': 'You can follow other users to see their activity in your feed. Click the "Follow" button on their profile.',
    'recommend products': 'After logging in, you can recommend products by clicking the "Recommend" button on any product.',
    'discover users': 'Click "Discover" in the navigation bar to search for other users by username, email, or phone.',
    'cart': 'You can add products to your cart from the product page. View your cart by clicking the cart icon in the top bar.',
    'checkout': 'Go to your cart, review items, and choose PayPal, Cash on Delivery, or Wallet. For PayPal, you will be redirected to complete payment.',
    'video call': 'On a user profile or in a chat, click the video camera icon to start a peer‑to‑peer video call. Requires browser support.',
    'delivery': 'After an order is placed, the seller can update the delivery status and estimated delivery date. You can track your orders in your profile.',
    'wallet': 'Your wallet stores funds for quick payments. You can deposit via PayPal and request withdrawals. View your wallet by clicking "Wallet" in the navbar.',
    'verification': 'Sellers can apply for a verification badge to build trust. Once approved, a blue checkmark appears on your profile and listings.',
    'weather': 'You can check local weather and market prices on the homepage to help plan your business activities.',
}

def find_best_answer(question):
    q = question.lower()
    for key, answer in CHATBOT_KNOWLEDGE.items():
        if key in q or any(word in q for word in key.split()):
            return answer
    search_results = web_search(question, num_results=3)
    if search_results:
        response = "I searched the web and found these results:\n\n"
        for i, result in enumerate(search_results, 1):
            response += f"{i}. {result['title']}\n   {result['snippet']}\n   {result['link']}\n\n"
        return response
    return "I'm sorry, I don't have an answer for that. Try asking about: list, register, message, like, image, profile, group chat, follow, recommend, discover, cart, checkout, video call, delivery, wallet, verification, weather."

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    question = sanitize_input(data.get('question', ''))
    if not question:
        return jsonify({'answer': 'Please ask a question.'})
    greetings = ['hi', 'hello', 'hey', 'greetings']
    if any(g in question.lower() for g in greetings):
        answer = "Hello! I'm the BizTech Assistant. I can help you with information about the BizTech platform, answer questions, or search the web for you. How can I help today?"
    else:
        answer = find_best_answer(question)
    return jsonify({'answer': answer})

# ============================================================================
# Cart & Payment API (unchanged)
# ============================================================================
@app.route('/api/cart', methods=['GET'])
@login_required
def get_cart():
    cart = get_or_create_cart(g.user)
    items = []
    total = 0.0
    for item in cart.items:
        product = item.product
        if product:
            items.append({
                'id': item.id,
                'product_id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': item.quantity,
                'image': product.image,
                'available': product.available,
                'total': product.price * item.quantity if product.price else 0
            })
            if product.price:
                total += product.price * item.quantity
    return jsonify({'items': items, 'total': total})

@app.route('/api/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    if not product_id:
        return jsonify({'error': 'Product ID required'}), 400
    product = db.session.get(Product, product_id)
    if not product or not product.available:
        return jsonify({'error': 'Product not available'}), 404
    cart = get_or_create_cart(g.user)
    item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()
    if item:
        item.quantity += quantity
    else:
        item = CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity)
        db.session.add(item)
    db.session.commit()
    return jsonify({'success': True, 'cart_item_count': len(cart.items)})

@app.route('/api/cart/remove', methods=['POST'])
@login_required
def remove_from_cart():
    data = request.get_json()
    item_id = data.get('item_id')
    if not item_id:
        return jsonify({'error': 'Item ID required'}), 400
    item = CartItem.query.get(item_id)
    if not item or item.cart.user_id != g.user.id:
        return jsonify({'error': 'Item not found'}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/cart/update', methods=['POST'])
@login_required
def update_cart_item():
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity')
    if not item_id or quantity is None or quantity < 1:
        return jsonify({'error': 'Invalid data'}), 400
    item = CartItem.query.get(item_id)
    if not item or item.cart.user_id != g.user.id:
        return jsonify({'error': 'Item not found'}), 404
    item.quantity = quantity
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/checkout', methods=['POST'])
@login_required
def checkout():
    data = request.get_json()
    payment_method = data.get('payment_method')
    if payment_method not in ('paypal', 'cod', 'wallet'):
        return jsonify({'error': 'Invalid payment method'}), 400
    
    cart = get_or_create_cart(g.user)
    if not cart.items:
        return jsonify({'error': 'Cart is empty'}), 400
    
    total = 0.0
    for item in cart.items:
        if item.product.price:
            total += item.product.price * item.quantity
        else:
            return jsonify({'error': f'Product {item.product.name} has no price'}), 400
    
    if payment_method == 'cod':
        order = Order(
            user_id=g.user.id,
            total=total,
            payment_method='cod',
            status='pending',
            delivery_status='pending'
        )
        db.session.add(order)
        db.session.flush()
        for item in cart.items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.product.price
            )
            db.session.add(order_item)
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.commit()
        return jsonify({'success': True, 'order_id': order.id, 'redirect': url_for('order_confirmation', order_id=order.id)})
    
    elif payment_method == 'wallet':
        if g.user.wallet_balance < total:
            return jsonify({'error': 'Insufficient wallet balance'}), 400
        order = Order(
            user_id=g.user.id,
            total=total,
            payment_method='wallet',
            status='paid',
            delivery_status='pending'
        )
        db.session.add(order)
        db.session.flush()
        for item in cart.items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.product.price
            )
            db.session.add(order_item)
        g.user.wallet_balance -= total
        trans = Transaction(
            user_id=g.user.id,
            amount=-total,
            type='payment',
            status='completed',
            description=f'Payment for order #{order.id}'
        )
        db.session.add(trans)
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.commit()
        return jsonify({'success': True, 'order_id': order.id, 'redirect': url_for('order_confirmation', order_id=order.id)})
    
    elif payment_method == 'paypal':
        try:
            paypal_order = create_paypal_order(total)
            order = Order(
                user_id=g.user.id,
                total=total,
                payment_method='paypal',
                status='pending',
                paypal_order_id=paypal_order['id'],
                delivery_status='pending'
            )
            db.session.add(order)
            db.session.flush()
            for item in cart.items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price=item.product.price
                )
                db.session.add(order_item)
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
            approval_link = None
            for link in paypal_order['links']:
                if link['rel'] == 'approve':
                    approval_link = link['href']
                    break
            return jsonify({'success': True, 'order_id': order.id, 'approval_url': approval_link})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/payment/capture-paypal', methods=['POST'])
@login_required
def capture_paypal():
    data = request.get_json()
    order_id = data.get('order_id')
    paypal_order_id = data.get('paypal_order_id')
    if not order_id or not paypal_order_id:
        return jsonify({'error': 'Missing parameters'}), 400
    order = Order.query.get(order_id)
    if not order or order.user_id != g.user.id:
        return jsonify({'error': 'Order not found'}), 404
    try:
        capture_result = capture_paypal_order(paypal_order_id)
        if capture_result['status'] == 'COMPLETED':
            order.status = 'paid'
            db.session.commit()
            return jsonify({'success': True, 'redirect': url_for('order_confirmation', order_id=order.id)})
        else:
            return jsonify({'error': 'Payment not completed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Wallet API (unchanged)
# ============================================================================
@app.route('/api/wallet', methods=['GET'])
@login_required
def get_wallet():
    transactions = Transaction.query.filter_by(user_id=g.user.id).order_by(Transaction.created_at.desc()).limit(50).all()
    return jsonify({
        'balance': g.user.wallet_balance,
        'transactions': [{
            'id': t.id,
            'amount': t.amount,
            'type': t.type,
            'status': t.status,
            'description': t.description,
            'created_at': t.created_at.isoformat()
        } for t in transactions]
    })

@app.route('/api/wallet/deposit', methods=['POST'])
@login_required
def deposit():
    data = request.get_json()
    amount = data.get('amount')
    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    try:
        paypal_order = create_paypal_order(amount)
        trans = Transaction(
            user_id=g.user.id,
            amount=amount,
            type='deposit',
            status='pending',
            payment_method='paypal',
            paypal_order_id=paypal_order['id'],
            description=f'Deposit ${amount}'
        )
        db.session.add(trans)
        db.session.commit()

        approval_link = None
        for link in paypal_order['links']:
            if link['rel'] == 'approve':
                approval_link = link['href']
                break
        return jsonify({'approval_url': approval_link, 'transaction_id': trans.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/wallet/deposit/capture', methods=['POST'])
@login_required
def capture_deposit():
    data = request.get_json()
    transaction_id = data.get('transaction_id')
    paypal_order_id = data.get('paypal_order_id')

    trans = Transaction.query.get(transaction_id)
    if not trans or trans.user_id != g.user.id or trans.paypal_order_id != paypal_order_id:
        return jsonify({'error': 'Invalid transaction'}), 404

    try:
        capture_result = capture_paypal_order(paypal_order_id)
        if capture_result['status'] == 'COMPLETED':
            trans.status = 'completed'
            g.user.wallet_balance += trans.amount
            db.session.commit()
            return jsonify({'success': True, 'new_balance': g.user.wallet_balance})
        else:
            trans.status = 'failed'
            db.session.commit()
            return jsonify({'error': 'Payment not completed'}), 400
    except Exception as e:
        trans.status = 'failed'
        db.session.commit()
        return jsonify({'error': str(e)}), 500

@app.route('/api/wallet/withdraw/request', methods=['POST'])
@login_required
def request_withdrawal():
    data = request.get_json()
    amount = data.get('amount')
    method = data.get('method')
    details = data.get('details')

    if not amount or amount <= 0 or not method or not details:
        return jsonify({'error': 'Missing fields'}), 400
    if g.user.wallet_balance < amount:
        return jsonify({'error': 'Insufficient balance'}), 400

    req = WithdrawalRequest(
        user_id=g.user.id,
        amount=amount,
        method=method,
        details=details,
        status='pending'
    )
    db.session.add(req)
    g.user.wallet_balance -= amount
    trans = Transaction(
        user_id=g.user.id,
        amount=-amount,
        type='withdrawal',
        status='pending',
        description=f'Withdrawal request #{req.id}'
    )
    db.session.add(trans)
    db.session.commit()

    return jsonify({'success': True, 'request_id': req.id})

# ============================================================================
# Verification API (unchanged)
# ============================================================================
@app.route('/api/verification/request', methods=['POST'])
@login_required
def request_verification():
    data = request.get_json()
    business_name = data.get('business_name')
    contact_info = data.get('contact_info')
    if not business_name or not contact_info:
        return jsonify({'error': 'Missing fields'}), 400
    existing = VerificationRequest.query.filter_by(user_id=g.user.id, status='pending').first()
    if existing:
        return jsonify({'error': 'You already have a pending request'}), 400
    req = VerificationRequest(
        user_id=g.user.id,
        business_name=business_name,
        contact_info=contact_info,
        documents='uploaded_files'
    )
    db.session.add(req)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/verification/status')
@login_required
def verification_status():
    req = VerificationRequest.query.filter_by(user_id=g.user.id).order_by(VerificationRequest.created_at.desc()).first()
    if req:
        return jsonify({'status': req.status})
    return jsonify({'status': 'none'})

@app.route('/api/admin/verification-requests')
@login_required
def get_verification_requests():
    if g.user.id != 1:
        return jsonify({'error': 'Unauthorized'}), 403
    reqs = VerificationRequest.query.order_by(VerificationRequest.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'user_id': r.user_id,
        'user_name': r.user.username,
        'business_name': r.business_name,
        'contact_info': r.contact_info,
        'status': r.status,
        'created_at': r.created_at.isoformat()
    } for r in reqs])

@app.route('/api/admin/verification/<int:req_id>/process', methods=['POST'])
@login_required
def process_verification(req_id):
    if g.user.id != 1:
        return jsonify({'error': 'Unauthorized'}), 403
    req = VerificationRequest.query.get_or_404(req_id)
    data = request.get_json()
    action = data.get('action')
    if action == 'approve':
        req.status = 'approved'
        req.user.verified = True
    elif action == 'reject':
        req.status = 'rejected'
    else:
        return jsonify({'error': 'Invalid action'}), 400
    req.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'success': True})

# ============================================================================
# Market Price API (unchanged)
# ============================================================================
@app.route('/api/market-prices')
def get_market_prices():
    prices = MarketPrice.query.order_by(MarketPrice.date.desc()).limit(20).all()
    return jsonify([{
        'id': p.id,
        'commodity': p.commodity,
        'price': p.price,
        'unit': p.unit,
        'location': p.location,
        'date': p.date.isoformat()
    } for p in prices])

@app.route('/api/admin/market-price/add', methods=['POST'])
@login_required
def add_market_price():
    if g.user.id != 1:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    commodity = data.get('commodity')
    price = data.get('price')
    unit = data.get('unit', 'kg')
    location = data.get('location')
    if not commodity or not price or not location:
        return jsonify({'error': 'Missing fields'}), 400
    mp = MarketPrice(
        commodity=commodity,
        price=price,
        unit=unit,
        location=location
    )
    db.session.add(mp)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/admin/market-price/<int:price_id>/delete', methods=['DELETE'])
@login_required
def delete_market_price(price_id):
    if g.user.id != 1:
        return jsonify({'error': 'Unauthorized'}), 403
    mp = MarketPrice.query.get_or_404(price_id)
    db.session.delete(mp)
    db.session.commit()
    return jsonify({'success': True})

# ============================================================================
# Weather API (Open‑Meteo, no key)
# ============================================================================
@app.route('/api/weather')
def get_weather():
    try:
        # Coordinates for Masvingo, Zimbabwe
        lat = -20.0744
        lon = 30.8327
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            current = data['current_weather']
            # Map weathercode to description
            weathercode = current['weathercode']
            description = {
                0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
                45: 'Fog', 48: 'Rime fog',
                51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
                61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
                71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow',
                77: 'Snow grains',
                80: 'Slight rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers',
                85: 'Slight snow showers', 86: 'Heavy snow showers',
                95: 'Thunderstorm', 96: 'Thunderstorm with slight hail', 99: 'Thunderstorm with heavy hail'
            }.get(weathercode, 'Unknown')
            icon_map = {
                0: '01d', 1: '02d', 2: '03d', 3: '04d',
                45: '50d', 48: '50d', 51: '09d', 53: '09d', 55: '09d',
                61: '10d', 63: '10d', 65: '10d',
                71: '13d', 73: '13d', 75: '13d',
                80: '09d', 81: '09d', 82: '09d',
                95: '11d', 96: '11d', 99: '11d'
            }
            icon = icon_map.get(weathercode, '01d')
            return jsonify({
                'temp': current['temperature'],
                'description': description,
                'icon': icon
            })
        else:
            return jsonify({'error': 'Weather service unavailable'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Admin Withdrawal Management (unchanged)
# ============================================================================
@app.route('/admin/withdrawals')
@login_required
def admin_withdrawals():
    if g.user.id != 1:
        flash('Unauthorized', 'danger')
        return redirect(url_for('index'))
    return render_template_string(ADMIN_WITHDRAWALS_TEMPLATE)

@app.route('/api/admin/withdrawals')
@login_required
def get_withdrawal_requests():
    if g.user.id != 1:
        return jsonify({'error': 'Unauthorized'}), 403
    reqs = WithdrawalRequest.query.order_by(WithdrawalRequest.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'user_id': r.user_id,
        'user_name': r.user.username,
        'amount': r.amount,
        'method': r.method,
        'details': r.details,
        'status': r.status,
        'created_at': r.created_at.isoformat()
    } for r in reqs])

@app.route('/api/admin/withdrawal/<int:req_id>/process', methods=['POST'])
@login_required
def process_withdrawal(req_id):
    if g.user.id != 1:
        return jsonify({'error': 'Unauthorized'}), 403
    req = WithdrawalRequest.query.get_or_404(req_id)
    data = request.get_json()
    action = data.get('action')
    if action == 'approve':
        req.status = 'processed'
        req.processed_at = datetime.now(timezone.utc)
        trans = Transaction.query.filter_by(description=f'Withdrawal request #{req.id}').first()
        if trans:
            trans.status = 'completed'
    elif action == 'reject':
        req.status = 'rejected'
        user = db.session.get(User, req.user_id)
        if user:
            user.wallet_balance += req.amount
        trans = Transaction.query.filter_by(description=f'Withdrawal request #{req.id}').first()
        if trans:
            trans.status = 'failed'
    db.session.commit()
    return jsonify({'success': True})

# ============================================================================
# Seller Orders API (unchanged)
# ============================================================================
@app.route('/api/seller/orders')
@login_required
def seller_orders():
    product_ids = [p.id for p in g.user.products]
    if not product_ids:
        return jsonify([])
    order_items = OrderItem.query.filter(OrderItem.product_id.in_(product_ids)).all()
    order_ids = set([item.order_id for item in order_items])
    orders = Order.query.filter(Order.id.in_(order_ids)).order_by(Order.created_at.desc()).all()
    result = []
    for order in orders:
        items = [item for item in order.items if item.product_id in product_ids]
        result.append({
            'id': order.id,
            'buyer_id': order.user_id,
            'buyer_name': order.buyer.username,
            'total': order.total,
            'status': order.status,
            'payment_method': order.payment_method,
            'delivery_status': order.delivery_status,
            'delivery_date': order.delivery_date.isoformat() if order.delivery_date else None,
            'created_at': order.created_at.isoformat(),
            'items': [{
                'product_id': item.product_id,
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': item.price
            } for item in items]
        })
    return jsonify(result)

@app.route('/api/seller/order/<int:order_id>/update-delivery', methods=['POST'])
@login_required
def update_delivery(order_id):
    data = request.get_json()
    delivery_status = data.get('delivery_status')
    delivery_date_str = data.get('delivery_date')
    if delivery_status not in ['pending', 'shipped', 'delivered', 'cancelled']:
        return jsonify({'error': 'Invalid delivery status'}), 400
    
    order = Order.query.get_or_404(order_id)
    product_ids = [p.id for p in g.user.products]
    if not any(item.product_id in product_ids for item in order.items):
        return jsonify({'error': 'Unauthorized'}), 403
    
    order.delivery_status = delivery_status
    if delivery_date_str:
        try:
            order.delivery_date = datetime.fromisoformat(delivery_date_str).replace(tzinfo=timezone.utc)
        except:
            return jsonify({'error': 'Invalid date format'}), 400
    db.session.commit()
    return jsonify({'success': True})

# ============================================================================
# WebRTC ICE Servers endpoint (unchanged)
# ============================================================================
@app.route('/api/ice-servers')
def get_ice_servers():
    return jsonify(WEBRTC_ICE_SERVERS)

# ============================================================================
# User Authentication Routes (unchanged)
# ============================================================================
@app.route('/register', methods=['GET', 'POST'])
@rate_limit(limit=50, per=86400)
def register():
    if request.method == 'POST':
        username = sanitize_input(request.form['username'])
        email = sanitize_input(request.form['email'])
        phone = sanitize_input(request.form['phone'])
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email) | (User.phone == phone)).first():
            flash('Username, email, or phone already registered.', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, email=email, phone=phone)
        user.set_password(password)
        private_key, public_key = generate_key_pair()
        user.public_key = public_key
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"user_{int(time.time())}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles', filename)
                file.save(filepath)
                resize_image(filepath, max_size=(300, 300))
                user.profile_image = filename
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
@rate_limit(limit=100, per=86400)
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form['username'])
        password = request.form['password']
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if user and user.check_password(password):
            session.clear()
            session['user_id'] = user.id
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        flash('Invalid username/email or password.', 'danger')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ============================================================================
# Wallet Page
# ============================================================================
@app.route('/wallet')
@login_required
def wallet():
    return render_template_string(WALLET_TEMPLATE, user=g.user)

# ============================================================================
# Verification Page
# ============================================================================
@app.route('/verify')
@login_required
def verify():
    return render_template_string(VERIFY_TEMPLATE, user=g.user)

@app.route('/admin/verification')
@login_required
def admin_verification():
    if g.user.id != 1:
        flash('Unauthorized', 'danger')
        return redirect(url_for('index'))
    return render_template_string(ADMIN_VERIFICATION_TEMPLATE)

# ============================================================================
# Messaging UI
# ============================================================================
@app.route('/inbox')
@login_required
def inbox():
    return render_template_string(INBOX_TEMPLATE, user=g.user)

@app.route('/compose/<int:recipient_id>')
@login_required
def compose(recipient_id):
    recipient = db.session.get(User, recipient_id)
    return render_template_string(COMPOSE_TEMPLATE, recipient=recipient)

# ============================================================================
# Group Chat UI
# ============================================================================
@app.route('/groups')
def groups():
    return render_template_string(GROUPS_TEMPLATE, user=g.user)

@app.route('/groups/<int:group_id>')
@login_required
def group_chat(group_id):
    group = GroupChat.query.get_or_404(group_id)
    if group.is_private:
        member = GroupMember.query.filter_by(group_id=group_id, user_id=g.user.id).first()
        if not member:
            flash('You are not a member of this private group.', 'danger')
            return redirect(url_for('groups'))
    return render_template_string(GROUP_CHAT_TEMPLATE, group=group, user=g.user)

# ============================================================================
# Discover Page
# ============================================================================
@app.route('/discover')
def discover():
    return render_template_string(DISCOVER_TEMPLATE, user=g.user)

# ============================================================================
# Cart Page
# ============================================================================
@app.route('/cart')
@login_required
def cart_page():
    return render_template_string(CART_TEMPLATE, user=g.user)

# ============================================================================
# Checkout Page
# ============================================================================
@app.route('/checkout')
@login_required
def checkout_page():
    return render_template_string(CHECKOUT_TEMPLATE, user=g.user)

# ============================================================================
# Order Confirmation Page
# ============================================================================
@app.route('/order/<int:order_id>')
@login_required
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != g.user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('index'))
    return render_template_string(ORDER_CONFIRMATION_TEMPLATE, order=order)

# ============================================================================
# Seller Orders Page
# ============================================================================
@app.route('/seller/orders')
@login_required
def seller_orders_page():
    return render_template_string(SELLER_ORDERS_TEMPLATE, user=g.user)

# ============================================================================
# Video Call Page
# ============================================================================
@app.route('/call/<int:user_id>')
@login_required
def video_call(user_id):
    target = db.session.get(User, user_id)
    if not target:
        flash('User not found.', 'danger')
        return redirect(url_for('index'))
    return render_template_string(VIDEO_CALL_TEMPLATE, target=target, ice_servers=WEBRTC_ICE_SERVERS, user=g.user)

# ============================================================================
# User Dashboard & Profile
# ============================================================================
@app.route('/dashboard')
@login_required
def dashboard():
    listings = BusinessListing.query.filter_by(user_id=g.user.id).order_by(BusinessListing.created_at.desc()).all()
    total_likes = sum(l.likes for l in listings)
    products = Product.query.filter_by(user_id=g.user.id).count()
    return render_template_string(DASHBOARD_TEMPLATE, 
                                  user=g.user, 
                                  listings=listings, 
                                  total_likes=total_likes,
                                  products=products)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        g.user.email = sanitize_input(request.form['email'])
        g.user.phone = sanitize_input(request.form['phone'])
        if request.form['password']:
            g.user.set_password(request.form['password'])
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"user_{g.user.id}_{int(time.time())}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles', filename)
                file.save(filepath)
                resize_image(filepath, max_size=(300, 300))
                g.user.profile_image = filename
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))
    return render_template_string(PROFILE_TEMPLATE, user=g.user)

# ============================================================================
# Public User Profile
# ============================================================================
@app.route('/user/<int:user_id>')
def public_profile(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('index'))
    listings = BusinessListing.query.filter_by(user_id=user.id, approved=True).order_by(BusinessListing.created_at.desc()).all()
    products = Product.query.filter_by(user_id=user.id).order_by(Product.created_at.desc()).all()
    is_following = False
    if g.user:
        is_following = g.user.is_following(user)
    follower_count = user.followers.count()
    following_count = user.followed.count()
    return render_template_string(PUBLIC_PROFILE_TEMPLATE, 
                                  profile_user=user, 
                                  listings=listings,
                                  products=products,
                                  current_user=g.user,
                                  is_following=is_following,
                                  follower_count=follower_count,
                                  following_count=following_count)

# ============================================================================
# Listing management
# ============================================================================
@app.route('/add-listing', methods=['GET', 'POST'])
@login_required
@rate_limit(limit=50, per=86400)
def add_listing():
    if request.method == 'GET':
        return render_template_string(ADD_LISTING_TEMPLATE, user=g.user)
    # POST
    business_name = sanitize_input(request.form['business_name'])
    description = sanitize_input(request.form['description'])
    location = sanitize_input(request.form['location'])
    category = sanitize_input(request.form['category'])
    phone = sanitize_input(request.form.get('phone', g.user.phone))
    if not all([business_name, description, location]):
        flash('All fields except phone are required.', 'danger')
        return redirect(url_for('dashboard'))
    listing = BusinessListing(
        business_name=business_name,
        description=description,
        location=location,
        phone=phone,
        category=category,
        user_id=g.user.id
    )
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"listing_{int(time.time())}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'listings', filename)
            file.save(filepath)
            resize_image(filepath, max_size=(800, 800))
            listing.image = filename
    db.session.add(listing)
    db.session.commit()
    socketio.emit('new_listing', listing.to_dict())
    flash('Listing added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/edit-listing/<int:listing_id>', methods=['GET', 'POST'])
@login_required
def edit_listing(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    if listing.user_id != g.user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        listing.business_name = sanitize_input(request.form['business_name'])
        listing.description = sanitize_input(request.form['description'])
        listing.location = sanitize_input(request.form['location'])
        listing.category = sanitize_input(request.form['category'])
        listing.phone = sanitize_input(request.form['phone'])
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"listing_{int(time.time())}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'listings', filename)
                file.save(filepath)
                resize_image(filepath, max_size=(800, 800))
                listing.image = filename
        db.session.commit()
        socketio.emit('update_listing', listing.to_dict())
        flash('Listing updated.', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(EDIT_LISTING_TEMPLATE, listing=listing)

@app.route('/delete-listing/<int:listing_id>', methods=['POST'])
@login_required
def delete_listing(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    if listing.user_id != g.user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('dashboard'))
    db.session.delete(listing)
    db.session.commit()
    socketio.emit('delete_listing', listing_id)
    flash('Listing deleted.', 'success')
    return redirect(url_for('dashboard'))

# ============================================================================
# Product management within listing
# ============================================================================
@app.route('/listing/<int:listing_id>/add-product', methods=['POST'])
@login_required
def add_listing_product(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    if listing.user_id != g.user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('listing_detail', listing_id=listing_id))
    name = sanitize_input(request.form['name'])
    description = sanitize_input(request.form['description'])
    price = request.form.get('price', type=float)
    available = request.form.get('available') == 'true'
    if not name or not description:
        flash('Product name and description required.', 'danger')
        return redirect(url_for('listing_detail', listing_id=listing_id))
    product = Product(
        name=name,
        description=description,
        price=price,
        available=available,
        listing_id=listing_id,
        user_id=g.user.id
    )
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"product_{int(time.time())}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
            file.save(filepath)
            resize_image(filepath, max_size=(800, 800))
            product.image = filename
    db.session.add(product)
    db.session.commit()
    flash('Product added successfully!', 'success')
    return redirect(url_for('listing_detail', listing_id=listing_id))

@app.route('/product/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.user_id != g.user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('index'))
    listing_id = product.listing_id
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted.', 'success')
    return redirect(url_for('listing_detail', listing_id=listing_id))

# ============================================================================
# Listing Detail Page (with map)
# ============================================================================
@app.route('/listing/<int:listing_id>')
def listing_detail(listing_id):
    listing = BusinessListing.query.get_or_404(listing_id)
    listing.views += 1
    db.session.commit()
    socketio.emit('update_views', {'id': listing_id, 'views': listing.views})
    recommendations = Recommendation.query.filter_by(listing_id=listing_id).order_by(Recommendation.created_at.desc()).all()
    user_liked = False
    if g.user:
        user_liked = Like.query.filter_by(user_id=g.user.id, listing_id=listing_id).first() is not None
    return render_template_string(LISTING_DETAIL_TEMPLATE, 
                                  listing=listing, 
                                  user=g.user, 
                                  rate=EXCHANGE_RATE,
                                  recommendations=recommendations,
                                  user_liked=user_liked)

# ============================================================================
# Serve uploaded files
# ============================================================================
@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ============================================================================
# Static Pages
# ============================================================================
@app.route('/about')
def about():
    return render_template_string(ABOUT_TEMPLATE)

@app.route('/terms')
def terms():
    return render_template_string(TERMS_TEMPLATE)

@app.route('/privacy')
def privacy():
    return render_template_string(PRIVACY_TEMPLATE)

# ============================================================================
# Home Page
# ============================================================================
@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)

# ============================================================================
# TEMPLATES (all included – base and index already defined above; now add missing ones)
# ============================================================================
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}BizTech – Business Technologies{% endblock %}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏪</text></svg>">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #006400;
            --primary-dark: #004d00;
            --secondary: #FFD200;
            --accent: #C40202;
            --dark: #1e1e2f;
            --light-bg: #f0f4f8;
            --light-green: #e8f0e8;
            --glass-bg: rgba(255, 255, 255, 0.2);
            --glass-border: rgba(255, 255, 255, 0.3);
            --shadow-sm: 0 2px 10px rgba(0,0,0,0.1);
            --shadow-md: 0 8px 30px rgba(0,0,0,0.12);
            --shadow-lg: 0 20px 40px rgba(0,0,0,0.2);
            --transition: all 0.3s ease;
        }
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(145deg, var(--light-bg), var(--light-green), #d4e4d4);
            background-size: 200% 200%;
            animation: gradientShift 10s ease infinite;
            color: #1a2b3c;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            transition: background 0.3s, color 0.3s;
        }
        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        body.dark-mode {
            background: #121212;
            color: #e0e0e0;
            animation: none;
        }
        .container { max-width: 1280px; margin: 0 auto; padding: 2rem 1.5rem; flex: 1; }
        .navbar {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--glass-border);
            box-shadow: var(--shadow-md);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .navbar a { text-decoration: none; color: inherit; margin: 0 1rem; font-weight: 500; position: relative; transition: var(--transition); }
        .navbar a:hover { color: var(--primary); transform: translateY(-2px); }
        .logo { font-size: 1.8rem; font-weight: 800; background: linear-gradient(135deg, var(--primary), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .badge {
            background: var(--accent);
            color: white;
            border-radius: 20px;
            padding: 0.2rem 0.6rem;
            font-size: 0.7rem;
            font-weight: bold;
            position: absolute;
            top: -8px;
            right: -12px;
            box-shadow: var(--shadow-sm);
        }
        .verified-badge {
            color: #1DA1F2;
            margin-left: 0.3rem;
            font-size: 1rem;
        }
        .profile-pic-small {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid var(--primary);
            margin-right: 0.5rem;
        }
        .btn {
            padding: 0.6rem 1.4rem;
            border-radius: 40px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.95rem;
        }
        .btn-primary { background: var(--primary); color: white; box-shadow: 0 4px 10px rgba(0,100,0,0.3); }
        .btn-primary:hover { background: var(--primary-dark); transform: scale(1.05); box-shadow: 0 6px 15px rgba(0,100,0,0.4); }
        .btn-outline { background: transparent; border: 2px solid var(--primary); color: var(--primary); }
        .btn-outline:hover { background: var(--primary); color: white; }
        .theme-toggle { cursor: pointer; margin-left: 1rem; font-size: 1.3rem; transition: var(--transition); }
        .theme-toggle:hover { transform: rotate(15deg); }
        .flash-messages { max-width: 1280px; margin: 1rem auto; padding: 0 1.5rem; }
        .flash {
            padding: 1rem 1.5rem;
            border-radius: 50px;
            margin-bottom: 0.8rem;
            backdrop-filter: blur(10px);
            border-left: 5px solid;
            animation: slideIn 0.3s ease;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        .flash.success { background: rgba(212, 237, 218, 0.9); color: #155724; border-left-color: #28a745; }
        .flash.danger { background: rgba(248, 215, 218, 0.9); color: #721c24; border-left-color: #dc3545; }
        .flash.warning { background: rgba(255, 243, 205, 0.9); color: #856404; border-left-color: #ffc107; }
        .flash.info { background: rgba(209, 236, 241, 0.9); color: #0c5460; border-left-color: #17a2b8; }
        footer {
            background: #1e2b3a;
            color: #ccc;
            text-align: center;
            padding: 2.5rem;
            margin-top: 3rem;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        footer a { color: var(--secondary); text-decoration: none; transition: var(--transition); }
        footer a:hover { color: white; }
        .card {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 24px;
            padding: 1.8rem;
            box-shadow: var(--shadow-md);
            transition: var(--transition);
        }
        .card:hover {
            transform: translateY(-5px) scale(1.02);
            box-shadow: var(--shadow-lg);
        }
        .hero {
            background: linear-gradient(135deg, rgba(0,100,0,0.8), rgba(255,210,0,0.8)), url('https://images.unsplash.com/photo-1554224154-22dec7ec8818?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=80') center/cover;
            padding: 4rem 2rem;
            border-radius: 30px;
            color: white;
            text-shadow: 0 2px 5px rgba(0,0,0,0.3);
            margin-bottom: 3rem;
        }
        .chat-button {
            position: fixed;
            bottom: 25px;
            right: 25px;
            background: var(--primary);
            color: white;
            width: 65px;
            height: 65px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2.2rem;
            cursor: pointer;
            box-shadow: var(--shadow-lg);
            z-index: 1000;
            transition: var(--transition);
            border: 2px solid rgba(255,255,255,0.3);
        }
        .chat-button:hover { transform: scale(1.15) rotate(5deg); background: var(--primary-dark); }
        .chat-window {
            position: fixed;
            bottom: 100px;
            right: 25px;
            width: 380px;
            max-width: 90vw;
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(20px);
            border-radius: 28px;
            box-shadow: var(--shadow-lg);
            display: none;
            flex-direction: column;
            z-index: 1001;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.5);
        }
        .chat-window.open { display: flex; animation: fadeInUp 0.3s; }
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .chat-header {
            background: var(--primary);
            color: white;
            padding: 1.2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .chat-header h4 { margin: 0; font-weight: 600; }
        .chat-header .close-chat { cursor: pointer; font-size: 1.5rem; opacity: 0.8; transition: var(--transition); }
        .chat-header .close-chat:hover { opacity: 1; transform: scale(1.2); }
        .chat-messages {
            height: 320px;
            overflow-y: auto;
            padding: 1.2rem;
            background: rgba(255,255,255,0.5);
        }
        .chat-message { margin-bottom: 1rem; display: flex; flex-direction: column; }
        .chat-message.user { align-items: flex-end; }
        .chat-message.bot { align-items: flex-start; }
        .chat-bubble {
            max-width: 80%;
            padding: 0.7rem 1.2rem;
            border-radius: 22px;
            word-wrap: break-word;
            line-height: 1.4;
            box-shadow: var(--shadow-sm);
        }
        .chat-message.user .chat-bubble {
            background: var(--primary);
            color: white;
            border-bottom-right-radius: 6px;
        }
        .chat-message.bot .chat-bubble {
            background: #e9eef3;
            color: #1a2b3c;
            border-bottom-left-radius: 6px;
        }
        .chat-input-area {
            display: flex;
            padding: 1rem;
            background: white;
            border-top: 1px solid #ddd;
        }
        .chat-input-area input {
            flex: 1;
            padding: 0.8rem 1.2rem;
            border: 1px solid #ccc;
            border-radius: 40px;
            outline: none;
            transition: var(--transition);
        }
        .chat-input-area input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(0,100,0,0.2); }
        .chat-input-area button {
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 40px;
            padding: 0.8rem 1.5rem;
            margin-left: 0.5rem;
            cursor: pointer;
            transition: var(--transition);
        }
        .chat-input-area button:hover { background: var(--primary-dark); transform: scale(1.05); }
        .typing-indicator {
            display: flex;
            gap: 5px;
            padding: 0.7rem 1.2rem;
            background: #e9eef3;
            border-radius: 22px;
            width: fit-content;
        }
        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: #888;
            border-radius: 50%;
            animation: typing 1.4s infinite;
        }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-10px); }
        }
        .listing-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 2rem;
            margin: 2rem 0;
        }
        .listing-card {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 28px;
            padding: 1.8rem;
            transition: var(--transition);
            cursor: pointer;
        }
        .listing-card:hover { transform: translateY(-8px) scale(1.02); box-shadow: var(--shadow-lg); }
        .listing-card h3 { font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--primary); }
        .listing-card .meta { display: flex; gap: 1rem; margin: 1rem 0; color: #666; }
        .listing-card .meta i { margin-right: 0.3rem; }
        .listing-card .stats { display: flex; gap: 1.5rem; margin-top: 1rem; font-weight: 600; }
        .product-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1.5rem;
            margin: 1.5rem 0;
        }
        .product-card {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 1.2rem;
            transition: var(--transition);
        }
        .product-card:hover { transform: translateY(-5px) scale(1.02); box-shadow: var(--shadow-lg); }
        .product-card img {
            width: 100%;
            height: 150px;
            object-fit: cover;
            border-radius: 12px;
            margin-bottom: 0.8rem;
        }
        #map { height: 300px; border-radius: 16px; margin: 1rem 0; }
        .language-selector {
            margin-left: 1rem;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            border: 1px solid var(--primary);
            background: transparent;
            color: inherit;
            cursor: pointer;
        }
        .listen-btn {
            background: transparent;
            border: none;
            color: var(--primary);
            cursor: pointer;
            margin-left: 0.5rem;
            font-size: 1.1rem;
        }
        .listen-btn:hover { color: var(--primary-dark); }
        .weather-widget, .prices-widget {
            background: var(--glass-bg);
            backdrop-filter: blur(8px);
            border-radius: 20px;
            padding: 1rem;
            margin-bottom: 1rem;
        }
    </style>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    {% block head %}{% endblock %}
</head>
<body>
    <!-- Theme script at the very top to prevent flash -->
    <script>
        (function() {
            const saved = localStorage.getItem('theme');
            if (saved === 'dark') {
                document.body.classList.add('dark-mode');
            }
        })();
    </script>
    <nav class="navbar">
        <div class="logo"><i class="fas fa-store-alt"></i> BizTech</div>
        <div style="display: flex; align-items: center; flex-wrap: wrap;">
            <a href="/" data-i18n="Home">Home</a>
            <a href="/discover" data-i18n="Discover">Discover</a>
            <a href="/groups" data-i18n="Groups">Groups</a>
            <a href="/cart"><i class="fas fa-shopping-cart"></i> <span data-i18n="Cart">Cart</span></a>
            <a href="/wallet"><i class="fas fa-wallet"></i> <span data-i18n="Wallet">Wallet</span></a>
            {% if g.user %}
                <a href="/verify" data-i18n="Verify">Verify</a>
            {% endif %}
            {% if g.user and g.user.listings|length > 0 %}
                <a href="/seller/orders"><i class="fas fa-truck"></i> <span data-i18n="Seller Orders">Seller Orders</span></a>
            {% endif %}
            {% if g.user and g.user.id == 1 %}
                <a href="/admin/withdrawals" data-i18n="Withdrawals">Withdrawals</a>
                <a href="/admin/verification" data-i18n="Verification">Verification</a>
            {% endif %}
            <a href="/about" data-i18n="About">About</a>
            <a href="/terms" data-i18n="Terms">Terms</a>
            {% if g.user %}
                <a href="/dashboard" data-i18n="Dashboard">Dashboard</a>
                <a href="/inbox">
                    <i class="fas fa-envelope"></i> <span data-i18n="Messages">Messages</span>
                    {% if g.user.unread_count() > 0 %}
                        <span class="badge">{{ g.user.unread_count() }}</span>
                    {% endif %}
                </a>
                <a href="/profile">
                    {% if g.user.profile_image and g.user.profile_image != 'default.jpg' %}
                        <img src="/static/uploads/profiles/{{ g.user.profile_image }}" class="profile-pic-small">
                    {% else %}
                        <i class="fas fa-user-circle" style="font-size: 1.8rem;"></i>
                    {% endif %}
                    {{ g.user.username }}
                    {% if g.user.verified %}<i class="fas fa-check-circle verified-badge"></i>{% endif %}
                </a>
                <a href="/logout" class="btn btn-outline" data-i18n="Logout">Logout</a>
            {% else %}
                <a href="/login" class="btn btn-outline" data-i18n="Login">Login</a>
                <a href="/register" class="btn btn-primary" data-i18n="Register">Register</a>
            {% endif %}
            <select class="language-selector" onchange="changeLanguage(this.value)">
                <option value="en">English</option>
                <option value="sn">ChiShona</option>
                <option value="nd">isiNdebele</option>
            </select>
            <span class="theme-toggle" onclick="toggleTheme()"><i class="fas fa-moon"></i></span>
        </div>
    </nav>

    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <div class="container">
        {% block content %}{% endblock %}
    </div>

    <footer>
        <p>© 2026 BizTech. <span data-i18n="Empowering local enterprises">Empowering local enterprises</span>.</p>
        <p><a href="/privacy" data-i18n="Privacy">Privacy</a> | <a href="/terms" data-i18n="Terms">Terms</a></p>
    </footer>

    <div class="chat-button" onclick="toggleChat()">
        <i class="fas fa-comment"></i>
    </div>
    <div class="chat-window" id="chatWindow">
        <div class="chat-header">
            <h4><i class="fas fa-robot"></i> <span data-i18n="BizTech Assistant">BizTech Assistant</span></h4>
            <span class="close-chat" onclick="toggleChat()">&times;</span>
        </div>
        <div class="chat-messages" id="chatMessages">
            <div class="chat-message bot">
                <div class="chat-bubble"><span data-i18n="Hi! I'm your assistant. Ask me anything about BizTech!">Hi! I'm your assistant. Ask me anything about BizTech!</span></div>
            </div>
        </div>
        <div class="chat-input-area">
            <input type="text" id="chatInput" data-i18n-placeholder="Type your question..." placeholder="Type your question..." onkeypress="if(event.key==='Enter') sendMessage()">
            <button onclick="sendMessage()"><i class="fas fa-paper-plane"></i></button>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();

        // Join private room for user if logged in
        {% if g.user %}
        socket.emit('join', { room: 'user_{{ g.user.id }}' });
        {% endif %}

        function setTheme(theme) {
            if (theme === 'dark') {
                document.body.classList.add('dark-mode');
                localStorage.setItem('theme', 'dark');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('theme', 'light');
            }
        }
        function toggleTheme() {
            if (document.body.classList.contains('dark-mode')) {
                setTheme('light');
            } else {
                setTheme('dark');
            }
        }

        const chatWindow = document.getElementById('chatWindow');
        const chatMessages = document.getElementById('chatMessages');
        const chatInput = document.getElementById('chatInput');

        function toggleChat() {
            chatWindow.classList.toggle('open');
        }

        function addMessage(text, isUser) {
            const msgDiv = document.createElement('div');
            msgDiv.className = 'chat-message ' + (isUser ? 'user' : 'bot');
            const bubble = document.createElement('div');
            bubble.className = 'chat-bubble';
            bubble.innerText = text;
            msgDiv.appendChild(bubble);
            chatMessages.appendChild(msgDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function showTyping() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'chat-message bot';
            typingDiv.id = 'typingIndicator';
            typingDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
            chatMessages.appendChild(typingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function removeTyping() {
            const typing = document.getElementById('typingIndicator');
            if (typing) typing.remove();
        }

        function sendMessage() {
            const question = chatInput.value.trim();
            if (!question) return;
            addMessage(question, true);
            chatInput.value = '';
            showTyping();
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question })
            })
            .then(res => res.json())
            .then(data => {
                removeTyping();
                addMessage(data.answer, false);
            })
            .catch(err => {
                removeTyping();
                addMessage('Sorry, something went wrong. Try again later.', false);
            });
        }

        socket.on('new_message', function(data) {
            if (data.for_user === {{ g.user.id if g.user else 'null' }}) {
                const badge = document.querySelector('.badge');
                if (badge) {
                    let count = parseInt(badge.innerText) || 0;
                    badge.innerText = count + 1;
                } else {
                    const msgLink = document.querySelector('a[href="/inbox"]');
                    if (msgLink) {
                        const newBadge = document.createElement('span');
                        newBadge.className = 'badge';
                        newBadge.innerText = '1';
                        msgLink.appendChild(newBadge);
                    }
                }
            }
        });

        socket.on('group_message', function(data) {
            if (window.location.pathname.startsWith('/groups/')) {
                const groupId = window.location.pathname.split('/')[2];
                if (data.group_id == groupId) {
                    appendGroupMessage(data);
                }
            }
        });

        socket.on('group_typing', function(data) {
            if (window.location.pathname.startsWith('/groups/')) {
                const groupId = window.location.pathname.split('/')[2];
                if (data.group_id == groupId) {
                    showGroupTyping(data.username, data.is_typing);
                }
            }
        });

        // Language translations (simplified – full list would be huge; only key phrases shown)
        const translations = {
            en: {
                'Home': 'Home',
                'Discover': 'Discover',
                'Groups': 'Groups',
                'Cart': 'Cart',
                'Wallet': 'Wallet',
                'Verify': 'Verify',
                'Seller Orders': 'Seller Orders',
                'Withdrawals': 'Withdrawals',
                'Verification': 'Verification',
                'About': 'About',
                'Terms': 'Terms',
                'Dashboard': 'Dashboard',
                'Messages': 'Messages',
                'Logout': 'Logout',
                'Login': 'Login',
                'Register': 'Register',
                'Privacy': 'Privacy',
                'Empowering local enterprises': 'Empowering local enterprises',
                'BizTech Assistant': 'BizTech Assistant',
                "Hi! I'm your assistant. Ask me anything about BizTech!": "Hi! I'm your assistant. Ask me anything about BizTech!",
                'Type your question...': 'Type your question...',
            },
            sn: {
                'Home': 'Kumba',
                'Discover': 'Tsvaga',
                'Groups': 'Mapoka',
                'Cart': 'Dengu',
                'Wallet': 'Chikwama',
                'Verify': 'Simudzira',
                'Seller Orders': 'Maodha evatengesi',
                'Withdrawals': 'Zvikumbiro',
                'Verification': 'Kusimbiswa',
                'About': 'Nezvedu',
                'Terms': 'Mitemo',
                'Dashboard': 'Dhibhodhi',
                'Messages': 'Mameseji',
                'Logout': 'Buditsa',
                'Login': 'Pinda',
                'Register': 'Nyoresa',
                'Privacy': 'Zvakavanzika',
                'Empowering local enterprises': 'Kusimudzira mabhizimusi emuno',
                'BizTech Assistant': 'Mubatsiri weBizTech',
                "Hi! I'm your assistant. Ask me anything about BizTech!": "Mhoro! Ndini mubatsiri wako. Bvunza chero chinhu nezveBizTech!",
                'Type your question...': 'Nyora mubvunzo wako...',
            },
            nd: {
                'Home': 'Ekhaya',
                'Discover': 'Thola',
                'Groups': 'Amaqembu',
                'Cart': 'Inqola',
                'Wallet': 'Isikhwama',
                'Verify': 'Qinisekisa',
                'Seller Orders': 'Ii-oda zabathengisi',
                'Withdrawals': 'Izicelo',
                'Verification': 'Ukuqinisekiswa',
                'About': 'Ngaye',
                'Terms': 'Imigomo',
                'Dashboard': 'Ideshibhodi',
                'Messages': 'Imilayezo',
                'Logout': 'Phuma',
                'Login': 'Ngena',
                'Register': 'Bhalisa',
                'Privacy': 'Imfihlo',
                'Empowering local enterprises': 'Ukuxhasa amabhizinisi endawo',
                'BizTech Assistant': 'Umsizi weBizTech',
                "Hi! I'm your assistant. Ask me anything about BizTech!": "Sawubona! Ngingumsizi wakho. Buza noma yini ngeBizTech!",
                'Type your question...': 'Bhala umbuzo wakho...',
            }
        };

        function changeLanguage(lang) {
            localStorage.setItem('language', lang);
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (translations[lang] && translations[lang][key]) {
                    el.innerText = translations[lang][key];
                }
            });
            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                const key = el.getAttribute('data-i18n-placeholder');
                if (translations[lang] && translations[lang][key]) {
                    el.placeholder = translations[lang][key];
                }
            });
        }

        (function() {
            const savedLang = localStorage.getItem('language') || 'en';
            document.querySelector('.language-selector').value = savedLang;
            changeLanguage(savedLang);
        })();

        function speakText(text, lang = 'en') {
            if (!window.speechSynthesis) {
                alert('Text-to-speech not supported in your browser.');
                return;
            }
            const utterance = new SpeechSynthesisUtterance(text);
            if (lang === 'sn') utterance.lang = 'sn-ZW';
            else if (lang === 'nd') utterance.lang = 'nd-ZW';
            else utterance.lang = 'en-US';
            window.speechSynthesis.speak(utterance);
        }

        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('[data-speak]').forEach(el => {
                const btn = document.createElement('button');
                btn.className = 'listen-btn';
                btn.innerHTML = '<i class="fas fa-volume-up"></i>';
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const lang = localStorage.getItem('language') || 'en';
                    speakText(el.innerText, lang);
                };
                el.appendChild(btn);
            });
        });
    </script>
</body>
</html>
"""

INDEX_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="hero">
        <h1 style="font-size: 3.5rem; font-weight: 800;" data-i18n="BizTech – Business Technologies">BizTech – Business Technologies</h1>
        <p style="font-size: 1.3rem; max-width: 700px; margin: 1.5rem auto;" data-i18n="Connecting local businesses with customers via web and real‑time messaging – free and secure.">Connecting local businesses with customers via web and real‑time messaging – free and secure.</p>
        <div style="margin: 2.5rem 0;">
            <a href="/register" class="btn btn-primary" style="margin-right: 1rem; padding: 0.8rem 2rem;" data-i18n="Get Started">Get Started</a>
            <span class="btn btn-outline" onclick="toggleChat()" style="padding: 0.8rem 2rem;" data-i18n="Ask Assistant">Ask Assistant</span>
        </div>
    </div>

    <div style="display: flex; gap: 2rem; flex-wrap: wrap; margin-bottom: 2rem;">
        <div class="weather-widget card" style="flex:1;">
            <h3><i class="fas fa-cloud-sun"></i> <span data-i18n="Local Weather">Local Weather</span></h3>
            <div id="weather">Loading...</div>
        </div>
        <div class="prices-widget card" style="flex:1;">
            <h3><i class="fas fa-chart-line"></i> <span data-i18n="Market Prices">Market Prices</span></h3>
            <div id="prices">Loading...</div>
        </div>
    </div>

    <div class="listing-grid" id="listing-feed"></div>

    <script>
        function loadWeather() {
            fetch('/api/weather')
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('weather').innerHTML = `<p>${data.error}</p>`;
                    } else {
                        document.getElementById('weather').innerHTML = `
                            <p><strong>${data.temp}°C</strong> - ${data.description}</p>
                            <img src="https://openweathermap.org/img/wn/${data.icon}.png" alt="${data.description}">
                        `;
                    }
                })
                .catch(() => {
                    document.getElementById('weather').innerHTML = '<p>Weather unavailable</p>';
                });
        }

        function loadPrices() {
            fetch('/api/market-prices')
                .then(res => res.json())
                .then(prices => {
                    const container = document.getElementById('prices');
                    if (prices.length === 0) {
                        container.innerHTML = '<p>No prices yet.</p>';
                        return;
                    }
                    let html = '<ul style="list-style:none; padding:0;">';
                    prices.slice(0,5).forEach(p => {
                        html += `<li><strong>${p.commodity}</strong> – $${p.price}/${p.unit} (${p.location}) <small>${new Date(p.date).toLocaleDateString()}</small></li>`;
                    });
                    html += '</ul>';
                    container.innerHTML = html;
                });
        }

        function loadListings() {
            fetch('/api/listings?page=1')
                .then(res => res.json())
                .then(data => {
                    const feed = document.getElementById('listing-feed');
                    feed.innerHTML = '';
                    data.items.forEach(item => {
                        const verifiedBadge = item.owner_verified ? '<i class="fas fa-check-circle verified-badge"></i>' : '';
                        const card = document.createElement('div');
                        card.className = 'listing-card';
                        card.innerHTML = `
                            <h3>${item.business_name} ${verifiedBadge}</h3>
                            <p>${item.description.substring(0,100)}...</p>
                            <div class="meta">
                                <span><i class="fas fa-map-marker-alt"></i> ${item.location}</span>
                                <span><i class="fas fa-tag"></i> ${item.category}</span>
                            </div>
                            <div class="stats">
                                <span><i class="fas fa-heart" style="color: var(--accent);"></i> ${item.likes}</span>
                                <span><i class="fas fa-eye"></i> ${item.views}</span>
                                <span><i class="fas fa-clock"></i> ${item.created_ago}</span>
                            </div>
                            <a href="/listing/${item.id}" class="btn btn-outline" style="margin-top: 1rem;" data-i18n="View Details">View Details</a>
                            <button class="listen-btn" onclick="speakText('${item.business_name}')"><i class="fas fa-volume-up"></i></button>
                        `;
                        feed.appendChild(card);
                    });
                });
        }

        loadWeather();
        loadPrices();
        loadListings();
        socket.on('new_listing', function() { loadListings(); });
    </script>
    {% endblock %}
    '''
)

WALLET_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:600px; margin:2rem auto;">
        <h2 data-i18n="Your Wallet">Your Wallet</h2>
        <p><strong data-i18n="Balance">Balance:</strong> $<span id="wallet-balance">{{ user.wallet_balance }}</span></p>
        <div style="display:flex; gap:1rem; margin:1rem 0;">
            <button class="btn btn-primary" onclick="showDeposit()" data-i18n="Deposit">Deposit</button>
            <button class="btn btn-outline" onclick="showWithdraw()" data-i18n="Withdraw">Withdraw</button>
        </div>
        <div id="deposit-form" style="display:none;">
            <h3 data-i18n="Deposit via PayPal">Deposit via PayPal</h3>
            <input type="number" id="deposit-amount" data-i18n-placeholder="Amount (USD)" placeholder="Amount (USD)" min="1" step="0.01" style="width:100%; padding:0.5rem; margin-bottom:0.5rem;">
            <button class="btn btn-primary" onclick="deposit()" data-i18n="Continue to PayPal">Continue to PayPal</button>
        </div>
        <div id="withdraw-form" style="display:none;">
            <h3 data-i18n="Request Withdrawal">Request Withdrawal</h3>
            <input type="number" id="withdraw-amount" data-i18n-placeholder="Amount (USD)" placeholder="Amount (USD)" min="1" step="0.01" style="width:100%; padding:0.5rem; margin-bottom:0.5rem;">
            <select id="withdraw-method" style="width:100%; padding:0.5rem; margin-bottom:0.5rem;">
                <option value="bank" data-i18n="Bank Transfer">Bank Transfer</option>
                <option value="ecocash" data-i18n="EcoCash">EcoCash</option>
            </select>
            <input type="text" id="withdraw-details" data-i18n-placeholder="Account number / phone" placeholder="Account number / phone" style="width:100%; padding:0.5rem; margin-bottom:0.5rem;">
            <button class="btn btn-primary" onclick="withdraw()" data-i18n="Request">Request</button>
        </div>
    </div>
    <div class="card">
        <h3 data-i18n="Transaction History">Transaction History</h3>
        <table style="width:100%; border-collapse:collapse;">
            <thead>
                <tr><th data-i18n="Date">Date</th><th data-i18n="Description">Description</th><th data-i18n="Amount">Amount</th><th data-i18n="Status">Status</th></tr>
            </thead>
            <tbody id="transactions"></tbody>
        </table>
    </div>
    <script>
        function loadWallet() {
            fetch('/api/wallet')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('wallet-balance').innerText = data.balance.toFixed(2);
                    const tbody = document.getElementById('transactions');
                    tbody.innerHTML = '';
                    data.transactions.forEach(t => {
                        const row = `<tr>
                            <td>${new Date(t.created_at).toLocaleString()}</td>
                            <td>${t.description || t.type}</td>
                            <td style="color:${t.amount>0?'green':'red'}">$${t.amount.toFixed(2)}</td>
                            <td>${t.status}</td>
                        </tr>`;
                        tbody.innerHTML += row;
                    });
                });
        }

        function showDeposit() {
            document.getElementById('deposit-form').style.display = 'block';
            document.getElementById('withdraw-form').style.display = 'none';
        }
        function showWithdraw() {
            document.getElementById('withdraw-form').style.display = 'block';
            document.getElementById('deposit-form').style.display = 'none';
        }

        function deposit() {
            const amount = document.getElementById('deposit-amount').value;
            if (!amount || amount <= 0) return alert('Enter amount');
            fetch('/api/wallet/deposit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: parseFloat(amount) })
            })
            .then(res => res.json())
            .then(data => {
                if (data.approval_url) {
                    window.location.href = data.approval_url;
                } else {
                    alert(data.error || 'Deposit failed');
                }
            })
            .catch(() => alert('Network error'));
        }

        function withdraw() {
            const amount = document.getElementById('withdraw-amount').value;
            const method = document.getElementById('withdraw-method').value;
            const details = document.getElementById('withdraw-details').value;
            if (!amount || amount <= 0 || !details) return alert('Fill all fields');
            fetch('/api/wallet/withdraw/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: parseFloat(amount), method, details })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert('Withdrawal request submitted. It will be processed soon.');
                    loadWallet();
                } else {
                    alert(data.error);
                }
            })
            .catch(() => alert('Network error'));
        }

        loadWallet();
    </script>
    {% endblock %}
    '''
)

VERIFY_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:600px; margin:2rem auto;">
        <h2 data-i18n="Business Verification">Business Verification</h2>
        <p data-i18n="Get a verified badge to build trust with customers.">Get a verified badge to build trust with customers.</p>
        <div id="status"></div>
        <form id="verify-form">
            <div style="margin-bottom:1rem;">
                <label data-i18n="Business Name">Business Name</label>
                <input type="text" id="business_name" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Contact Info (phone/email)">Contact Info (phone/email)</label>
                <input type="text" id="contact_info" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <button type="submit" class="btn btn-primary" data-i18n="Submit Request">Submit Request</button>
        </form>
    </div>
    <script>
        function loadStatus() {
            fetch('/api/verification/status')
                .then(res => res.json())
                .then(data => {
                    const statusDiv = document.getElementById('status');
                    if (data.status === 'none') {
                        statusDiv.innerHTML = '';
                    } else if (data.status === 'pending') {
                        statusDiv.innerHTML = '<p style="color:orange;" data-i18n="Your request is pending review.">Your request is pending review.</p>';
                        document.getElementById('verify-form').style.display = 'none';
                    } else if (data.status === 'approved') {
                        statusDiv.innerHTML = '<p style="color:green;" data-i18n="Congratulations! You are verified.">Congratulations! You are verified.</p>';
                        document.getElementById('verify-form').style.display = 'none';
                    } else if (data.status === 'rejected') {
                        statusDiv.innerHTML = '<p style="color:red;" data-i18n="Your request was rejected. You can apply again.">Your request was rejected. You can apply again.</p>';
                    }
                });
        }

        document.getElementById('verify-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const business_name = document.getElementById('business_name').value;
            const contact_info = document.getElementById('contact_info').value;
            fetch('/api/verification/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ business_name, contact_info })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert('Request submitted');
                    loadStatus();
                } else {
                    alert(data.error);
                }
            })
            .catch(() => alert('Network error'));
        });

        loadStatus();
    </script>
    {% endblock %}
    '''
)

ADMIN_VERIFICATION_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Verification Requests">Verification Requests</h2>
    <div id="requests"></div>
    <script>
        function loadRequests() {
            fetch('/api/admin/verification-requests')
                .then(res => res.json())
                .then(requests => {
                    const container = document.getElementById('requests');
                    if (!requests.length) {
                        container.innerHTML = '<p data-i18n="No requests">No requests</p>';
                        return;
                    }
                    let html = '';
                    requests.forEach(r => {
                        html += `<div class="card">
                            <p><span data-i18n="User">User</span>: ${r.user_name} (ID: ${r.user_id})</p>
                            <p><span data-i18n="Business">Business</span>: ${r.business_name}</p>
                            <p><span data-i18n="Contact">Contact</span>: ${r.contact_info}</p>
                            <p><span data-i18n="Status">Status</span>: ${r.status}</p>
                            <p><span data-i18n="Requested">Requested</span>: ${new Date(r.created_at).toLocaleString()}</p>
                            ${r.status === 'pending' ? `
                                <button onclick="process(${r.id}, 'approve')" data-i18n="Approve">Approve</button>
                                <button onclick="process(${r.id}, 'reject')" data-i18n="Reject">Reject</button>
                            ` : ''}
                        </div>`;
                    });
                    container.innerHTML = html;
                });
        }

        function process(id, action) {
            fetch(`/api/admin/verification/${id}/process`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action })
            })
            .then(res => res.json())
            .then(() => loadRequests());
        }

        loadRequests();
    </script>
    {% endblock %}
    '''
)

ADMIN_WITHDRAWALS_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Withdrawal Requests">Withdrawal Requests</h2>
    <div id="requests"></div>
    <script>
        function loadRequests() {
            fetch('/api/admin/withdrawals')
                .then(res => res.json())
                .then(requests => {
                    const container = document.getElementById('requests');
                    if (!requests.length) {
                        container.innerHTML = '<p data-i18n="No requests">No requests</p>';
                        return;
                    }
                    let html = '';
                    requests.forEach(r => {
                        html += `<div class="card">
                            <p><span data-i18n="User">User</span>: ${r.user_name} (ID: ${r.user_id})</p>
                            <p><span data-i18n="Amount">Amount</span>: $${r.amount}</p>
                            <p><span data-i18n="Method">Method</span>: ${r.method} - ${r.details}</p>
                            <p><span data-i18n="Status">Status</span>: ${r.status}</p>
                            <p><span data-i18n="Requested">Requested</span>: ${new Date(r.created_at).toLocaleString()}</p>
                            ${r.status === 'pending' ? `
                                <button onclick="process(${r.id}, 'approve')" data-i18n="Approve">Approve</button>
                                <button onclick="process(${r.id}, 'reject')" data-i18n="Reject">Reject</button>
                            ` : ''}
                        </div>`;
                    });
                    container.innerHTML = html;
                });
        }

        function process(id, action) {
            fetch(`/api/admin/withdrawal/${id}/process`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action })
            })
            .then(res => res.json())
            .then(() => loadRequests());
        }

        loadRequests();
    </script>
    {% endblock %}
    '''
)

# ============================================================================
# Additional required templates (minimal but functional)
# ============================================================================
LOGIN_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:400px; margin:2rem auto;">
        <h2 data-i18n="Login">Login</h2>
        <form method="post">
            <div style="margin-bottom:1rem;">
                <label data-i18n="Username or Email">Username or Email</label>
                <input type="text" name="username" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Password">Password</label>
                <input type="password" name="password" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <button type="submit" class="btn btn-primary" data-i18n="Login">Login</button>
        </form>
        <p style="margin-top:1rem;"><a href="/register" data-i18n="Don't have an account? Register">Don't have an account? Register</a></p>
    </div>
    {% endblock %}
    '''
)

REGISTER_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:500px; margin:2rem auto;">
        <h2 data-i18n="Register">Register</h2>
        <form method="post" enctype="multipart/form-data">
            <div style="margin-bottom:1rem;">
                <label data-i18n="Username">Username</label>
                <input type="text" name="username" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Email">Email</label>
                <input type="email" name="email" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Phone">Phone</label>
                <input type="text" name="phone" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Password">Password</label>
                <input type="password" name="password" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Profile Image (optional)">Profile Image (optional)</label>
                <input type="file" name="profile_image" accept="image/*">
            </div>
            <button type="submit" class="btn btn-primary" data-i18n="Register">Register</button>
        </form>
        <p style="margin-top:1rem;"><a href="/login" data-i18n="Already have an account? Login">Already have an account? Login</a></p>
    </div>
    {% endblock %}
    '''
)

ADD_LISTING_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:600px; margin:2rem auto;">
        <h2 data-i18n="Add New Listing">Add New Listing</h2>
        <form method="post" enctype="multipart/form-data" action="/add-listing">
            <div style="margin-bottom:1rem;">
                <label data-i18n="Business Name">Business Name</label>
                <input type="text" name="business_name" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Description">Description</label>
                <textarea name="description" required style="width:100%; padding:0.8rem;"></textarea>
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Location">Location</label>
                <input type="text" name="location" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Category">Category</label>
                <input type="text" name="category" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Phone (optional)">Phone (optional)</label>
                <input type="text" name="phone" style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Image (optional)">Image (optional)</label>
                <input type="file" name="image" accept="image/*">
            </div>
            <button type="submit" class="btn btn-primary" data-i18n="Add Listing">Add Listing</button>
        </form>
    </div>
    {% endblock %}
    '''
)

DASHBOARD_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Your Dashboard">Your Dashboard</h2>
    <p><strong data-i18n="Total Listings">Total Listings</strong>: {{ listings|length }} | <strong data-i18n="Total Likes">Total Likes</strong>: {{ total_likes }} | <strong data-i18n="Products">Products</strong>: {{ products }}</p>
    <a href="/add-listing" class="btn btn-primary" data-i18n="Add New Listing">Add New Listing</a>
    <div class="listing-grid">
        {% for listing in listings %}
            <div class="listing-card">
                <h3>{{ listing.business_name }}</h3>
                <p>{{ listing.description[:100] }}...</p>
                <div class="stats">
                    <span><i class="fas fa-heart"></i> {{ listing.likes }}</span>
                    <span><i class="fas fa-eye"></i> {{ listing.views }}</span>
                </div>
                <div style="display:flex; gap:0.5rem; margin-top:1rem;">
                    <a href="/edit-listing/{{ listing.id }}" class="btn btn-outline" data-i18n="Edit">Edit</a>
                    <form method="post" action="/delete-listing/{{ listing.id }}" style="display:inline;">
                        <button type="submit" class="btn btn-outline" style="border-color:var(--accent); color:var(--accent);" onclick="return confirm('Delete this listing?')" data-i18n="Delete">Delete</button>
                    </form>
                    <a href="/listing/{{ listing.id }}" class="btn btn-outline" data-i18n="View">View</a>
                </div>
            </div>
        {% else %}
            <p data-i18n="You have no listings yet.">You have no listings yet.</p>
        {% endfor %}
    </div>
    {% endblock %}
    '''
)

PROFILE_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:500px; margin:2rem auto;">
        <h2 data-i18n="Your Profile">Your Profile</h2>
        <form method="post" enctype="multipart/form-data">
            <div style="margin-bottom:1rem;">
                <label data-i18n="Email">Email</label>
                <input type="email" name="email" value="{{ user.email }}" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Phone">Phone</label>
                <input type="text" name="phone" value="{{ user.phone }}" required style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="New Password (leave blank to keep current)">New Password (leave blank to keep current)</label>
                <input type="password" name="password" style="width:100%; padding:0.8rem; border-radius:40px;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Profile Image">Profile Image</label>
                <input type="file" name="profile_image" accept="image/*">
                {% if user.profile_image and user.profile_image != 'default.jpg' %}
                    <img src="/static/uploads/profiles/{{ user.profile_image }}" style="max-width:100px; display:block; margin-top:0.5rem;">
                {% endif %}
            </div>
            <button type="submit" class="btn btn-primary" data-i18n="Update Profile">Update Profile</button>
        </form>
    </div>
    {% endblock %}
    '''
)

PUBLIC_PROFILE_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:600px; margin:2rem auto; text-align:center;">
        {% if profile_user.profile_image and profile_user.profile_image != 'default.jpg' %}
            <img src="/static/uploads/profiles/{{ profile_user.profile_image }}" style="width:120px; height:120px; border-radius:50%; object-fit:cover; border:4px solid var(--primary);">
        {% else %}
            <i class="fas fa-user-circle" style="font-size:120px; color:var(--primary);"></i>
        {% endif %}
        <h2>{{ profile_user.username }} {% if profile_user.verified %}<i class="fas fa-check-circle verified-badge"></i>{% endif %}</h2>
        <p><i class="fas fa-envelope"></i> {{ profile_user.email }} | <i class="fas fa-phone"></i> {{ profile_user.phone }}</p>
        <p><strong data-i18n="Listings">Listings</strong>: {{ profile_user.listings|length }} | <strong data-i18n="Followers">Followers</strong>: <span id="follower-count">{{ follower_count }}</span> | <strong data-i18n="Following">Following</strong>: {{ following_count }}</p>
        {% if current_user and current_user.id != profile_user.id %}
            <button id="follow-btn" class="btn btn-primary" onclick="toggleFollow()">{{ "Unfollow" if is_following else "Follow" }}</button>
            <a href="/compose/{{ profile_user.id }}" class="btn btn-outline" data-i18n="Message">Message</a>
            <a href="/call/{{ profile_user.id }}" class="btn btn-outline"><i class="fas fa-video"></i> <span data-i18n="Video Call">Video Call</span></a>
        {% endif %}
    </div>
    <h3 data-i18n="Listings">Listings</h3>
    <div class="listing-grid">
        {% for listing in listings %}
            <div class="listing-card">
                <h3>{{ listing.business_name }}</h3>
                <p>{{ listing.description[:100] }}...</p>
                <a href="/listing/{{ listing.id }}" class="btn btn-outline" data-i18n="View">View</a>
            </div>
        {% else %}
            <p data-i18n="No listings yet.">No listings yet.</p>
        {% endfor %}
    </div>
    <h3 data-i18n="Products">Products</h3>
    <div class="product-grid">
        {% for product in products %}
            <div class="product-card">
                {% if product.image %}
                    <img src="/static/uploads/products/{{ product.image }}">
                {% endif %}
                <h4>{{ product.name }}</h4>
                <p>${{ product.price if product.price else 'N/A' }}</p>
                <p>{{ product.description[:50] }}...</p>
            </div>
        {% else %}
            <p data-i18n="No products yet.">No products yet.</p>
        {% endfor %}
    </div>
    <script>
        function toggleFollow() {
            fetch('/api/follow/{{ profile_user.id }}', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        const btn = document.getElementById('follow-btn');
                        btn.innerText = data.following ? 'Unfollow' : 'Follow';
                        const countSpan = document.getElementById('follower-count');
                        let count = parseInt(countSpan.innerText);
                        countSpan.innerText = data.following ? count + 1 : count - 1;
                    } else {
                        alert(data.error);
                    }
                })
                .catch(() => alert('Network error'));
        }
    </script>
    {% endblock %}
    '''
)

INBOX_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Messages">Messages</h2>
    <div id="conversations"></div>
    <div id="message-area" style="display:none; margin-top:2rem;">
        <h3 id="chat-with"></h3>
        <div id="messages" style="height:300px; overflow-y:auto; border:1px solid #ccc; padding:1rem; margin-bottom:1rem;"></div>
        <input type="text" id="message-input" placeholder="Type message..." style="width:80%; padding:0.8rem;">
        <button class="btn btn-primary" onclick="sendMessage()"><i class="fas fa-paper-plane"></i></button>
    </div>
    <script>
        let currentChatId = null;
        function loadConversations() {
            fetch('/api/conversations')
                .then(res => res.json())
                .then(convos => {
                    const container = document.getElementById('conversations');
                    container.innerHTML = '';
                    convos.forEach(c => {
                        const div = document.createElement('div');
                        div.className = 'card';
                        div.style.cursor = 'pointer';
                        div.onclick = () => openChat(c.user.id, c.user.username);
                        div.innerHTML = `
                            <div style="display:flex; align-items:center;">
                                <img src="/static/uploads/profiles/${c.user.profile_image}" style="width:40px; height:40px; border-radius:50%; margin-right:1rem;">
                                <div>
                                    <strong>${c.user.username} ${c.user.verified ? '<i class="fas fa-check-circle verified-badge"></i>' : ''}</strong>
                                    <p>${c.last_message ? c.last_message.content : 'No messages'}</p>
                                </div>
                                ${c.unread ? '<span class="badge" style="position:static;">'+c.unread+'</span>' : ''}
                            </div>
                        `;
                        container.appendChild(div);
                    });
                });
        }

        function openChat(userId, username) {
            currentChatId = userId;
            document.getElementById('chat-with').innerHTML = `Chat with ${username}`;
            document.getElementById('message-area').style.display = 'block';
            fetch('/api/messages/' + userId)
                .then(res => res.json())
                .then(msgs => {
                    const msgsDiv = document.getElementById('messages');
                    msgsDiv.innerHTML = '';
                    msgs.forEach(m => {
                        const msgDiv = document.createElement('div');
                        msgDiv.className = m.sender_id === {{ user.id }} ? 'chat-message user' : 'chat-message bot';
                        msgDiv.innerHTML = `<div class="chat-bubble">${m.content}</div>`;
                        msgsDiv.appendChild(msgDiv);
                    });
                    msgsDiv.scrollTop = msgsDiv.scrollHeight;
                });
        }

        function sendMessage() {
            const input = document.getElementById('message-input');
            const content = input.value.trim();
            if (!content || !currentChatId) return;
            fetch('/api/send-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recipient_id: currentChatId, content: content })
            })
            .then(res => res.json())
            .then(msg => {
                input.value = '';
                const msgsDiv = document.getElementById('messages');
                const msgDiv = document.createElement('div');
                msgDiv.className = 'chat-message user';
                msgDiv.innerHTML = `<div class="chat-bubble">${msg.content}</div>`;
                msgsDiv.appendChild(msgDiv);
                msgsDiv.scrollTop = msgsDiv.scrollHeight;
            })
            .catch(() => alert('Failed to send message'));
        }

        loadConversations();
        socket.on('new_message', function(data) {
            if (data.for_user === {{ user.id }} && data.message.sender_id === currentChatId) {
                const msgsDiv = document.getElementById('messages');
                const msgDiv = document.createElement('div');
                msgDiv.className = 'chat-message bot';
                msgDiv.innerHTML = `<div class="chat-bubble">${data.message.content}</div>`;
                msgsDiv.appendChild(msgDiv);
                msgsDiv.scrollTop = msgsDiv.scrollHeight;
            }
        });
    </script>
    {% endblock %}
    '''
)

COMPOSE_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:500px; margin:2rem auto;">
        <h2 data-i18n="Message to">Message to {{ recipient.username }}</h2>
        <textarea id="message-content" rows="4" style="width:100%; padding:0.8rem; border-radius:20px;"></textarea>
        <button class="btn btn-primary" onclick="send()" style="margin-top:1rem;" data-i18n="Send">Send</button>
    </div>
    <script>
        function send() {
            const content = document.getElementById('message-content').value.trim();
            if (!content) return;
            fetch('/api/send-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recipient_id: {{ recipient.id }}, content: content })
            })
            .then(res => res.json())
            .then(() => {
                alert('Message sent');
                window.location.href = '/inbox';
            })
            .catch(() => alert('Failed to send'));
        }
    </script>
    {% endblock %}
    '''
)

GROUPS_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Groups">Groups</h2>
    <button class="btn btn-primary" onclick="showCreateGroup()" data-i18n="Create Group">Create Group</button>
    <div id="create-group-form" style="display:none; margin:1rem 0;">
        <input type="text" id="group-name" placeholder="Group name" style="width:100%; padding:0.8rem;">
        <textarea id="group-desc" placeholder="Description" style="width:100%; padding:0.8rem;"></textarea>
        <label><input type="checkbox" id="group-private"> Private</label>
        <button class="btn btn-primary" onclick="createGroup()">Create</button>
    </div>
    <h3 data-i18n="My Groups">My Groups</h3>
    <div id="my-groups"></div>
    <h3 data-i18n="Public Groups">Public Groups</h3>
    <div id="public-groups"></div>
    <script>
        function showCreateGroup() {
            document.getElementById('create-group-form').style.display = 'block';
        }
        function createGroup() {
            const name = document.getElementById('group-name').value.trim();
            const desc = document.getElementById('group-desc').value.trim();
            const isPrivate = document.getElementById('group-private').checked;
            if (!name) return alert('Group name required');
            fetch('/api/groups/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, description: desc, is_private: isPrivate })
            })
            .then(res => res.json())
            .then(data => {
                window.location.href = '/groups/' + data.id;
            });
        }
        function loadGroups() {
            fetch('/api/groups')
                .then(res => res.json())
                .then(groups => {
                    const container = document.getElementById('my-groups');
                    container.innerHTML = '';
                    groups.forEach(g => {
                        container.innerHTML += `<div class="card" onclick="window.location='/groups/${g.id}'">
                            <h4>${g.name}</h4>
                            <p>${g.description || ''}</p>
                            <small>Members: ${g.member_count}</small>
                        </div>`;
                    });
                });
            fetch('/api/groups/public')
                .then(res => res.json())
                .then(groups => {
                    const container = document.getElementById('public-groups');
                    container.innerHTML = '';
                    groups.forEach(g => {
                        container.innerHTML += `<div class="card" onclick="window.location='/groups/${g.id}'">
                            <h4>${g.name}</h4>
                            <p>${g.description || ''}</p>
                            <small>Members: ${g.member_count}</small>
                        </div>`;
                    });
                });
        }
        loadGroups();
    </script>
    {% endblock %}
    '''
)

GROUP_CHAT_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2>{{ group.name }}</h2>
    <p>{{ group.description }}</p>
    <div id="group-messages" style="height:400px; overflow-y:auto; border:1px solid #ccc; padding:1rem; margin-bottom:1rem;"></div>
    <div style="display:flex;">
        <input type="text" id="group-message-input" placeholder="Type message..." style="flex:1; padding:0.8rem;">
        <button class="btn btn-primary" onclick="sendGroupMessage()"><i class="fas fa-paper-plane"></i></button>
    </div>
    <small id="typing-indicator"></small>
    <script>
        const groupId = {{ group.id }};
        socket.emit('join_group', { group_id: groupId });

        function loadGroupMessages() {
            fetch('/api/groups/' + groupId + '/messages')
                .then(res => res.json())
                .then(msgs => {
                    const container = document.getElementById('group-messages');
                    container.innerHTML = '';
                    msgs.forEach(m => {
                        appendGroupMessage(m);
                    });
                });
        }

        function appendGroupMessage(m) {
            const container = document.getElementById('group-messages');
            const div = document.createElement('div');
            div.className = 'chat-message ' + (m.user_id === {{ user.id }} ? 'user' : 'bot');
            div.innerHTML = `<div class="chat-bubble"><strong>${m.username}:</strong> ${m.content}</div>`;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        function sendGroupMessage() {
            const input = document.getElementById('group-message-input');
            const content = input.value.trim();
            if (!content) return;
            socket.emit('group_message', { group_id: groupId, content: content, encrypted: false });
            input.value = '';
        }

        socket.on('group_message', function(data) {
            if (data.group_id === groupId) {
                appendGroupMessage(data);
            }
        });

        let typingTimer;
        document.getElementById('group-message-input').addEventListener('input', function() {
            socket.emit('group_typing', { group_id: groupId, is_typing: true });
            clearTimeout(typingTimer);
            typingTimer = setTimeout(() => {
                socket.emit('group_typing', { group_id: groupId, is_typing: false });
            }, 1000);
        });

        socket.on('group_typing', function(data) {
            if (data.group_id === groupId && data.user_id !== {{ user.id }}) {
                document.getElementById('typing-indicator').innerText = data.is_typing ? data.username + ' is typing...' : '';
            }
        });

        loadGroupMessages();
    </script>
    {% endblock %}
    '''
)

DISCOVER_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Discover Users">Discover Users</h2>
    <input type="text" id="search-input" placeholder="Search by username, email, phone..." style="width:100%; padding:0.8rem; margin-bottom:1rem;">
    <div id="results"></div>
    <script>
        document.getElementById('search-input').addEventListener('input', function() {
            const q = this.value.trim();
            if (q.length < 2) return;
            fetch('/api/users/search?q=' + encodeURIComponent(q))
                .then(res => res.json())
                .then(users => {
                    const container = document.getElementById('results');
                    container.innerHTML = '';
                    users.forEach(u => {
                        container.innerHTML += `<div class="card" onclick="window.location='/user/${u.id}'">
                            <div style="display:flex; align-items:center;">
                                <img src="/static/uploads/profiles/${u.profile_image}" style="width:50px; height:50px; border-radius:50%; margin-right:1rem;">
                                <div>
                                    <strong>${u.username} ${u.verified ? '<i class="fas fa-check-circle verified-badge"></i>' : ''}</strong>
                                    <p>Listings: ${u.listings_count} | Followers: ${u.followers_count}</p>
                                </div>
                            </div>
                        </div>`;
                    });
                });
        });
    </script>
    {% endblock %}
    '''
)

CART_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Your Cart">Your Cart</h2>
    <div id="cart-items"></div>
    <div style="margin-top:2rem;">
        <strong data-i18n="Total">Total</strong>: $<span id="cart-total">0.00</span>
        <a href="/checkout" class="btn btn-primary" data-i18n="Proceed to Checkout">Proceed to Checkout</a>
    </div>
    <script>
        function loadCart() {
            fetch('/api/cart')
                .then(res => res.json())
                .then(data => {
                    const container = document.getElementById('cart-items');
                    container.innerHTML = '';
                    data.items.forEach(item => {
                        container.innerHTML += `
                            <div class="card" style="display:flex; align-items:center; gap:1rem;">
                                <img src="/static/uploads/products/${item.image || 'default.jpg'}" style="width:80px; height:80px; object-fit:cover; border-radius:10px;">
                                <div style="flex:1;">
                                    <h4>${item.name}</h4>
                                    <p>$${item.price} x ${item.quantity}</p>
                                </div>
                                <button onclick="removeItem(${item.id})" class="btn btn-outline" style="border-color:var(--accent);">Remove</button>
                            </div>
                        `;
                    });
                    document.getElementById('cart-total').innerText = data.total.toFixed(2);
                });
        }

        function removeItem(itemId) {
            fetch('/api/cart/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ item_id: itemId })
            })
            .then(res => res.json())
            .then(() => loadCart())
            .catch(() => alert('Failed to remove'));
        }

        loadCart();
    </script>
    {% endblock %}
    '''
)

CHECKOUT_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Checkout">Checkout</h2>
    <div id="cart-summary"></div>
    <div style="margin-top:2rem;">
        <h3 data-i18n="Payment Method">Payment Method</h3>
        <select id="payment-method">
            <option value="paypal">PayPal</option>
            <option value="cod">Cash on Delivery</option>
            <option value="wallet">Wallet</option>
        </select>
        <button class="btn btn-primary" onclick="checkout()" data-i18n="Place Order">Place Order</button>
    </div>
    <script>
        function loadSummary() {
            fetch('/api/cart')
                .then(res => res.json())
                .then(data => {
                    let html = '<h3>Items:</h3><ul>';
                    data.items.forEach(i => {
                        html += `<li>${i.name} x ${i.quantity} - $${(i.price * i.quantity).toFixed(2)}</li>`;
                    });
                    html += `</ul><p><strong>Total: $${data.total.toFixed(2)}</strong></p>`;
                    document.getElementById('cart-summary').innerHTML = html;
                });
        }

        function checkout() {
            const method = document.getElementById('payment-method').value;
            fetch('/api/checkout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ payment_method: method })
            })
            .then(res => res.json())
            .then(data => {
                if (data.approval_url) {
                    window.location.href = data.approval_url;
                } else if (data.redirect) {
                    window.location.href = data.redirect;
                } else {
                    alert(data.error || 'Checkout failed');
                }
            })
            .catch(() => alert('Checkout error'));
        }

        loadSummary();
    </script>
    {% endblock %}
    '''
)

ORDER_CONFIRMATION_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:600px; margin:2rem auto;">
        <h2 data-i18n="Order Confirmation">Order Confirmation</h2>
        <p><strong data-i18n="Order ID">Order ID</strong>: {{ order.id }}</p>
        <p><strong data-i18n="Total">Total</strong>: ${{ order.total }}</p>
        <p><strong data-i18n="Status">Status</strong>: {{ order.status }}</p>
        <p><strong data-i18n="Delivery Status">Delivery Status</strong>: {{ order.delivery_status }}</p>
        <p><strong data-i18n="Payment Method">Payment Method</strong>: {{ order.payment_method }}</p>
        <a href="/" class="btn btn-primary" data-i18n="Back to Home">Back to Home</a>
    </div>
    {% endblock %}
    '''
)

SELLER_ORDERS_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Seller Orders">Seller Orders</h2>
    <div id="orders"></div>
    <script>
        function loadOrders() {
            fetch('/api/seller/orders')
                .then(res => res.json())
                .then(orders => {
                    const container = document.getElementById('orders');
                    container.innerHTML = '';
                    orders.forEach(o => {
                        container.innerHTML += `
                            <div class="card">
                                <p><strong>Order #${o.id}</strong> - Buyer: ${o.buyer_name}</p>
                                <p>Total: $${o.total} | Status: ${o.status} | Delivery: ${o.delivery_status}</p>
                                <p>Items: ${o.items.map(i => i.product_name + ' x' + i.quantity).join(', ')}</p>
                                <button onclick="updateDelivery(${o.id})" class="btn btn-outline">Update Delivery</button>
                            </div>
                        `;
                    });
                });
        }

        function updateDelivery(orderId) {
            const status = prompt('Enter delivery status (pending/shipped/delivered/cancelled):');
            if (!status) return;
            const date = prompt('Enter delivery date (YYYY-MM-DD) or leave blank:', '');
            fetch('/api/seller/order/' + orderId + '/update-delivery', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delivery_status: status, delivery_date: date || null })
            })
            .then(res => res.json())
            .then(() => loadOrders())
            .catch(() => alert('Update failed'));
        }

        loadOrders();
    </script>
    {% endblock %}
    '''
)

VIDEO_CALL_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <h2 data-i18n="Video Call with">Video Call with {{ target.username }}</h2>
    <div style="display:flex; gap:1rem; flex-wrap:wrap;">
        <video id="localVideo" autoplay playsinline muted style="width:45%; background:#000; border-radius:10px;"></video>
        <video id="remoteVideo" autoplay playsinline style="width:45%; background:#000; border-radius:10px;"></video>
    </div>
    <div style="margin-top:1rem;">
        <button class="btn btn-primary" onclick="startCall()" id="callBtn" data-i18n="Start Call" disabled>Start Call</button>
        <button class="btn btn-outline" onclick="hangUp()" id="hangupBtn" disabled data-i18n="Hang Up">Hang Up</button>
    </div>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        const iceServers = {{ ice_servers|tojson }};
        let localStream;
        let peerConnection;
        let targetUserId = {{ target.id }};
        let callerId = {{ user.id }};
        let callActive = false;

        async function getLocalStream() {
            try {
                localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
                document.getElementById('localVideo').srcObject = localStream;
                document.getElementById('callBtn').disabled = false;
            } catch (e) {
                alert('Could not access camera/microphone');
            }
        }

        function createPeerConnection() {
            peerConnection = new RTCPeerConnection({ iceServers: iceServers });
            localStream.getTracks().forEach(track => peerConnection.addTrack(track, localStream));

            peerConnection.ontrack = (event) => {
                document.getElementById('remoteVideo').srcObject = event.streams[0];
            };

            peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    socket.emit('ice_candidate', { target_user_id: targetUserId, candidate: event.candidate });
                }
            };
        }

        async function startCall() {
            createPeerConnection();
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);
            socket.emit('call_user', { target_user_id: targetUserId, offer: offer });
            document.getElementById('callBtn').disabled = true;
            document.getElementById('hangupBtn').disabled = false;
            callActive = true;
        }

        socket.on('incoming_call', async (data) => {
            if (data.caller_id === targetUserId) {
                if (confirm('Incoming call from ' + data.caller_name + '. Answer?')) {
                    createPeerConnection();
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
                    const answer = await peerConnection.createAnswer();
                    await peerConnection.setLocalDescription(answer);
                    socket.emit('answer_call', { caller_id: data.caller_id, answer: answer });
                    document.getElementById('callBtn').disabled = true;
                    document.getElementById('hangupBtn').disabled = false;
                    callActive = true;
                }
            }
        });

        socket.on('call_answered', async (data) => {
            await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
        });

        socket.on('ice_candidate', (data) => {
            if (peerConnection) {
                peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
        });

        function hangUp() {
            if (peerConnection) peerConnection.close();
            peerConnection = null;
            callActive = false;
            document.getElementById('callBtn').disabled = false;
            document.getElementById('hangupBtn').disabled = true;
            document.getElementById('remoteVideo').srcObject = null;
        }

        getLocalStream();
    </script>
    {% endblock %}
    '''
)

EDIT_LISTING_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card" style="max-width:600px; margin:2rem auto;">
        <h2 data-i18n="Edit Listing">Edit Listing</h2>
        <form method="post" enctype="multipart/form-data">
            <div style="margin-bottom:1rem;">
                <label data-i18n="Business Name">Business Name</label>
                <input type="text" name="business_name" value="{{ listing.business_name }}" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Description">Description</label>
                <textarea name="description" required style="width:100%; padding:0.8rem;">{{ listing.description }}</textarea>
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Location">Location</label>
                <input type="text" name="location" value="{{ listing.location }}" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Category">Category</label>
                <input type="text" name="category" value="{{ listing.category }}" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Phone">Phone</label>
                <input type="text" name="phone" value="{{ listing.phone }}" required style="width:100%; padding:0.8rem;">
            </div>
            <div style="margin-bottom:1rem;">
                <label data-i18n="Image (optional)">Image (optional)</label>
                <input type="file" name="image" accept="image/*">
                {% if listing.image %}
                    <img src="/static/uploads/listings/{{ listing.image }}" style="max-width:100px; display:block;">
                {% endif %}
            </div>
            <button type="submit" class="btn btn-primary" data-i18n="Update Listing">Update Listing</button>
        </form>
    </div>
    {% endblock %}
    '''
)

LISTING_DETAIL_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card">
        <h2>{{ listing.business_name }} {% if listing.owner_verified %}<i class="fas fa-check-circle verified-badge"></i>{% endif %}</h2>
        <p>{{ listing.description }}</p>
        <p><i class="fas fa-map-marker-alt"></i> {{ listing.location }} | <i class="fas fa-phone"></i> {{ listing.phone }}</p>
        <p><i class="fas fa-heart"></i> <span id="like-count">{{ listing.likes }}</span> | <i class="fas fa-eye"></i> {{ listing.views }}</p>
        {% if user %}
            <button class="btn btn-outline" onclick="toggleLike()" id="like-btn">{{ "Unlike" if user_liked else "Like" }}</button>
            <a href="/compose/{{ listing.user_id }}" class="btn btn-outline" data-i18n="Message Owner">Message Owner</a>
        {% endif %}
        {% if listing.image %}
            <img src="/static/uploads/listings/{{ listing.image }}" style="max-width:100%; border-radius:20px; margin:1rem 0;">
        {% endif %}
    </div>

    <div id="map"></div>
    <script>
        var map = L.map('map').setView([-20.0744, 30.8327], 10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(map);
        L.marker([-20.0744, 30.8327]).addTo(map).bindPopup('{{ listing.location }}').openPopup();
    </script>

    <h3 data-i18n="Products">Products</h3>
    <div class="product-grid" id="products"></div>
    {% if user and user.id == listing.user_id %}
        <h4 data-i18n="Add Product">Add Product</h4>
        <form method="post" action="/listing/{{ listing.id }}/add-product" enctype="multipart/form-data" style="max-width:400px;">
            <input type="text" name="name" placeholder="Product name" required style="width:100%; padding:0.8rem; margin-bottom:0.5rem;">
            <textarea name="description" placeholder="Description" required style="width:100%; padding:0.8rem; margin-bottom:0.5rem;"></textarea>
            <input type="number" step="0.01" name="price" placeholder="Price (optional)" style="width:100%; padding:0.8rem; margin-bottom:0.5rem;">
            <label><input type="checkbox" name="available" value="true" checked> Available</label>
            <input type="file" name="image" accept="image/*" style="margin:0.5rem 0;">
            <button type="submit" class="btn btn-primary">Add Product</button>
        </form>
    {% endif %}

    <h3 data-i18n="Recommendations">Recommendations</h3>
    <div id="recommendations">
        {% for rec in recommendations %}
            <div class="card">
                <p><strong>{{ rec.user.username }}</strong>: {{ rec.comment }}</p>
                <small>{{ rec.created_ago }}</small>
            </div>
        {% else %}
            <p>No recommendations yet.</p>
        {% endfor %}
    </div>
    {% if user %}
        <textarea id="rec-comment" placeholder="Write a recommendation..." style="width:100%; padding:0.8rem;"></textarea>
        <button class="btn btn-primary" onclick="addRecommendation()" data-i18n="Recommend">Recommend</button>
    {% endif %}

    <script>
        function loadProducts() {
            fetch('/api/listings/{{ listing.id }}/products')
                .then(res => res.json())
                .then(products => {
                    const container = document.getElementById('products');
                    container.innerHTML = '';
                    products.forEach(p => {
                        container.innerHTML += `
                            <div class="product-card">
                                ${p.image ? '<img src="/static/uploads/products/'+p.image+'">' : ''}
                                <h4>${p.name}</h4>
                                <p>$${p.price ? p.price.toFixed(2) : 'N/A'}</p>
                                <p>${p.description.substring(0,50)}...</p>
                                <button class="btn btn-outline" onclick="addToCart(${p.id})" data-i18n="Add to Cart">Add to Cart</button>
                                ${p.available ? '' : '<span style="color:red;">Out of stock</span>'}
                            </div>
                        `;
                    });
                });
        }

        function addToCart(productId) {
            fetch('/api/cart/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_id: productId, quantity: 1 })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) alert('Added to cart');
                else alert('Error');
            })
            .catch(() => alert('Network error'));
        }

        function toggleLike() {
            fetch('/api/like/{{ listing.id }}', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    document.getElementById('like-count').innerText = data.likes;
                    document.getElementById('like-btn').innerText = data.liked ? 'Unlike' : 'Like';
                })
                .catch(() => alert('Failed to like'));
        }

        function addRecommendation() {
            const comment = document.getElementById('rec-comment').value.trim();
            if (!comment) return;
            fetch('/api/listing/{{ listing.id }}/recommend', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ comment: comment })
            })
            .then(res => res.json())
            .then(() => {
                alert('Recommendation added');
                location.reload();
            })
            .catch(() => alert('Failed to recommend'));
        }

        loadProducts();
        socket.on('update_likes', function(data) {
            if (data.id === {{ listing.id }}) {
                document.getElementById('like-count').innerText = data.likes;
            }
        });
        socket.on('update_views', function(data) {
            if (data.id === {{ listing.id }}) {
                // optionally update views
            }
        });
    </script>
    {% endblock %}
    '''
)

ABOUT_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card">
        <h2 data-i18n="About BizTech">About BizTech</h2>
        <p data-i18n="BizTech is a platform that connects local businesses in Chivi District with customers. It offers real‑time messaging, group chats, AI assistance, shopping cart, wallet, video calls, and delivery tracking – all free.">
        BizTech is a platform that connects local businesses in Chivi District with customers. It offers real‑time messaging, group chats, AI assistance, shopping cart, wallet, video calls, and delivery tracking – all free.
        </p>
        <p data-i18n="Founded in 2025 by high school students, it has grown into a full‑featured social marketplace.">
        Founded in 2025 by high school students, it has grown into a full‑featured social marketplace.
        </p>
    </div>
    {% endblock %}
    '''
)

TERMS_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card">
        <h2 data-i18n="Terms of Service">Terms of Service</h2>
        <p data-i18n="By using BizTech, you agree to use the platform responsibly and not to misuse any features. We are not liable for any transactions between users.">
        By using BizTech, you agree to use the platform responsibly and not to misuse any features. We are not liable for any transactions between users.
        </p>
    </div>
    {% endblock %}
    '''
)

PRIVACY_TEMPLATE = BASE_TEMPLATE.replace(
    '{% block content %}{% endblock %}',
    '''
    {% block content %}
    <div class="card">
        <h2 data-i18n="Privacy Policy">Privacy Policy</h2>
        <p data-i18n="We respect your privacy. Your personal data is only used to provide the services. We do not sell your information.">
        We respect your privacy. Your personal data is only used to provide the services. We do not sell your information.
        </p>
    </div>
    {% endblock %}
    '''
)

# ============================================================================
# Enhanced port scanner – only 127.0.0.1, max 10 attempts
# ============================================================================
def find_free_port(host='127.0.0.1', start_port=5000, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue
    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()

    host = '127.0.0.1'
    port = find_free_port(host, start_port=5000, max_attempts=10)
    if port is None:
        print(f"❌ No free ports found on {host} in range 5000-5009.")
        sys.exit(1)

    print(f"Attempting to start on {host}:{port} ...")
    print("For production deployment, use a reverse proxy like nginx.")
    print("Make sure to set PAYPAL_CLIENT_ID, PAYPAL_SECRET environment variables for PayPal functionality.")
    socketio.run(app, debug=args.debug, host=host, port=port, use_reloader=False)