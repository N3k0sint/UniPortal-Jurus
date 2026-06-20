import os
import uuid
import magic
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_from_directory, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Length, Email, Regexp, ValidationError, EqualTo

from uniklpj_portal.models import db, User, Project, Document, CollabRequest
from uniklpj_portal.routes.auth import log_event, role_required
from uniklpj_portal import bcrypt

# --- WTForms for Secure User Profile Modification ---
class EditProfileForm(FlaskForm):
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
    submit = SubmitField('Update Profile')
    
    def __init__(self, original_user, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_user = original_user

    def validate_username(self, field):
        if field.data != self.original_user.username:
            if User.query.filter_by(username=field.data).first():
                raise ValidationError('Username is already taken.')

    def validate_email(self, field):
        if field.data != self.original_user.email:
            if User.query.filter_by(email=field.data).first():
                raise ValidationError('Email address is already registered.')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message="Password must be at least 8 characters long.")
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message="Passwords must match.")
    ])
    submit = SubmitField('Change Password')

    # Enforce password complexity check (aligned with JURUS password standards)
    def validate_new_password(self, field):
        p = field.data
        if not any(char.isdigit() for char in p):
            raise ValidationError('Password must contain at least one digit.')
        if not any(char.isupper() for char in p):
            raise ValidationError('Password must contain at least one uppercase letter.')
        if not any(char.islower() for char in p):
            raise ValidationError('Password must contain at least one lowercase letter.')
        if not any(char in '!@#$%^&*()_+=-[]{}|;:,.<>?/~`' for char in p):
            raise ValidationError('Password must contain at least one special character.')


portal_bp = Blueprint('portal', __name__)

# --- WTForms for Secure Input Validation ---
class ProjectForm(FlaskForm):
    title = StringField('Project Title', validators=[
        DataRequired(),
        Length(min=5, max=150)
    ])
    description = TextAreaField('Project Description', validators=[
        DataRequired(),
        Length(min=10, max=2000)
    ])
    submit = SubmitField('Create Project')


class DocumentForm(FlaskForm):
    document = FileField('Upload Research Proposal (PDF only, max 10MB)', validators=[DataRequired()])
    submit = SubmitField('Upload Document')


# --- Routes ---
@portal_bp.route('/')
@portal_bp.route('/dashboard')
@login_required
def dashboard():
    # In a research collaboration portal, all logged-in users can view all projects to collaborate
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('portal/dashboard.html', projects=projects)


@portal_bp.route('/project/new', methods=['GET', 'POST'])
@login_required
@role_required(['Admin', 'Researcher']) # Collaborators cannot create projects
def create_project():
    form = ProjectForm()
    if form.validate_on_submit():
        new_project = Project(
            title=form.title.data,
            description=form.description.data,
            owner_id=current_user.id
        )
        db.session.add(new_project)
        db.session.commit()
        
        log_event(
            action="PROJECT_CREATION",
            user_id=current_user.id,
            details=f"Created project: {new_project.title} (ID: {new_project.id})"
        )
        flash("Project created successfully!", "success")
        return redirect(url_for('portal.dashboard'))
        
    return render_template('portal/create_project.html', form=form)


