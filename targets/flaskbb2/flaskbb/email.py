import logging
from flask import render_template
from flask_mail import Message
from flask_babelplus import lazy_gettext as _
from flaskbb.extensions import mail, celery
logger = logging.getLogger(__name__)


@celery.task
def send_reset_token(token, username, email):
    
    send_email(
        subject=_("Password Recovery Confirmation"),
        recipients=[email],
        text_body=render_template(
            "email/reset_password.txt",
            username=username,
            token=token
        ),
        html_body=render_template(
            "email/reset_password.html",
            username=username,
            token=token
        )
    )


@celery.task
def send_activation_token(token, username, email):
    
    send_email(
        subject=_("Account Activation"),
        recipients=[email],
        text_body=render_template(
            "email/activate_account.txt",
            username=username,
            token=token
        ),
        html_body=render_template(
            "email/activate_account.html",
            username=username,
            token=token
        )
    )
@celery.task
def send_async_email(*args, **kwargs):
    send_email(*args, **kwargs)


def send_email(subject, recipients, text_body, html_body, sender=None):
    
    msg = Message(subject, recipients=recipients, sender=sender)
    msg.body = text_body
    msg.html = html_body
    mail.send(msg)
