import logging
from flaskbb.extensions import cache, db
from flaskbb.utils.database import CRUDMixin
from flaskbb.utils.forms import SettingValueType, generate_settings_form
logger = logging.getLogger(__name__)

class SettingsGroup(db.Model, CRUDMixin):
    __tablename__ = "settingsgroup"

    key = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    settings = db.relationship("Setting", lazy="dynamic", backref="group",
                               cascade="all, delete-orphan")

    def __repr__(self):
        return "<{} {}>".format(self.__class__.__name__, self.key)


class Setting(db.Model, CRUDMixin):
    __tablename__ = "settings"

    key = db.Column(db.String(255), primary_key=True)
    value = db.Column(db.PickleType, nullable=False)
    settingsgroup = db.Column(db.String(255),
                              db.ForeignKey('settingsgroup.key',
                                            ondelete="CASCADE"),
                              nullable=False)

    
    name = db.Column(db.String(200), nullable=False)

    
    description = db.Column(db.Text, nullable=False)

    
    value_type = db.Column(db.Enum(SettingValueType), nullable=False)
    
    
    extra = db.Column(db.PickleType)

    @classmethod
    def get_form(cls, group):
        
        return generate_settings_form(settings=group.settings)
    @classmethod
    def get_all(cls):
        return cls.query.all()

    @classmethod
    def update(cls, settings):
        for key, value in settings.items():
            setting = cls.query.filter(Setting.key == key.lower()).first()

            setting.value = value

            db.session.add(setting)
            db.session.commit()

        cls.invalidate_cache()

    @classmethod
    def get_settings(cls, from_group=None):
        result = None
        if from_group is not None:
            result = from_group.settings
        else:
            result = cls.query.all()

        settings = {}
        for setting in result:
            settings[setting.key] = setting.value

        return settings

    @classmethod
    @cache.cached(key_prefix="settings")
    def as_dict(cls, from_group=None, upper=True):
        settings = {}
        result = None
        if from_group is not None:
            result = SettingsGroup.query.filter_by(key=from_group).\
                first_or_404()
            result = result.settings
        else:
            result = cls.query.all()

        for setting in result:
            if upper:
                setting_key = setting.key.upper()
            else:
                setting_key = setting.key

            settings[setting_key] = setting.value

        return settings

    @classmethod
    def invalidate_cache(cls):
        cache.delete_memoized(cls.as_dict, cls)
