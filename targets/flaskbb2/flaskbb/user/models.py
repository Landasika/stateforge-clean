import logging
from flask import url_for
from flask_login import AnonymousUserMixin, UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from flaskbb.deprecation import deprecated
from flaskbb.exceptions import AuthenticationError
from flaskbb.extensions import cache, db
from flaskbb.forum.models import Forum, Post, Topic, topictracker
from flaskbb.utils.database import CRUDMixin, UTCDateTime, make_comparable
from flaskbb.utils.helpers import time_utcnow
from flaskbb.utils.settings import flaskbb_config

logger = logging.getLogger(__name__)


groups_users = db.Table(
    'groups_users',
    db.Column('user_id', db.Integer,
              db.ForeignKey('users.id', ondelete="CASCADE"),
              nullable=False),
    db.Column('group_id', db.Integer,
              db.ForeignKey('groups.id', ondelete="CASCADE"),
              nullable=False)
)


@make_comparable
class Group(db.Model, CRUDMixin):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    
    admin = db.Column(db.Boolean, default=False, nullable=False)
    super_mod = db.Column(db.Boolean, default=False, nullable=False)
    mod = db.Column(db.Boolean, default=False, nullable=False)
    guest = db.Column(db.Boolean, default=False, nullable=False)
    banned = db.Column(db.Boolean, default=False, nullable=False)

    
    mod_edituser = db.Column(db.Boolean, default=False, nullable=False)
    mod_banuser = db.Column(db.Boolean, default=False, nullable=False)

    
    editpost = db.Column(db.Boolean, default=True, nullable=False)
    deletepost = db.Column(db.Boolean, default=False, nullable=False)
    deletetopic = db.Column(db.Boolean, default=False, nullable=False)
    posttopic = db.Column(db.Boolean, default=True, nullable=False)
    postreply = db.Column(db.Boolean, default=True, nullable=False)
    viewhidden = db.Column(db.Boolean, default=False, nullable=False)
    makehidden = db.Column(db.Boolean, default=False, nullable=False)
    
    def __repr__(self):
        
        return "<{} {} {}>".format(self.__class__.__name__, self.id, self.name)

    @classmethod
    def selectable_groups_choices(cls):
        return Group.query.order_by(Group.name.asc()).with_entities(
            Group.id, Group.name
        ).all()
    @classmethod
    def get_guest_group(cls):
        return cls.query.filter(cls.guest == True).first()

    @classmethod
    def get_member_group(cls):
        
        
        return cls.query.filter(cls.admin == False, cls.super_mod == False,
                                cls.mod == False, cls.guest == False,
                                cls.banned == False).first()


