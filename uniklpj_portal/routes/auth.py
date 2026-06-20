from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Regexp, ValidationError
from functools import wraps

from uniklpj_portal.models import db, User, Role, AuditLog
from uniklpj_portal import bcrypt

auth_bp = Blueprint('auth', __name__)

# Helper to log actions
def log_event(action, user_id=None, details=None):
    ip_addr = request.remote_addr or '127.0.0.1'
    # Check for proxy forwarding
    if request.headers.getlist("X-Forwarded-For"):
        ip_addr = request.headers.getlist("X-Forwarded-For")[0]
        
    new_log = AuditLog(
        user_id=user_id,
        action=action,
        ip_address=ip_addr,
        details=details
    )
    db.session.add(new_log)
    db.session.commit()

# --- Custom Role-Based Access Control Decorator ---
def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role.role_name not in allowed_roles:
                log_event(
                    action="UNAUTHORIZED_ACCESS_ATTEMPT",
                    user_id=current_user.id,
                    details=f"Attempted to access: {request.path}. Allowed roles: {allowed_roles}."
                )
                flash("Access Denied: You do not have the required permissions for this action.", "danger")
                return redirect(url_for('auth.errors_403')) # Redirect to custom 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Helper redirect for custom 403
@auth_bp.app_errorhandler(403)
@auth_bp.route('/403')
def errors_403(error=None):
    return render_template('errors/403.html'), 403

# --- WTForms for Authentication Input Validation ---
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=25),
        Regexp(r'^[a-zA-Z0-9_]+$', message="Username must contain only letters, numbers, or underscores.")
    ])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')


class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=25),
        Regexp(r'^[a-zA-Z0-9_]+$', message="Username must contain only letters, numbers, or underscores.")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(),
        Email(),
        Length(max=100)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message="Password must be at least 8 characters long.")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message="Passwords must match.")
    ])
    role_id = SelectField('Register As', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Register')

    # Enforce password complexity check
    def validate_password(self, field):
        p = field.data
        if not any(char.isdigit() for char in p):
            raise ValidationError('Password must contain at least one digit.')
        if not any(char.isupper() for char in p):
            raise ValidationError('Password must contain at least one uppercase letter.')
        if not any(char.islower() for char in p):
            raise ValidationError('Password must contain at least one lowercase letter.')
        if not any(char in '!@#$%^&*()_+=-[]{}|;:,.<>?/~`' for char in p):
            raise ValidationError('Password must contain at least one special character.')

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username is already taken.')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email address is already registered.')


# --- Routes ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('portal.dashboard'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            log_event(action="USER_LOGIN_SUCCESS", user_id=user.id, details="Successfully signed in.")
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for('portal.dashboard'))
        else:
            # Audit log failed attempt with Username context if valid
            user_id = user.id if user else None
            log_event(
                action="USER_LOGIN_FAILED",
                user_id=user_id,
                details=f"Failed login attempt for username: {form.username.data}"
            )
            flash("Invalid username or password. Please try again.", "danger")
            
    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('portal.dashboard'))
        
    form = RegisterForm()
    # Populate role selection dynamically from database roles (excluding Admin for self-registration)
    roles = Role.query.filter(Role.role_name != 'Admin').all()
    form.role_id.choices = [(r.id, r.role_name) for r in roles]
    
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        new_user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_password,
            role_id=form.role_id.data
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Audit log creation of new user
        log_event(action="USER_REGISTRATION", user_id=new_user.id, details=f"New user registered under role: {new_user.role.role_name}")
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for('auth.login'))
        
    return render_template('auth/register.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    user_id = current_user.id
    username = current_user.username
    logout_user()
    log_event(action="USER_LOGOUT", user_id=user_id, details=f"User {username} signed out.")
    flash("You have been signed out successfully.", "success")
    return redirect(url_for('auth.login'))
