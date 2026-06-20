import os
import uuid
import magic
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_from_directory, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Regexp, ValidationError

from uniklpj_portal.models import db, User, Project, Document
from uniklpj_portal.routes.auth import log_event, role_required

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
@role_required(['Admin', 'Researcher'])
def upload_document(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Access Control Check: Researchers can only upload to their own projects (prevent IDOR)
    if not current_user.is_admin() and project.owner_id != current_user.id:
        log_event(
            action="UNAUTHORIZED_FILE_UPLOAD_ATTEMPT",
            user_id=current_user.id,
            details=f"Attempted to upload file to project ID: {project_id} owned by user ID: {project.owner_id}"
        )
        flash("Access Denied: You cannot upload files to projects you do not own.", "danger")
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
            
        # Register in database
        new_doc = Document(
            original_filename=original_name,
            secure_uuid_filename=secure_uuid_name,
            file_path=dest_path,
            mime_type=mime_type,
            project_id=project.id,
            uploaded_by=current_user.id
        )
        db.session.add(new_doc)
        db.session.commit()
        
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
    
    # In a collaboration portal, all authenticated users are allowed to read/download project documents
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
