from pluggy import HookspecMarker
spec = HookspecMarker("flaskbb")
@spec
def flaskbb_extensions(app):
    pass


@spec
def flaskbb_load_translations():
    pass


@spec
def flaskbb_load_migrations():
    pass


@spec
def flaskbb_load_blueprints(app):
    pass


@spec
def flaskbb_request_processors(app):
    pass


@spec
def flaskbb_errorhandlers(app):
    pass

@spec
def flaskbb_jinja_directives(app):
    pass
@spec
def flaskbb_additional_setup(app, pluggy):
    pass


@spec
def flaskbb_load_post_markdown_class(app):
    pass
@spec
def flaskbb_load_nonpost_markdown_class(app):
    pass

@spec
def flaskbb_cli(cli, app):
    pass


@spec
def flaskbb_shell_context():
    pass
@spec
def flaskbb_event_post_save_before(post):
    pass
@spec
def flaskbb_event_post_save_after(post, is_new):
    pass


@spec
def flaskbb_event_topic_save_before(topic):
    pass
@spec
def flaskbb_event_topic_save_after(topic, is_new):
    pass
@spec
def flaskbb_event_user_registered(username):
    pass
@spec
def flaskbb_gather_registration_validators():
    pass
@spec
def flaskbb_registration_failure_handler(user_info, failures):
    pass  

@spec
def flaskbb_registration_post_processor(user):
    pass  
@spec(firstresult=True)
def flaskbb_authenticate(identifier, secret):
    pass
@spec
def flaskbb_post_authenticate(user):
    pass
@spec
def flaskbb_authentication_failed(identifier):
    pass
@spec(firstresult=True)
def flaskbb_reauth_attempt(user, secret):
    pass
@spec
def flaskbb_post_reauth(user):
    pass


@spec
def flaskbb_reauth_failed(user):
    pass
@spec
def flaskbb_form_post(form):
    pass
@spec
def flaskbb_form_post_save(form, post):
    pass
@spec
def flaskbb_form_topic(form):
    pass

@spec
def flaskbb_form_topic_save(form, topic):
    pass


@spec
def flaskbb_form_registration(form):
    pass
@spec
def flaskbb_gather_password_validators(app):
    pass


@spec
def flaskbb_gather_email_validators(app):
    pass
@spec
def flaskbb_gather_details_update_validators(app):
    pass


@spec
def flaskbb_details_updated(user, details_update):
    pass
@spec
def flaskbb_password_updated(user):
    pass

@spec
def flaskbb_email_updated(user, email_update):
    pass
@spec
def flaskbb_settings_updated(user, settings_update):
    pass


@spec
def flaskbb_tpl_navigation_before():
    pass
@spec
def flaskbb_tpl_navigation_after():
    pass


@spec
def flaskbb_tpl_user_nav_loggedin_before():
    pass
@spec
def flaskbb_tpl_user_nav_loggedin_after():
    pass
@spec
def flaskbb_tpl_form_registration_before(form):
    pass
@spec
def flaskbb_tpl_form_registration_after(form):
    pass
@spec
def flaskbb_tpl_form_user_details_before(form):
    pass
@spec
def flaskbb_tpl_form_user_details_after(form):
    pass


@spec
def flaskbb_tpl_profile_settings_menu(user):
    pass
@spec
def flaskbb_tpl_profile_sidebar_links(user):
    pass
@spec
def flaskbb_tpl_admin_settings_menu(user):
    pass
@spec
def flaskbb_tpl_admin_settings_sidebar(user):
    pass
@spec
def flaskbb_tpl_profile_sidebar_stats(user):
    pass
@spec
def flaskbb_tpl_post_author_info_before(user, post):
    pass
@spec
def flaskbb_tpl_post_author_info_after(user, post):
    pass

@spec
def flaskbb_tpl_post_content_before(post):
    pass
@spec
def flaskbb_tpl_post_content_after(post):
    pass
@spec
def flaskbb_tpl_post_menu_before(post):
    pass
@spec
def flaskbb_tpl_post_menu_after(post):
    pass

@spec
def flaskbb_tpl_topic_controls(topic):
    pass
@spec
def flaskbb_tpl_form_new_post_before(form):
    pass
@spec
def flaskbb_tpl_form_new_post_after(form):
    pass
@spec
def flaskbb_tpl_form_new_topic_before(form):
    pass
@spec
def flaskbb_tpl_form_new_topic_after(form):
    pass
