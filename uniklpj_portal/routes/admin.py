from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp, ValidationError

from uniklpj_portal.models import db, User, Project, Role, AuditLog
from uniklpj_portal.routes.auth import log_event, role_required

admin_bp = Blueprint('admin', __name__)

# --- WTForms for Secure Admin Editing ---
class EditUserForm(FlaskForm):
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
    role_id = SelectField('Security Role', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Update User')
    
    def __init__(self, original_user, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_user = original_user

    def validate_username(self, field):
        if field.data != self.original_user.username:
            if User.query.filter_by(username=field.data).first():
                raise ValidationError('Username is already taken.')

    def validate_email(self, field):
        if field.data != self.original_user.email:
            if User.query.filter_by(email=field.data).first():
                raise ValidationError('Email address is already registered.')


# --- Routes ---
@admin_bp.route('/admin/logs')
@login_required
@role_required(['Admin']) # Secure: Only Admin can access the log viewer
def view_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('admin/logs.html', logs=logs)


@admin_bp.route('/admin/users')
@login_required
@role_required(['Admin'])
def manage_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['Admin'])
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = EditUserForm(original_user=user)
    
    # Populate security role options dynamically
    roles = Role.query.all()
    form.role_id.choices = [(r.id, r.role_name) for r in roles]
    
    if form.validate_on_submit():
        # Prevent self-demotion / lockout
        if user.id == current_user.id and form.role_id.data != user.role_id:
            flash("Security Restriction: You cannot modify your own administrative role to prevent self-demotion lockout.", "danger")
            return redirect(url_for('admin.manage_users'))
            
        # Prevent demoting the last admin (concurrency/race condition safe)
        admin_role = Role.query.filter_by(role_name='Admin').first()
        if user.role_id == admin_role.id and form.role_id.data != admin_role.id:
            # Query with row locking
            admin_users = User.query.filter_by(role_id=admin_role.id).with_for_update().all()
            if len(admin_users) <= 1:
                flash("Security Restriction: Cannot demote the last remaining Administrator in the system.", "danger")
                return redirect(url_for('admin.manage_users'))
                
        old_username = user.username
        old_role = user.role.role_name
        
        user.username = form.username.data
        user.email = form.email.data
        user.role_id = form.role_id.data
        db.session.commit()
        
        # Audit log the administrative change
        log_event(
            action="ADMIN_EDIT_USER",
            user_id=current_user.id,
            details=f"Admin modified user ID: {user.id}. Changes: Username '{old_username}' -> '{user.username}', Role '{old_role}' -> '{user.role.role_name}'"
        )
        flash(f"User account '{user.username}' updated successfully.", "success")
        return redirect(url_for('admin.manage_users'))
        
    elif request.method == 'GET':
        form.username.data = user.username
        form.email.data = user.email
        form.role_id.data = user.role_id
        
    return render_template('admin/edit_user.html', form=form, user=user)


@admin_bp.route('/admin/project/<int:project_id>/delete', methods=['POST'])
@login_required
@role_required(['Admin']) # Admin administrative delete override
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    title = project.title
    db.session.delete(project)
    db.session.commit()
    
    log_event(
        action="ADMIN_DELETE_PROJECT",
        user_id=current_user.id,
        details=f"Admin deleted project: {title} (ID: {project_id})"
    )
    flash(f"Project '{title}' has been successfully deleted by Administrator.", "success")
    return redirect(url_for('portal.dashboard'))


@admin_bp.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required(['Admin'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own administrative account.", "danger")
        return redirect(url_for('admin.manage_users'))
        
    # Prevent deleting the last admin (concurrency/race condition safe)
    admin_role = Role.query.filter_by(role_name='Admin').first()
    if user.role_id == admin_role.id:
        # Lock admin rows to prevent race condition
        admin_users = User.query.filter_by(role_id=admin_role.id).with_for_update().all()
        if len(admin_users) <= 1:
            flash("Security Restriction: Cannot delete the last remaining Administrator in the system.", "danger")
            return redirect(url_for('admin.manage_users'))
            
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    log_event(
        action="ADMIN_DELETE_USER",
        user_id=current_user.id,
        details=f"Admin deleted user account: {username} (ID: {user_id})"
    )
    flash(f"User account '{username}' has been successfully deleted.", "success")
    return redirect(url_for('admin.manage_users'))