@portal_bp.route('/project/<int:project_id>/upload', methods=['GET', 'POST'])
@login_required
@role_required(['Admin', 'Researcher', 'Collaborator'])
def upload_document(project_id):
    project = Project.query.get_or_404(project_id)
    
    is_collab = CollabRequest.query.filter_by(project_id=project.id, collaborator_id=current_user.id, status='Accepted').first() is not None
    
    # Access Control Check: Owner, Admin, or approved Collaborators only (prevent IDOR)
    if not current_user.is_admin() and project.owner_id != current_user.id and not is_collab:
        log_event(
            action="UNAUTHORIZED_FILE_UPLOAD_ATTEMPT",
            user_id=current_user.id,
            details=f"Attempted to upload file to project ID: {project_id} owned by user ID: {project.owner_id}"
        )
        flash("Access Denied: You do not have permission to upload files to this project.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    form = DocumentForm()
    if form.validate_on_submit():
        file = form.document.data
        if not file or file.filename == '':
            flash("No file selected.", "danger")
            return redirect(request.url)
            
        original_name = file.filename
        
        # 1. Check Extension (First line of defense)
        _, ext = os.path.splitext(original_name)
        if ext.lower() != '.pdf':
            log_event(
                action="MALICIOUS_FILE_UPLOAD_BLOCKED",
                user_id=current_user.id,
                details=f"Blocked invalid file extension: {original_name}"
            )
            flash("Upload Failed: Only PDF (.pdf) documents are allowed.", "danger")
            return redirect(request.url)
            
        # 2. Check MIME-type using libmagic (Deep packet inspection)
        try:
            file_head = file.read(2048)
            file.seek(0) # Reset file stream pointer
            
            mime_detector = magic.Magic(mime=True)
            mime_type = mime_detector.from_buffer(file_head)
            
            if mime_type != 'application/pdf':
                log_event(
                    action="MALICIOUS_FILE_SIGNATURE_BLOCKED",
                    user_id=current_user.id,
                    details=f"Blocked spoofed PDF file signature. Detected MIME: {mime_type} for file: {original_name}"
                )
                flash("Upload Failed: Spoofed file detected. The file content is not a valid PDF.", "danger")
                return redirect(request.url)
        except Exception as e:
            flash(f"Error checking file format: {str(e)}", "danger")
            return redirect(request.url)
            
        # 3. Secure Renaming to Random UUID (Prevents directory traversal/file overwrite)
        secure_uuid_name = f"{uuid.uuid4().hex}.pdf"
        dest_path = os.path.join(current_app.config['UPLOAD_FOLDER'], secure_uuid_name)
        
        # Save to disk outside web root
        try:
            file.save(dest_path)
        except Exception as e:
            flash(f"Failed to write file to storage directory: {str(e)}", "danger")
            return redirect(request.url)
            
        # Determine if upload is automatically approved or pending request
        is_approved = True
        if not current_user.is_admin() and project.owner_id != current_user.id:
            is_approved = False

        # Register in database
        new_doc = Document(
            original_filename=original_name,
            secure_uuid_filename=secure_uuid_name,
            file_path=dest_path,
            mime_type=mime_type,
            project_id=project.id,
            uploaded_by=current_user.id,
            is_approved=is_approved
        )
        db.session.add(new_doc)
        db.session.commit()
        
        if not is_approved:
            log_event(
                action="FILE_UPLOAD_REQUEST_SUBMITTED",
                user_id=current_user.id,
                details=f"Submitted document upload request: {original_name} (Saved as: {secure_uuid_name}) to project: {project.title}"
            )
            flash("Your document upload request has been submitted for owner approval.", "warning")
        else:
            log_event(
                action="FILE_UPLOAD_SUCCESS",
                user_id=current_user.id,
                details=f"Uploaded document: {original_name} (Saved as: {secure_uuid_name}) to project: {project.title}"
            )
            flash("Document uploaded successfully!", "success")
        return redirect(url_for('portal.dashboard'))
        
    return render_template('portal/upload_document.html', form=form, project=project)


@portal_bp.route('/document/download/<int:doc_id>')
@login_required
def download_document(doc_id):
    document = Document.query.get_or_404(doc_id)
    project = Project.query.get(document.project_id)
    
    # Access Control: If document is not approved, only owner, uploader, or admin can download
    if not document.is_approved:
        if not current_user.is_admin() and project.owner_id != current_user.id and document.uploaded_by != current_user.id:
            log_event(
                action="UNAUTHORIZED_FILE_DOWNLOAD_ATTEMPT",
                user_id=current_user.id,
                details=f"Attempted to download unapproved file ID: {doc_id} on project: {project.title}"
            )
            flash("Access Denied: This document is pending approval from the project owner.", "danger")
            return redirect(url_for('auth.errors_403'))
            
    # Serve file securely from isolated directory
    log_event(
        action="FILE_DOWNLOAD_SUCCESS",
        user_id=current_user.id,
        details=f"Downloaded document: {document.original_filename} (UUID: {document.secure_uuid_filename})"
    )
    return send_from_directory(
        directory=current_app.config['UPLOAD_FOLDER'],
        path=document.secure_uuid_filename,
        as_attachment=True,
        download_name=document.original_filename
    )


@portal_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # IDOR Protection: This form is tied directly to current_user.
    # No user_id is accepted in the parameters, preventing parameter tampering.
    form = EditProfileForm(original_user=current_user)
    
    if form.validate_on_submit():
        old_username = current_user.username
        old_email = current_user.email
        
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        
        # Log the modification
        log_event(
            action="USER_PROFILE_EDIT",
            user_id=current_user.id,
            details=f"Modified profile info. Changes: Username '{old_username}' -> '{current_user.username}', Email '{old_email}' -> '{current_user.email}'"
        )
        flash("Your profile information has been successfully updated.", "success")
        return redirect(url_for('portal.dashboard'))
        
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        
    return render_template('portal/edit_profile.html', form=form)


@portal_bp.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        # Validate current password
        if not bcrypt.check_password_hash(current_user.password_hash, form.current_password.data):
            log_event(
                action="USER_PASSWORD_CHANGE_FAILED",
                user_id=current_user.id,
                details="Attempted password change with incorrect current password."
            )
            flash("Current password is incorrect.", "danger")
            return redirect(url_for('portal.change_password'))
        
        # Hash new password
        hashed_password = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        current_user.password_hash = hashed_password
        db.session.commit()
        
        log_event(
            action="USER_PASSWORD_CHANGE_SUCCESS",
            user_id=current_user.id,
            details="Password successfully changed."
        )
        flash("Your password has been successfully updated.", "success")
        return redirect(url_for('portal.dashboard'))
        
    return render_template('portal/change_password.html', form=form)


@portal_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['Admin', 'Researcher', 'Collaborator'])
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    is_collab = CollabRequest.query.filter_by(project_id=project.id, collaborator_id=current_user.id, status='Accepted').first() is not None
    
    # Access Control: Owner, Admin, or Approved Collaborator only
    if not current_user.is_admin() and project.owner_id != current_user.id and not is_collab:
        log_event(
            action="UNAUTHORIZED_PROJECT_EDIT_ATTEMPT",
            user_id=current_user.id,
            details=f"Attempted to edit project ID: {project_id} owned by user ID: {project.owner_id}"
        )
        flash("Access Denied: You do not have permission to edit this project.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    form = ProjectForm()
    if form.validate_on_submit():
        old_title = project.title
        project.title = form.title.data
        project.description = form.description.data
        db.session.commit()
        
        log_event(
            action="PROJECT_EDIT_SUCCESS",
            user_id=current_user.id,
            details=f"Updated project ID: {project.id}. Title changed from '{old_title}' to '{project.title}'."
        )
        flash("Project proposal updated successfully!", "success")
        return redirect(url_for('portal.dashboard'))
        
    elif request.method == 'GET':
        form.title.data = project.title
        form.description.data = project.description
        
    return render_template('portal/edit_project.html', form=form, project=project)


@portal_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Access Control: Owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        log_event(
            action="UNAUTHORIZED_PROJECT_DELETE_ATTEMPT",
            user_id=current_user.id,
            details=f"Attempted to delete project ID: {project_id} owned by user ID: {project.owner_id}"
        )
        flash("Access Denied: You cannot delete projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    title = project.title
    # Manually delete all files from storage disk first
    for doc in project.documents:
        try:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.secure_uuid_filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            # Continue deleting other files and database record
            pass
            
    db.session.delete(project)
    db.session.commit()
    
    log_event(
        action="PROJECT_DELETE_SUCCESS",
        user_id=current_user.id,
        details=f"Deleted project: {title} (ID: {project_id})"
    )
    flash(f"Project '{title}' and all its uploaded files have been deleted successfully.", "success")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/document/<int:doc_id>/delete', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher', 'Collaborator'])
