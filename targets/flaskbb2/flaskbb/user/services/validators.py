import attr
from flask_babelplus import gettext as _
from requests.exceptions import RequestException
from ...core.changesets import ChangeSetValidator
from sqlalchemy import func

from ...core.exceptions import StopValidation, ValidationError
from ...utils.helpers import check_image


@attr.s(eq=False, order=False, hash=False, frozen=True, repr=True)
class CantShareEmailValidator(ChangeSetValidator):
    
    users = attr.ib()

    def validate(self, model, changeset):
        others = self.users.query.filter(
            self.users.id != model.id,
            func.lower(self.users.email) == changeset.new_email,
        ).count()
        if others != 0:
            raise ValidationError(
                "new_email",
                _("%(email)s is already registered", email=changeset.new_email),
            )


class OldEmailMustMatch(ChangeSetValidator):
    
    def validate(self, model, changeset):
        if model.email != changeset.old_email:
            raise StopValidation([("old_email", _("Old email does not match"))])


class EmailsMustBeDifferent(ChangeSetValidator):
    
    def validate(self, model, changeset):
        if model.email == changeset.new_email:
            raise ValidationError("new_email", _("New email address must be different"))
class PasswordsMustBeDifferent(ChangeSetValidator):
    
    def validate(self, model, changeset):
        if model.check_password(changeset.new_password):
            raise ValidationError("new_password", _("New password must be different"))

class OldPasswordMustMatch(ChangeSetValidator):
    def validate(self, model, changeset):
        if not model.check_password(changeset.old_password):
            raise StopValidation([("old_password", _("Old password is wrong"))])


class ValidateAvatarURL(ChangeSetValidator):
    
    def validate(self, user, details_change):
        if not details_change.avatar:
            return
        try:
            error, ignored = check_image(details_change.avatar)
            if error:
                raise ValidationError("avatar", error)
        except RequestException:
            raise ValidationError("avatar", _("Could not retrieve avatar"))