class User(db.Model, UserMixin, CRUDMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    _password = db.Column('password', db.String(120), nullable=False)
    date_joined = db.Column(UTCDateTime(timezone=True), default=time_utcnow,
                            nullable=False)
    lastseen = db.Column(UTCDateTime(timezone=True), default=time_utcnow,
                         nullable=True)
    birthday = db.Column(db.DateTime, nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    website = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    signature = db.Column(db.Text, nullable=True)
    avatar = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    last_failed_login = db.Column(UTCDateTime(timezone=True), nullable=True)
    login_attempts = db.Column(db.Integer, default=0, nullable=False)
    activated = db.Column(db.Boolean, default=False, nullable=False)

    theme = db.Column(db.String(15), nullable=True)
    language = db.Column(db.String(15), default="en", nullable=True)

    post_count = db.Column(db.Integer, default=0)

    primary_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'),
                                 nullable=False)

    posts = db.relationship(
        "Post",
        backref="user",
        primaryjoin="User.id == Post.user_id",
        lazy="dynamic"
    )

    topics = db.relationship(
        "Topic",
        backref="user",
        primaryjoin="User.id == Topic.user_id",
        lazy="dynamic"
    )

    primary_group = db.relationship(
        "Group",
        backref="user_group",
        uselist=False,
        lazy="joined",
        foreign_keys=[primary_group_id]
    )

    secondary_groups = db.relationship(
        "Group",
        secondary=groups_users,
        primaryjoin=(groups_users.c.user_id == id),
        backref=db.backref("users", lazy="dynamic"),
        lazy="dynamic"
    )

    tracked_topics = db.relationship(
        "Topic",
        secondary=topictracker,
        primaryjoin=(topictracker.c.user_id == id),
        backref=db.backref("topicstracked", lazy="dynamic"),
        lazy="dynamic",
        single_parent=True
    )

    
    @property
    def is_active(self):
        
        if flaskbb_config["ACTIVATE_ACCOUNT"]:
            if self.activated:
                return True
            return False

        return True
    @property
    def last_post(self):
        return Post.query.filter(Post.user_id == self.id).\
            order_by(Post.date_created.desc()).first()
    @property
    def url(self):
        
        return url_for("user.profile", username=self.username)

    @property
    def permissions(self):
        
        return self.get_permissions()

    @property
    def groups(self):
        
        return self.get_groups()

    @property
    def days_registered(self):
        
        days_registered = (time_utcnow() - self.date_joined).days
        if not days_registered:
            return 1
        return days_registered

    @property
    def topic_count(self):
        
        return Topic.query.filter(Topic.user_id == self.id).count()

    @property
    def posts_per_day(self):
        
        return round((float(self.post_count) / float(self.days_registered)), 1)

    @property
    def topics_per_day(self):
        
        return round(
            (float(self.topic_count) / float(self.days_registered)), 1
        )
    
    def __repr__(self):
        
        return "<{} {}>".format(self.__class__.__name__, self.username)
    def _get_password(self):
        
        return self._password

    def _set_password(self, password):
        
        if not password:
            return
        self._password = generate_password_hash(password)
    
    password = db.synonym('_password',
                          descriptor=property(_get_password,
                                              _set_password))

    def check_password(self, password):
        
        if self.password is None:
            return False
        return check_password_hash(self.password, password)
    @classmethod
    @deprecated("Use authentication services instead.")
    def authenticate(cls, login, password):
        
        user = cls.query.filter(db.or_(User.username == login,
                                       User.email == login)).first()

        if user is not None:
            if user.check_password(password):
                
                user.login_attempts = 0
                user.save()
                return user

            
            
            if user.login_attempts is None:
                user.login_attempts = 1
            else:
                user.login_attempts += 1
            user.last_failed_login = time_utcnow()
            user.save()
        check_password_hash("dummy password", password)
        raise AuthenticationError

    def recalculate(self):
        
        self.post_count = Post.query.filter_by(user_id=self.id).count()
        self.save()
        return self

    def all_topics(self, page, viewer):
        
        group_ids = [g.id for g in viewer.groups]
        topics = Topic.query.\
            filter(Topic.user_id == self.id,
                   Forum.id == Topic.forum_id,
                   Forum.groups.any(Group.id.in_(group_ids))).\
            order_by(Topic.id.desc()).\
            paginate(page, flaskbb_config['TOPICS_PER_PAGE'], False)
        return topics

    def all_posts(self, page, viewer):
        group_ids = [g.id for g in viewer.groups]
        posts = Post.query.\
            filter(Post.user_id == self.id,
                   Post.topic_id == Topic.id,
                   Topic.forum_id == Forum.id,
                   Forum.groups.any(Group.id.in_(group_ids))).\
            order_by(Post.id.desc()).\
            paginate(page, flaskbb_config['TOPICS_PER_PAGE'], False)
        return posts

    def track_topic(self, topic):
        if not self.is_tracking_topic(topic):
            self.tracked_topics.append(topic)
            return self
    def untrack_topic(self, topic):
        if self.is_tracking_topic(topic):
            self.tracked_topics.remove(topic)
            return self

    def is_tracking_topic(self, topic):
        
        return self.tracked_topics.filter(
            topictracker.c.topic_id == topic.id).count() > 0

    def add_to_group(self, group):
        if not self.in_group(group):
            self.secondary_groups.append(group)
            return self
    def remove_from_group(self, group):
        if self.in_group(group):
            self.secondary_groups.remove(group)
            return self

    def in_group(self, group):
        
        return self.secondary_groups.filter(
            groups_users.c.group_id == group.id).count() > 0

    @cache.memoize()
    def get_groups(self):
        return [self.primary_group] + list(self.secondary_groups)
    @cache.memoize()
    def get_permissions(self, exclude=None):
        
        if exclude:
            exclude = set(exclude)
        else:
            exclude = set()
        exclude.update(['id', 'name', 'description'])
        perms = {}
        for group in self.groups:
            columns = set(group.__table__.columns.keys()) - set(exclude)
            for c in columns:
                perms[c] = getattr(group, c) or perms.get(c, False)
        return perms
    def invalidate_cache(self):
        cache.delete_memoized(self.get_permissions, self)
        cache.delete_memoized(self.get_groups, self)

    def ban(self):
        
        if not self.get_permissions()['banned']:
            banned_group = Group.query.filter(
                Group.banned == True
            ).first()

            self.primary_group = banned_group
            self.save()
            self.invalidate_cache()
            return True
        return False
    def unban(self):
        if self.get_permissions()['banned']:
            member_group = Group.query.filter(
                Group.admin == False,
                Group.super_mod == False,
                Group.mod == False,
                Group.guest == False,
                Group.banned == False
            ).first()
            self.primary_group = member_group
            self.save()
            self.invalidate_cache()
            return True
        return False
    def save(self, groups=None):
        
        if groups is not None:
            
            with db.session.no_autoflush:
                secondary_groups = self.secondary_groups.all()
                for group in secondary_groups:
                    self.remove_from_group(group)

            for group in groups:
                
                if group == self.primary_group:
                    continue
                self.add_to_group(group)

            self.invalidate_cache()

        db.session.add(self)
        db.session.commit()
        return self
    def delete(self):
        
        db.session.delete(self)
        db.session.commit()
        return self


class Guest(AnonymousUserMixin):
    @property
    def permissions(self):
        return self.get_permissions()

    @property
    def groups(self):
        return self.get_groups()

    @cache.memoize()
    def get_groups(self):
        return Group.query.filter(Group.guest == True).all()

    @cache.memoize()
    def get_permissions(self, exclude=None):
        
        if exclude:
            exclude = set(exclude)
        else:
            exclude = set()
        exclude.update(['id', 'name', 'description'])

        perms = {}
        
        for group in self.groups:
            columns = set(group.__table__.columns.keys()) - set(exclude)
            for c in columns:
                perms[c] = getattr(group, c) or perms.get(c, False)
        return perms
    @classmethod
    def invalidate_cache(cls):
        
        cache.delete_memoized(cls.get_permissions, cls)
