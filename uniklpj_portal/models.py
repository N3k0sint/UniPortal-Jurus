from datetime import datetime, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

def get_myt_now():
    # Malaysia Time (MYT) is UTC+8
    # Naive local datetime representation for database compatibility
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(50), unique=True, nullable=False)
    
    users = db.relationship('User', backref='role', lazy=True)

    def __repr__(self):
        return f"<Role {self.role_name}>"


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=get_myt_now)
    
    projects = db.relationship('Project', backref='owner', lazy=True)
    documents = db.relationship('Document', backref='uploader', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"

    # Helper methods for role checking
    def is_admin(self):
        return self.role.role_name == 'Admin'

    def is_researcher(self):
        return self.role.role_name == 'Researcher'

    def is_collaborator(self):
        return self.role.role_name == 'Collaborator'


class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_myt_now)
    
    documents = db.relationship('Document', backref='project', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project {self.title}>"


class Document(db.Model):
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    secure_uuid_filename = db.Column(db.String(255), unique=True, nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_approved = db.Column(db.Boolean, default=True, nullable=False)
    delete_requested = db.Column(db.Boolean, default=False, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=get_myt_now)

    def __repr__(self):
        return f"<Document {self.original_filename}>"


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=get_myt_now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Nullable for unauthenticated login attempts
    action = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    details = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<AuditLog {self.action} by User {self.user_id} at {self.timestamp}>"


class BlockedIP(db.Model):
    __tablename__ = 'blocked_ips'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False)
    blocked_at = db.Column(db.DateTime, default=get_myt_now)
    reason = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<BlockedIP {self.ip_address}>"


class CollabRequest(db.Model):
    __tablename__ = 'collab_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    collaborator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending', nullable=False) # Pending, Accepted, Rejected
    created_at = db.Column(db.DateTime, default=get_myt_now)
    
    project = db.relationship('Project', backref=db.backref('collab_requests', lazy=True, cascade="all, delete-orphan"))
    collaborator = db.relationship('User', foreign_keys=[collaborator_id], backref=db.backref('collab_requests', lazy=True))

    def __repr__(self):
        return f"<CollabRequest User {self.collaborator_id} to Project {self.project_id} Status {self.status}>"
