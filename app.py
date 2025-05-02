from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Message, Group, GroupMembership, GroupMessage
import os
import time
import threading
from datetime import datetime
import secrets
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Create profile pictures directory if it doesn't exist
if not os.path.exists('static/profile_pics'):
    os.makedirs('static/profile_pics')

# Profile update form
class ProfileUpdateForm(FlaskForm):
    bio = TextAreaField('Bio', validators=[Length(max=500)])
    profile_picture = FileField('Update Profile Picture', 
                               validators=[FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')])
    submit = SubmitField('Update')

# Dictionary to track online users and their last activity timestamp
online_users = {}
online_users_lock = threading.Lock()

# Time in seconds after which a user is considered offline if no activity
ONLINE_TIMEOUT = 20  # Reduced from 35 to be more responsive

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def update_user_activity(user_id):
    """Update the last activity timestamp for a user"""
    with online_users_lock:
        online_users[user_id] = time.time()

def cleanup_offline_users():
    """Remove users who haven't had activity recently"""
    current_time = time.time()
    with online_users_lock:
        offline_users = [user_id for user_id, last_active in online_users.items() 
                        if current_time - last_active > ONLINE_TIMEOUT]
        for user_id in offline_users:
            del online_users[user_id]
    return offline_users

@app.route('/api/online-status', methods=['GET'])
@login_required
def get_online_status():
    """Get online status of all users"""
    # Clean up offline users first
    cleanup_offline_users()
    
    # Get online user IDs
    with online_users_lock:
        online_user_ids = list(online_users.keys())
    
    # Get user data for online users
    online_users_data = []
    for user_id in online_user_ids:
        user = User.query.get(int(user_id))
        if user:
            online_users_data.append({
                'id': user.id,
                'username': user.username
            })
    
    return jsonify({'online_users': online_users_data})

@app.route('/api/set-offline', methods=['POST'])
@login_required
def set_user_offline():
    """Mark the current user as offline"""
    # For sendBeacon API which can't set custom headers
    try:
        json_data = request.get_json(silent=True)
        if json_data and 'csrf_token' in json_data:
            csrf.validate_csrf(json_data['csrf_token'])
    except:
        # Continue even if CSRF validation fails during page unload
        pass
    
    with online_users_lock:
        if current_user.id in online_users:
            del online_users[current_user.id]
    
    return jsonify({'success': True})

@app.route('/api/user-status/<int:user_id>', methods=['GET'])
@login_required
def get_user_status(user_id):
    """Check if a specific user is online"""
    # Clean up offline users first
    cleanup_offline_users()
    
    # Check if user is in online users dictionary
    with online_users_lock:
        is_online = user_id in online_users
    
    return jsonify({'user_id': user_id, 'online': is_online})

@app.route('/api/messages/<int:user_id>/<int:last_message_id>', methods=['GET'])
@login_required
def check_new_messages(user_id, last_message_id):
    """Long-polling endpoint to check for new messages"""
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if user exists
    other_user = User.query.get_or_404(user_id)
    
    # Don't allow chatting with yourself
    if other_user.id == current_user.id:
        return jsonify({'error': "Can't chat with yourself"}), 400
    
    # Try to get new messages for up to 30 seconds (long-polling)
    max_time = time.time() + 30
    while time.time() < max_time:
        # Update user's online status periodically
        update_user_activity(current_user.id)
        
        # Check if the other user is online
        with online_users_lock:
            other_user_online = other_user.id in online_users
        
        # Query for new messages from the other user to current user
        new_messages = Message.query.filter(
            Message.sender_id == user_id,
            Message.recipient_id == current_user.id,
            Message.id > last_message_id
        ).order_by(Message.timestamp).all()
        
        # If there are new messages, format and return them
        if new_messages:
            # Mark messages as read
            for message in new_messages:
                message.read = True
            db.session.commit()
            
            # Format messages for JSON response
            messages_data = [{
                'id': message.id,
                'sender_id': message.sender_id,
                'recipient_id': message.recipient_id,
                'body': message.body,
                'timestamp': message.timestamp.strftime('%H:%M | %b %d'),
                'read': message.read
            } for message in new_messages]
            
            return jsonify({
                'messages': messages_data,
                'other_user_online': other_user_online
            })
        
        # No new messages yet, wait before checking again
        time.sleep(1)
    
    # Clean up any offline users before responding
    cleanup_offline_users()
    
    # Check other user's status one more time before responding
    with online_users_lock:
        other_user_online = other_user.id in online_users
    
    # If timeout reached without new messages, return empty response with online status
    return jsonify({
        'messages': [],
        'other_user_online': other_user_online
    })

@app.route('/api/send_message/<int:recipient_id>', methods=['POST'])
@login_required
def api_send_message(recipient_id):
    """API endpoint to send a message and return its data"""
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if recipient exists
    recipient = User.query.get_or_404(recipient_id)
    
    # Don't allow sending messages to yourself
    if recipient.id == current_user.id:
        return jsonify({'error': "Can't send messages to yourself"}), 400
    
    # Get message content from JSON data
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
    
    body = data['message']
    if not body:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    # Create and save message
    message = Message(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        body=body
    )
    
    db.session.add(message)
    db.session.commit()
    
    # Check if recipient is online
    with online_users_lock:
        recipient_online = recipient_id in online_users
    
    # Return the new message data
    return jsonify({
        'id': message.id,
        'sender_id': message.sender_id,
        'recipient_id': message.recipient_id,
        'body': message.body,
        'timestamp': message.timestamp.strftime('%H:%M | %b %d'),
        'read': message.read,
        'recipient_online': recipient_online
    })

@app.route('/')
def home():
    # Redirect to dashboard if logged in, otherwise to login page
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Get all users current user has chatted with
    chat_users = current_user.get_chat_users()
    
    # Get all groups the user is a member of
    user_groups = current_user.get_groups()
    
    # Clean up any offline users
    cleanup_offline_users()
    
    # Get online status for all chat users
    with online_users_lock:
        online_status = {user.id: user.id in online_users for user in chat_users}
    
    # Check if a specific user is selected (from chat route)
    selected_user_id = request.args.get('selected_user', type=int)
    selected_user = None
    if selected_user_id:
        selected_user = User.query.get(selected_user_id)
    
    # Check if a specific group is selected
    selected_group_id = request.args.get('selected_group', type=int)
    selected_group = None
    if selected_group_id:
        selected_group = Group.query.get(selected_group_id)
        # Ensure the user is a member of this group
        if selected_group and not current_user.is_group_member(selected_group_id):
            selected_group = None
    
    return render_template('dashboard.html', 
                          chat_users=chat_users, 
                          online_status=online_status, 
                          selected_user=selected_user,
                          user_groups=user_groups,
                          selected_group=selected_group,
                          GroupMessage=GroupMessage)

@app.route('/users')
@login_required
def users():
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Get all users except current user
    users = User.query.all()
    
    # Clean up any offline users
    cleanup_offline_users()
    
    # Get online status for all users
    with online_users_lock:
        online_status = {user.id: user.id in online_users for user in users}
    
    return render_template('users.html', users=users, online_status=online_status)

@app.route('/search')
@login_required
def search():
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Get search query
    query = request.args.get('q', '')
    
    users = []
    groups = []
    
    if query:
        # Search for users
        users = User.query.filter(
            User.id != current_user.id,  # Exclude current user
            User.username.ilike(f'%{query}%')  # Case-insensitive partial match
        ).all()
        
        # Search for groups that the user is a member of
        user_group_ids = [membership.group_id for membership in current_user.group_memberships]
        groups = Group.query.filter(
            Group.id.in_(user_group_ids),
            Group.name.ilike(f'%{query}%')
        ).all()
        
        # Also search for public groups (if you want to implement this feature)
        # public_groups = Group.query.filter(
        #     ~Group.id.in_(user_group_ids),  # Groups user is not a member of
        #     Group.is_public == True,        # Only if you add an is_public field
        #     Group.name.ilike(f'%{query}%')
        # ).all()
        # groups.extend(public_groups)
    
    # Clean up any offline users
    cleanup_offline_users()
    
    # Get online status for all users
    with online_users_lock:
        online_status = {user.id: user.id in online_users for user in users}
    
    return render_template('search.html', 
                          query=query,
                          users=users, 
                          groups=groups,
                          online_status=online_status)

@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if user exists
    other_user = User.query.get_or_404(user_id)
    
    # Don't allow chatting with yourself
    if other_user.id == current_user.id:
        flash("You can't chat with yourself!", 'warning')
        return redirect(url_for('dashboard'))
    
    # Mark received messages as read
    received_messages = Message.query.filter_by(sender_id=user_id, recipient_id=current_user.id).all()
    for message in received_messages:
        if not message.read:
            message.read = True
    db.session.commit()
    
    # Redirect to the dashboard with the chat user as a parameter
    return redirect(url_for('dashboard', selected_user=user_id))

@app.route('/send_message/<int:recipient_id>', methods=['POST'])
@login_required
def send_message(recipient_id):
    # Check if recipient exists
    recipient = User.query.get_or_404(recipient_id)
    
    # Don't allow sending messages to yourself
    if recipient.id == current_user.id:
        flash("You can't send messages to yourself!", 'warning')
        return redirect(url_for('dashboard'))
    
    # Get message content
    body = request.form.get('message')
    
    if not body:
        flash('Message cannot be empty!', 'danger')
        return redirect(url_for('chat', user_id=recipient_id))
    
    # Create and save message
    message = Message(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        body=body
    )
    
    db.session.add(message)
    db.session.commit()
    
    return redirect(url_for('chat', user_id=recipient_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        user_by_username = User.query.filter_by(username=username).first()
        user_by_email = User.query.filter_by(email=email).first()
        
        if user_by_username:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
        
        if user_by_email:
            flash('Email already registered. Please use a different one.', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password, password):
            flash('Please check your username and password and try again.', 'danger')
            return redirect(url_for('login'))
        
        login_user(user, remember=remember)
        next_page = request.args.get('next')
        
        return redirect(next_page) if next_page else redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

def save_profile_picture(form_picture):
    """Save the uploaded profile picture with a random name and resize it"""
    # Generate a random hex for unique filename
    random_hex = secrets.token_hex(8)
    
    # Get the file extension from the uploaded picture
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_filename = random_hex + f_ext
    
    # Define the path where the picture will be saved
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_filename)
    
    # Resize the image to save space and ensure consistent display
    output_size = (200, 200)
    img = Image.open(form_picture)
    img.thumbnail(output_size)
    
    # Save the image
    img.save(picture_path)
    
    return picture_filename

@app.route('/profile/<string:username>')
@login_required
def profile(username):
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Get the user from the database
    user = User.query.filter_by(username=username).first_or_404()
    
    return render_template('profile.html', user=user, title=f"{user.username}'s Profile")

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # Update user's online status
    update_user_activity(current_user.id)
    
    form = ProfileUpdateForm()
    
    if form.validate_on_submit():
        # Only update the profile picture if one was uploaded
        if form.profile_picture.data:
            profile_pic_file = save_profile_picture(form.profile_picture.data)
            current_user.profile_image = profile_pic_file
        
        # Update the bio
        current_user.bio = form.bio.data
        
        # Commit the changes to the database
        db.session.commit()
        
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    
    # Pre-populate the form with current data
    elif request.method == 'GET':
        form.bio.data = current_user.bio
    
    return render_template('edit_profile.html', form=form, title='Edit Profile')

@app.route('/create-group', methods=['GET', 'POST'])
@login_required
def create_group():
    # Update user's online status
    update_user_activity(current_user.id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if not name:
            flash('Group name is required!', 'danger')
            return redirect(url_for('create_group'))
        
        # Create the group
        new_group = Group(name=name, description=description, creator_id=current_user.id)
        db.session.add(new_group)
        db.session.flush()  # Flush to get the group ID
        
        # Add current user as a member
        membership = GroupMembership(user_id=current_user.id, group_id=new_group.id)
        db.session.add(membership)
        
        db.session.commit()
        
        flash(f'Group "{name}" created successfully!', 'success')
        return redirect(url_for('group_chat', group_id=new_group.id))
    
    # Get all users for potential members
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('create_group.html', users=users)

@app.route('/group/<int:group_id>')
@login_required
def group_chat(group_id):
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if group exists
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member of the group
    if not current_user.is_group_member(group_id):
        flash("You are not a member of this group.", 'warning')
        return redirect(url_for('dashboard'))
    
    # Redirect to dashboard with the group selected
    return redirect(url_for('dashboard', selected_group=group_id))

@app.route('/group/<int:group_id>/members')
@login_required
def group_members(group_id):
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if group exists
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member of the group
    if not current_user.is_group_member(group_id):
        flash("You are not a member of this group.", 'warning')
        return redirect(url_for('dashboard'))
    
    # Get all members
    members = group.get_members()
    
    # Check if user is admin
    is_admin = current_user.is_group_admin(group_id)
    
    # Get users who are not members for invitation
    non_members = User.query.filter(User.id != current_user.id).all()
    non_members = [user for user in non_members if not user.is_group_member(group_id)]
    
    return render_template('group_members.html', 
                          group=group, 
                          members=members, 
                          is_admin=is_admin,
                          non_members=non_members)

@app.route('/group/<int:group_id>/add-member', methods=['POST'])
@login_required
def add_group_member(group_id):
    # Check if group exists
    group = Group.query.get_or_404(group_id)
    
    # Check if user is admin
    if not current_user.is_group_admin(group_id):
        flash("Only the group admin can add members.", 'danger')
        return redirect(url_for('group_members', group_id=group_id))
    
    # Get selected user
    user_id = request.form.get('user_id', type=int)
    if not user_id:
        flash("No user selected.", 'danger')
        return redirect(url_for('group_members', group_id=group_id))
    
    user = User.query.get_or_404(user_id)
    
    # Check if user is already a member
    if user.is_group_member(group_id):
        flash(f"{user.username} is already a member of this group.", 'info')
        return redirect(url_for('group_members', group_id=group_id))
    
    # Add user to group
    membership = GroupMembership(user_id=user_id, group_id=group_id)
    db.session.add(membership)
    db.session.commit()
    
    flash(f"{user.username} added to the group successfully!", 'success')
    return redirect(url_for('group_members', group_id=group_id))

@app.route('/group/<int:group_id>/remove-member/<int:user_id>', methods=['POST'])
@login_required
def remove_group_member(group_id, user_id):
    # Check if group exists
    group = Group.query.get_or_404(group_id)
    
    # Check if user is admin
    if not current_user.is_group_admin(group_id):
        flash("Only the group admin can remove members.", 'danger')
        return redirect(url_for('group_members', group_id=group_id))
    
    # Cannot remove the admin (creator)
    if user_id == group.creator_id:
        flash("Cannot remove the group creator.", 'danger')
        return redirect(url_for('group_members', group_id=group_id))
    
    # Remove membership
    membership = GroupMembership.query.filter_by(user_id=user_id, group_id=group_id).first_or_404()
    db.session.delete(membership)
    db.session.commit()
    
    user = User.query.get_or_404(user_id)
    flash(f"{user.username} removed from the group.", 'success')
    return redirect(url_for('group_members', group_id=group_id))

@app.route('/group/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    # Check if group exists
    group = Group.query.get_or_404(group_id)
    
    # Cannot leave if you're the creator
    if group.creator_id == current_user.id:
        flash("As the creator, you cannot leave the group. You may delete it instead.", 'warning')
        return redirect(url_for('group_members', group_id=group_id))
    
    # Remove membership
    membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group_id).first_or_404()
    db.session.delete(membership)
    db.session.commit()
    
    flash(f"You have left the group '{group.name}'.", 'success')
    return redirect(url_for('dashboard'))

@app.route('/group/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    # Check if group exists
    group = Group.query.get_or_404(group_id)
    
    # Check if user is the creator
    if group.creator_id != current_user.id:
        flash("Only the group creator can delete the group.", 'danger')
        return redirect(url_for('group_members', group_id=group_id))
    
    # Delete all memberships
    GroupMembership.query.filter_by(group_id=group_id).delete()
    
    # Delete all messages
    GroupMessage.query.filter_by(group_id=group_id).delete()
    
    # Delete the group
    db.session.delete(group)
    db.session.commit()
    
    flash(f"Group '{group.name}' has been deleted.", 'success')
    return redirect(url_for('dashboard'))

# API routes for group functionality
@app.route('/api/group/<int:group_id>/messages/<int:last_message_id>', methods=['GET'])
@login_required
def check_new_group_messages(group_id, last_message_id):
    """Long-polling endpoint to check for new group messages"""
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if group exists and user is a member
    group = Group.query.get_or_404(group_id)
    if not current_user.is_group_member(group_id):
        return jsonify({'error': "You are not a member of this group", 'code': 'not_member'}), 403
    
    # Try to get new messages for up to 30 seconds (long-polling)
    max_time = time.time() + 30
    while time.time() < max_time:
        # Update user's online status periodically
        update_user_activity(current_user.id)
        
        # Query for new messages
        new_messages = GroupMessage.query.filter(
            GroupMessage.group_id == group_id,
            GroupMessage.id > last_message_id
        ).order_by(GroupMessage.timestamp).all()
        
        # If there are new messages, format and return them
        if new_messages:
            # Format messages for JSON response
            messages_data = [{
                'id': message.id,
                'sender_id': message.sender_id,
                'sender_username': message.sender.username,
                'group_id': message.group_id,
                'body': message.body,
                'timestamp': message.timestamp.strftime('%H:%M | %b %d')
            } for message in new_messages]
            
            return jsonify({
                'messages': messages_data,
                'status': 'success'
            })
        
        # No new messages yet, wait before checking again
        time.sleep(1)
    
    # If timeout reached without new messages, return empty response
    return jsonify({
        'messages': [],
        'status': 'timeout'
    })

@app.route('/api/group/<int:group_id>/send-message', methods=['POST'])
@login_required
def api_send_group_message(group_id):
    """API endpoint to send a message to a group and return its data"""
    # Update user's online status
    update_user_activity(current_user.id)
    
    # Check if group exists and user is a member
    group = Group.query.get_or_404(group_id)
    if not current_user.is_group_member(group_id):
        return jsonify({'error': "You are not a member of this group", 'code': 'not_member'}), 403
    
    # Get message content from JSON data
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided', 'code': 'no_message'}), 400
    
    body = data['message']
    if not body:
        return jsonify({'error': 'Message cannot be empty', 'code': 'empty_message'}), 400
    
    # Create and save message
    message = GroupMessage(
        sender_id=current_user.id,
        group_id=group_id,
        body=body
    )
    
    db.session.add(message)
    db.session.commit()
    
    # Return the new message data
    return jsonify({
        'id': message.id,
        'sender_id': message.sender_id,
        'sender_username': current_user.username,
        'group_id': message.group_id,
        'body': message.body,
        'timestamp': message.timestamp.strftime('%H:%M | %b %d'),
        'status': 'success'
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 