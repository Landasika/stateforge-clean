from collections.abc import MutableMapping
from flaskbb.management.models import Setting
class FlaskBBConfig(MutableMapping):
    def __init__(self, *args, **kwargs):
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return Setting.as_dict()[key]

    def __setitem__(self, key, value):
        Setting.update({key.lower(): value})
    def __delitem__(self, key):  
        pass

    def __iter__(self):
        return iter(Setting.as_dict())

    def __len__(self):
        return len(Setting.as_dict())


flaskbb_config = FlaskBBConfig()