def delete_document(doc_id):
    document = Document.query.get_or_404(doc_id)
    project = Project.query.get(document.project_id)
    
    is_collab = CollabRequest.query.filter_by(project_id=project.id, collaborator_id=current_user.id, status='Accepted').first() is not None
    
    # Access Control: Owner, Admin, or approved Collaborators only (prevent IDOR)
    if not current_user.is_admin() and project.owner_id != current_user.id and not is_collab:
        log_event(
            action="UNAUTHORIZED_FILE_DELETE_ATTEMPT",
            user_id=current_user.id,
            details=f"Attempted to delete document ID: {doc_id} on project: {project.title}"
        )
        flash("Access Denied: You do not have permission to delete this file.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    filename = document.original_filename
    uuid_filename = document.secure_uuid_filename
    
    # If the user is the owner or an admin, delete permanently
    if current_user.is_admin() or project.owner_id == current_user.id:
        try:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], uuid_filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            pass
            
        db.session.delete(document)
        db.session.commit()
        
        log_event(
            action="FILE_DELETE_SUCCESS",
            user_id=current_user.id,
            details=f"Deleted document: {filename} (UUID: {uuid_filename}) from project: {project.title}"
        )
        flash(f"Document '{filename}' has been deleted successfully.", "success")
    else:
        # Approved collaborator, request deletion instead
        document.delete_requested = True
        db.session.commit()
        
        log_event(
            action="FILE_DELETE_REQUEST_SUBMITTED",
            user_id=current_user.id,
            details=f"Submitted deletion request for document: {filename} on project: {project.title}"
        )
        flash(f"Deletion request for '{filename}' has been submitted to the project owner.", "warning")
        
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/project/<int:project_id>/request-collab', methods=['POST'])
@login_required
@role_required(['Collaborator', 'Researcher'])
def request_collaboration(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check that requesting user is not the project owner
    if current_user.id == project.owner_id:
        flash("Access Denied: You cannot request collaboration on your own project.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    # Check if a request already exists
    existing_request = CollabRequest.query.filter_by(
        project_id=project_id,
        collaborator_id=current_user.id
    ).first()
    
    if existing_request:
        flash(f"You have already submitted a collaboration request for '{project.title}'. Status: {existing_request.status}", "warning")
        return redirect(url_for('portal.dashboard'))
        
    new_request = CollabRequest(
        project_id=project_id,
        collaborator_id=current_user.id,
        status='Pending'
    )
    db.session.add(new_request)
    db.session.commit()
    
    log_event(
        action="COLLAB_REQUEST_SUBMITTED",
        user_id=current_user.id,
        details=f"User requested to join project ID: {project_id} ('{project.title}')"
    )
    flash(f"Your request to collaborate on '{project.title}' has been submitted to the project owner.", "success")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/collab-request/<int:request_id>/approve', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def approve_collab_request(request_id):
    req = CollabRequest.query.get_or_404(request_id)
    project = Project.query.get(req.project_id)
    
    # Access Control: Project owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        flash("Access Denied: You cannot approve requests for projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    req.status = 'Accepted'
    db.session.commit()
    
    log_event(
        action="COLLAB_REQUEST_APPROVED",
        user_id=current_user.id,
        details=f"Approved collaboration request ID: {req.id} from user ID: {req.collaborator_id} for project: {project.title}"
    )
    flash(f"Approved collaboration request from '{req.collaborator.username}'.", "success")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/collab-request/<int:request_id>/reject', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def reject_collab_request(request_id):
    req = CollabRequest.query.get_or_404(request_id)
    project = Project.query.get(req.project_id)
    
    # Access Control: Project owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        flash("Access Denied: You cannot decline requests for projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    req.status = 'Rejected'
    db.session.commit()
    
    log_event(
        action="COLLAB_REQUEST_DECLINED",
        user_id=current_user.id,
        details=f"Declined collaboration request ID: {req.id} from user ID: {req.collaborator_id} for project: {project.title}"
    )
    flash(f"Declined collaboration request from '{req.collaborator.username}'.", "warning")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/document/<int:doc_id>/approve-upload', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def approve_upload(doc_id):
    document = Document.query.get_or_404(doc_id)
    project = Project.query.get(document.project_id)
    
    # Access Control: Project owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        flash("Access Denied: You cannot approve uploads for projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    document.is_approved = True
    db.session.commit()
    
    log_event(
        action="FILE_UPLOAD_REQUEST_APPROVED",
        user_id=current_user.id,
        details=f"Approved document upload: {document.original_filename} (ID: {document.id}) on project: {project.title}"
    )
    flash(f"Approved upload request for '{document.original_filename}'.", "success")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/document/<int:doc_id>/reject-upload', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def reject_upload(doc_id):
    document = Document.query.get_or_404(doc_id)
    project = Project.query.get(document.project_id)
    
    # Access Control: Project owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        flash("Access Denied: You cannot reject uploads for projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    filename = document.original_filename
    uuid_filename = document.secure_uuid_filename
    
    # Delete from storage disk
    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], uuid_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
        
    db.session.delete(document)
    db.session.commit()
    
    log_event(
        action="FILE_UPLOAD_REQUEST_DECLINED",
        user_id=current_user.id,
        details=f"Declined document upload: {filename} (ID: {doc_id}) on project: {project.title}"
    )
    flash(f"Declined and removed upload request for '{filename}'.", "warning")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/document/<int:doc_id>/approve-delete', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def approve_delete(doc_id):
    document = Document.query.get_or_404(doc_id)
    project = Project.query.get(document.project_id)
    
    # Access Control: Project owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        flash("Access Denied: You cannot approve deletion for projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    filename = document.original_filename
    uuid_filename = document.secure_uuid_filename
    
    # Delete from storage disk
    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], uuid_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
        
    db.session.delete(document)
    db.session.commit()
    
    log_event(
        action="FILE_DELETE_REQUEST_APPROVED",
        user_id=current_user.id,
        details=f"Approved deletion request for document: {filename} (ID: {doc_id}) on project: {project.title}"
    )
    flash(f"Approved deletion of '{filename}'. The file has been permanently removed.", "success")
    return redirect(url_for('portal.dashboard'))


@portal_bp.route('/document/<int:doc_id>/reject-delete', methods=['POST'])
@login_required
@role_required(['Admin', 'Researcher'])
def reject_delete(doc_id):
    document = Document.query.get_or_404(doc_id)
    project = Project.query.get(document.project_id)
    
    # Access Control: Project owner or Admin only
    if not current_user.is_admin() and project.owner_id != current_user.id:
        flash("Access Denied: You cannot reject deletion for projects you do not own.", "danger")
        return redirect(url_for('portal.dashboard'))
        
    document.delete_requested = False
    db.session.commit()
    
    log_event(
        action="FILE_DELETE_REQUEST_DECLINED",
        user_id=current_user.id,
        details=f"Declined deletion request for document: {document.original_filename} (ID: {doc_id}) on project: {project.title}"
    )
    flash(f"Declined deletion request for '{document.original_filename}'.", "warning")
    return redirect(url_for('portal.dashboard'))
