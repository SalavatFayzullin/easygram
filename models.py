from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    profile_image = db.Column(db.String(120), default='default.jpg')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Add relationships for chats
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    messages_received = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy='dynamic')
    
    # Add relationship for groups
    groups_created = db.relationship('Group', backref='creator', lazy='dynamic')
    group_memberships = db.relationship('GroupMembership', backref='user', lazy='dynamic')
    group_messages = db.relationship('GroupMessage', backref='sender', lazy='dynamic')
    
    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"
        
    def last_message_with(self, user_id):
        """Get the last message between current user and specified user"""
        sent = self.messages_sent.filter_by(recipient_id=user_id).order_by(Message.timestamp.desc()).first()
        received = self.messages_received.filter_by(sender_id=user_id).order_by(Message.timestamp.desc()).first()
        
        if sent and not received:
            return sent
        if received and not sent:
            return received
            
        if not sent and not received:
            return None
            
        return sent if sent.timestamp > received.timestamp else received
        
    def get_chat_users(self):
        """Get all users current user has chatted with"""
        sent_to_users = db.session.query(User).join(
            Message, Message.recipient_id == User.id
        ).filter(Message.sender_id == self.id).distinct()
        
        received_from_users = db.session.query(User).join(
            Message, Message.sender_id == User.id
        ).filter(Message.recipient_id == self.id).distinct()
        
        # Combine both querysets
        return sent_to_users.union(received_from_users).all()
    
    def get_groups(self):
        """Get all groups the current user is a member of"""
        return [membership.group for membership in self.group_memberships]
    
    def is_group_admin(self, group_id):
        """Check if the user is an admin of the specified group"""
        group = Group.query.get(group_id)
        if not group:
            return False
        return group.creator_id == self.id
        
    def is_group_member(self, group_id):
        """Check if the user is a member of the specified group"""
        return GroupMembership.query.filter_by(user_id=self.id, group_id=group_id).first() is not None

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f"Message('{self.body}', '{self.timestamp}')"

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    members = db.relationship('GroupMembership', backref='group', lazy='dynamic')
    messages = db.relationship('GroupMessage', backref='group', lazy='dynamic')
    
    def __repr__(self):
        return f"Group('{self.name}')"
    
    def get_members(self):
        """Get all members of the group"""
        return [membership.user for membership in self.members]
    
    def last_message(self):
        """Get the last message in the group"""
        return self.messages.order_by(GroupMessage.timestamp.desc()).first()
        
    def get_ordered_messages(self):
        """Get all messages ordered by timestamp"""
        return self.messages.order_by(GroupMessage.timestamp).all()

class GroupMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    joined_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f"GroupMembership(user_id={self.user_id}, group_id={self.group_id})"

class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f"GroupMessage(group_id={self.group_id}, '{self.body}', '{self.timestamp}')" 