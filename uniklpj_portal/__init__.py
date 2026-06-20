import os
from datetime import timedelta
from flask import Flask, render_template, request, session
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

bcrypt = Bcrypt()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # Secure Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-unsafe-key-change-it')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configure file upload limits
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'uploads'))
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Strict 10MB limit
    
    # Session Cookie Security Hardening
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1) # Strict 1-hour timeout
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions
    from uniklpj_portal.models import db
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Configure Login Manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    login_manager.session_protection = "strong" # Enforces active session protection against hijacking
    
    @login_manager.user_loader
    def load_user(user_id):
        from uniklpj_portal.models import User
        return User.query.get(int(user_id))
    
    # Register blueprints
    from uniklpj_portal.routes.auth import auth_bp
    from uniklpj_portal.routes.portal import portal_bp
    from uniklpj_portal.routes.admin import admin_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp)
    
    # Custom Secure Error Handlers
    @app.errorhandler(400)
    def bad_request(error):
        return render_template('errors/400.html'), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        # We suppress stack trace output to standard users for secure deployment
        return render_template('errors/500.html'), 500
        
    # Inject security headers globally to all responses
    @app.after_request
    def inject_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com;"
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    @app.before_request
    def block_blacklisted_ips_and_make_session_permanent():
        # Get client IP securely
        ip_addr = request.remote_addr or '127.0.0.1'
        if request.headers.getlist("X-Forwarded-For"):
            x_forwarded_for = request.headers.getlist("X-Forwarded-For")[0]
            ip_addr = x_forwarded_for.split(',')[0].strip()
            
        # We need to import BlockedIP inside the request context
        from uniklpj_portal.models import BlockedIP
        if BlockedIP.query.filter_by(ip_address=ip_addr).first():
            # Return custom 403 error page with an IP blocking explanation
            return render_template('errors/403.html', error_message="Access Denied: Your IP address has been dynamically blocked by system administrators due to security alerts."), 403
            
        # Set session to permanent before request so the 1-hour timeout constraint is active
        session.permanent = True

    # Initialize Database & Populate Seed Data
    with app.app_context():
        db.create_all()
        seed_database(db)
        
    return app

def seed_database(db):
    from uniklpj_portal.models import Role, User
    
    # 1. Create Default Roles if they don't exist
    roles = ['Admin', 'Researcher', 'Collaborator']
    for r_name in roles:
        if not Role.query.filter_by(role_name=r_name).first():
            new_role = Role(role_name=r_name)
            db.session.add(new_role)
    db.session.commit()
    
    # 2. Create Default Admin if it doesn't exist
    admin_role = Role.query.filter_by(role_name='Admin').first()
    if not User.query.filter_by(username='admin').first():
        # Enforce secure password meeting pam-complexity requirements
        pwd_hash = bcrypt.generate_password_hash('UniKL@PJ2026!').decode('utf-8')
        default_admin = User(
            username='admin',
            email='admin@uniklpj.edu.my',
            password_hash=pwd_hash,
            role_id=admin_role.id
        )
        db.session.add(default_admin)
        db.session.commit()
        print("[DATABASE SEED] Default Admin seeded: username 'admin', password 'UniKL@PJ2026!'")
