import ast
import itertools
import logging
import operator
import os
import re
import time
import warnings
from datetime import datetime, timedelta
from email import message_from_string
from functools import wraps

import pkg_resources
import requests
import unidecode
from babel.core import get_locale_identifier
from babel.dates import format_date as babel_format_date
from babel.dates import format_datetime as babel_format_datetime
from babel.dates import format_timedelta as babel_format_timedelta
from babel.dates import format_time as babel_format_time
from flask import current_app, flash, g, redirect, request, session, url_for
from flask_allows import Permission
from flask_babelplus import lazy_gettext as _
from flask_login import current_user
from flask_themes2 import get_themes_list, render_theme_template
from jinja2 import Markup
from PIL import ImageFile
from pytz import UTC
from werkzeug.local import LocalProxy
from werkzeug.utils import ImportStringError, import_string

from flaskbb.extensions import babel, redis_store
from flaskbb.utils.http import is_safe_url
from flaskbb.utils.settings import flaskbb_config


logger = logging.getLogger(__name__)

_punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.]+')


def to_bytes(text, encoding="utf-8"):
    
    if isinstance(text, str):
        text = text.encode(encoding)
    return text


def to_unicode(input_bytes, encoding="utf-8"):
    
    if not isinstance(input_bytes, str):
        input_bytes = input_bytes.decode(encoding)
    return input_bytes


def slugify(text, delim=u"-"):
    
    text = unidecode.unidecode(text)
    result = []
    for word in _punct_re.split(text.lower()):
        if word:
            result.append(word)
    return str(delim.join(result))

def redirect_url(endpoint, use_referrer=True):
    targets = [endpoint]
    allowed_hosts = current_app.config["ALLOWED_HOSTS"]
    if use_referrer:
        targets.insert(0, request.referrer)
    for target in targets:
        if target and is_safe_url(target, allowed_hosts):
            return target


def redirect_or_next(endpoint, use_referrer=True):
    
    return redirect(
        redirect_url(request.args.get("next"), use_referrer)
        or redirect_url(endpoint, use_referrer)
    )


def render_template(template, **context):  
    
    if current_user.is_authenticated and current_user.theme:
        theme = current_user.theme
    else:
        theme = session.get("theme", flaskbb_config["DEFAULT_THEME"])
    return render_theme_template(theme, template, **context)
def do_topic_action(topics, user, action, reverse):  
    
    if not topics:
        return False

    from flaskbb.utils.requirements import (
        IsAtleastModeratorInForum,
        CanDeleteTopic,
        Has,
    )
    if not Permission(IsAtleastModeratorInForum(forum=topics[0].forum)):
        flash(
            _("You do not have the permissions to execute this action."),
            "danger",
        )
        return False

    modified_topics = 0
    if action not in {"delete", "hide", "unhide"}:
        for topic in topics:
            if getattr(topic, action) and not reverse:
                continue
            setattr(topic, action, not reverse)
            modified_topics += 1
            topic.save()
    elif action == "delete":
        if not Permission(CanDeleteTopic):
            flash(
                _("You do not have the permissions to delete these topics."),
                "danger",
            )
            return False

        for topic in topics:
            modified_topics += 1
            topic.delete()

    elif action == "hide":
        if not Permission(Has("makehidden")):
            flash(
                _("You do not have the permissions to hide these topics."),
                "danger",
            )
            return False

        for topic in topics:
            if topic.hidden:
                continue
            modified_topics += 1
            topic.hide(user)

    elif action == "unhide":
        if not Permission(Has("makehidden")):
            flash(
                _("You do not have the permissions to unhide these topics."),
                "danger",
            )
            return False

        for topic in topics:
            if not topic.hidden:
                continue
            modified_topics += 1
            topic.unhide()

    return modified_topics


def get_categories_and_forums(query_result, user):
    
    it = itertools.groupby(query_result, operator.itemgetter(0))

    forums = []

    if user.is_authenticated:
        for key, value in it:
            forums.append((key, [(item[1], item[2]) for item in value]))
    else:
        for key, value in it:
            forums.append((key, [(item[1], None) for item in value]))

    return forums


def get_forums(query_result, user):
    
    it = itertools.groupby(query_result, operator.itemgetter(0))

    if user.is_authenticated:
        for key, value in it:
            forums = key, [(item[1], item[2]) for item in value]
    else:
        for key, value in it:
            forums = key, [(item[1], None) for item in value]

    return forums

def forum_is_unread(forum, forumsread, user):
    if not user.is_authenticated:
        return False
    read_cutoff = time_utcnow() - timedelta(
        days=flaskbb_config["TRACKER_LENGTH"]
    )
    if flaskbb_config["TRACKER_LENGTH"] == 0:
        return False
    if forum and forum.topic_count == 0:
        return False
    if forum.last_post_id is None or forum.last_post_created < read_cutoff:
        return False
    if forum and not forumsread:
        return forum.last_post_created > read_cutoff
    try:
        
        if forum.last_post_created > forumsread.cleared:
            if forum.last_post_created < forumsread.last_read:
                return False
    except TypeError:
        pass

    
    return forum.last_post_created > forumsread.last_read


def topic_is_unread(topic, topicsread, user, forumsread=None):
    
    if not user.is_authenticated:
        return False
    read_cutoff = time_utcnow() - timedelta(
        days=flaskbb_config["TRACKER_LENGTH"]
    )
    if flaskbb_config["TRACKER_LENGTH"] == 0:
        return False
    if topic.last_updated < read_cutoff:
        return False
    
    if topicsread is None:
        
        if forumsread and forumsread.cleared is not None:
            return forumsread.cleared < topic.last_updated

        
        
        return True

    
    return topicsread.last_read < topic.last_updated

def mark_online(user_id, guest=False):  
    user_id = to_bytes(user_id)
    now = int(time.time())
    expires = now + (flaskbb_config["ONLINE_LAST_MINUTES"] * 60) + 10
    if guest:
        all_users_key = "online-guests/%d" % (now // 60)
        user_key = "guest-activity/%s" % user_id
    else:
        all_users_key = "online-users/%d" % (now // 60)
        user_key = "user-activity/%s" % user_id
    p = redis_store.pipeline()
    p.sadd(all_users_key, user_id)
    p.set(user_key, now)
    p.expireat(all_users_key, expires)
    p.expireat(user_key, expires)
    p.execute()


def get_online_users(guest=False):  
    
    current = int(time.time()) // 60
    minutes = range(flaskbb_config["ONLINE_LAST_MINUTES"])
    if guest:
        users = redis_store.sunion(
            ["online-guests/%d" % (current - x) for x in minutes]
        )
    else:
        users = redis_store.sunion(
            ["online-users/%d" % (current - x) for x in minutes]
        )

    return [to_unicode(u) for u in users]
def crop_title(title, length=None, suffix="..."):
    
    length = flaskbb_config["TITLE_LENGTH"] if length is None else length

    if len(title) <= length:
        return title
    return title[:length].rsplit(" ", 1)[0] + suffix


def is_online(user):
    return user.lastseen >= time_diff()
def time_utcnow():
    return datetime.now(UTC)
def time_diff():
    now = time_utcnow()
    diff = now - timedelta(minutes=flaskbb_config["ONLINE_LAST_MINUTES"])
    return diff


def _get_user_locale():
    locale = flaskbb_config.get("DEFAULT_LANGUAGE", "en")
    if current_user.is_authenticated and current_user.language is not None:
        locale = current_user.language
    return locale

def _format_html_time_tag(datetime, what_to_display):
    if what_to_display == "date-only":
        content = babel_format_date(datetime, locale=_get_user_locale())
    elif what_to_display == "time-only":
        content = babel_format_time(datetime, format="short", locale=_get_user_locale())
    elif what_to_display == "date-and-time":
        content = babel_format_datetime(
            datetime, tzinfo=UTC, locale=_get_user_locale()
        )
        
        content += " UTC"
    else:
        raise ValueError("what_to_display argument invalid")
    isoformat = datetime.isoformat()

    return Markup(
        '<time datetime="{}" data-what_to_display="{}">{}</time>'.format(
            isoformat, what_to_display, content, content
        )
    )
def format_datetime(datetime):
    return _format_html_time_tag(datetime, "date-and-time")
def format_date(datetime):
    return _format_html_time_tag(datetime, "date-only")


def format_time(datetime):
    
    return _format_html_time_tag(datetime, "time-only")


def format_timedelta(delta, **kwargs):
    
    return babel_format_timedelta(delta, locale=_get_user_locale(), **kwargs)


def time_since(time):  
    
    delta = time - time_utcnow()
    return format_timedelta(delta, add_direction=True)
def format_quote(username, content):
    profile_url = url_for("user.profile", username=username)
    content = "\n> ".join(content.strip().split("\n"))
    quote = u"**[{username}]({profile_url}) wrote:**\n> {content}\n".format(
        username=username, profile_url=profile_url, content=content
    )

    return quote


def get_image_info(url):
    

    try:
        r = requests.get(url, stream=True)
    except requests.ConnectionError:
        return None
    image_size = r.headers.get("content-length", None)
    if image_size is None:
        return None
    image_size = float(image_size) / 1000  
    image_max_size = 10000
    image_data = {
        "content_type": "",
        "size": image_size,
        "width": 0,
        "height": 0,
    }

    
    if image_size > image_max_size:
        return image_data
    data = None
    parser = ImageFile.Parser()
    while True:
        data = r.raw.read(1024)
        if not data:
            break
        parser.feed(data)
        if parser.image:
            image_data["content_type"] = parser.image.format
            image_data["width"] = parser.image.size[0]
            image_data["height"] = parser.image.size[1]
            break
    return image_data


def check_image(url):
    
    img_info = get_image_info(url)
    error = None

    if img_info is None:
        error = "Couldn't get image info. Try a different hoster and/or image."
        return error, False
    if img_info["size"] > flaskbb_config["AVATAR_SIZE"]:
        error = "Image is too big! {}kb are allowed.".format(
            flaskbb_config["AVATAR_SIZE"]
        )
        return error, False

    if not img_info["content_type"] in flaskbb_config["AVATAR_TYPES"]:
        error = "Image type {} is not allowed. Allowed types are: {}".format(
            img_info["content_type"], ", ".join(flaskbb_config["AVATAR_TYPES"])
        )
        return error, False

    if img_info["width"] > flaskbb_config["AVATAR_WIDTH"]:
        error = "Image is too wide! {}px width is allowed.".format(
            flaskbb_config["AVATAR_WIDTH"]
        )
        return error, False

    if img_info["height"] > flaskbb_config["AVATAR_HEIGHT"]:
        error = "Image is too high! {}px height is allowed.".format(
            flaskbb_config["AVATAR_HEIGHT"]
        )
        return error, False

    return error, True
def get_alembic_locations(plugin_dirs):
    branches_dirs = [
        tuple([os.path.basename(os.path.dirname(p)), p]) for p in plugin_dirs
    ]

    return branches_dirs
def get_available_themes():
    return [(theme.identifier, theme.name) for theme in get_themes_list()]


def get_available_languages():
    
    return [
        (get_locale_identifier((l.language, l.territory)), l.display_name)
        for l in babel.list_translations()
    ]

def app_config_from_env(app, prefix="FLASKBB_"):
    
    for key, value in os.environ.items():
        if key.startswith(prefix):
            key = key[len(prefix) :]
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                pass
            app.config[key] = value
    return app
def get_flaskbb_config(app, config_file):
    if config_file is not None:
        
        if not isinstance(config_file, str):
            return config_file

        if os.path.exists(os.path.join(app.instance_path, config_file)):
            return os.path.join(app.instance_path, config_file)
        if os.path.exists(os.path.abspath(config_file)):
            return os.path.join(os.path.abspath(config_file))

        
        try:
            return import_string(config_file)
        except ImportStringError:
            return None
    else:
        
        
        project_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(__file__))
        )
        project_config = os.path.join(project_dir, "flaskbb.cfg")

        
        instance_config = os.path.join(app.instance_path, "flaskbb.cfg")
        if os.path.exists(instance_config):
            return instance_config

        
        if os.path.exists(project_config):
            return project_config

class ReverseProxyPathFix(object):
    

    def __init__(self, app, force_https=False):
        self.app = app
        self.force_https = force_https

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ.get("PATH_INFO", "")
            if path_info and path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name) :]
        server = environ.get(
            "HTTP_X_FORWARDED_SERVER_CUSTOM",
            environ.get("HTTP_X_FORWARDED_SERVER", ""),
        )
        if server:
            environ["HTTP_HOST"] = server

        scheme = environ.get("HTTP_X_SCHEME", "")

        if scheme:
            environ["wsgi.url_scheme"] = scheme

        if self.force_https:
            environ["wsgi.url_scheme"] = "https"

        return self.app(environ, start_response)

def real(obj):
    if isinstance(obj, LocalProxy):
        return obj._get_current_object()
    return obj
def parse_pkg_metadata(dist_name):
    try:
        raw_metadata = pkg_resources.get_distribution(dist_name).get_metadata(
            "METADATA"
        )
    except FileNotFoundError:
        raw_metadata = pkg_resources.get_distribution(dist_name).get_metadata(
            "PKG-INFO"
        )

    metadata = {}

    
    for key, value in message_from_string(raw_metadata).items():
        metadata[key.replace("-", "_").lower()] = value

    return metadata


def anonymous_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if current_user is not None and current_user.is_authenticated:
            return redirect_or_next(url_for("forum.index"))
        return f(*a, **k)

    return wrapper


def enforce_recaptcha(limiter):
    current_limit = getattr(g, "view_rate_limit", None)
    login_recaptcha = False
    if current_limit is not None:
        window_stats = limiter.limiter.get_window_stats(*current_limit)
        stats_diff = flaskbb_config["AUTH_REQUESTS"] - window_stats[1]
        login_recaptcha = stats_diff >= flaskbb_config["LOGIN_RECAPTCHA"]
    return login_recaptcha
def registration_enabled(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not flaskbb_config["REGISTRATION_ENABLED"]:
            flash(_("The registration has been disabled."), "info")
            return redirect_or_next(url_for("forum.index"))
        return f(*a, **k)

    return wrapper
def requires_unactivated(f):
    @wraps(f)
    def wrapper(*a, **k):
        if current_user.is_active or not flaskbb_config["ACTIVATE_ACCOUNT"]:
            flash(_("This account is already activated."), "info")
            return redirect(url_for("forum.index"))
        return f(*a, **k)

    return wrapper
def register_view(bp_or_app, routes, view_func, *args, **kwargs):
    for route in routes:
        bp_or_app.add_url_rule(route, view_func=view_func, *args, **kwargs)
class FlashAndRedirect(object):
    def __init__(self, message, level, endpoint):
        
        
        if not callable(endpoint):
            
            
            endpoint_ = lambda *a, **k: url_for(endpoint)  
        else:
            endpoint_ = endpoint
        self._message = message
        self._level = level
        self._endpoint = endpoint_
    def __call__(self, *a, **k):
        flash(self._message, self._level)
        return redirect(self._endpoint(*a, **k))
