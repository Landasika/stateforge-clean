from wtforms import (TextField, IntegerField, FloatField, BooleanField,
                     SelectField, SelectMultipleField, validators)
from flask_wtf import FlaskForm
from enum import Enum
class FlaskBBForm(FlaskForm):
    def populate_errors(self, errors):
        for (attribute, reason) in errors:
            self.errors.setdefault(attribute, []).append(reason)
            field = getattr(self, attribute, None)
            if field:
                field.errors.append(reason)


class SettingValueType(Enum):
    string = 0
    integer = 1
    float = 3
    boolean = 4
    select = 5
    selectmultiple = 6


def populate_settings_dict(form, settings):
    new_settings = {}
    for key, value in settings.items():
        try:
            
            if value == form[key].data:
                continue
            else:
                new_settings[key] = form[key].data
        except KeyError:
            pass

    return new_settings


def populate_settings_form(form, settings):
    for key, value in settings.items():
        try:
            form[key].data = value
        except (KeyError, ValueError):
            pass

    return form



def generate_settings_form(settings):  
    
    class SettingsForm(FlaskBBForm):
        pass

    
    for setting in settings:
        field_validators = []
        if setting.value_type in {SettingValueType.integer,
                                  SettingValueType.float}:
            validator_class = validators.NumberRange
        elif setting.value_type == SettingValueType.string:
            validator_class = validators.Length
        
        if "min" in setting.extra:
            
            field_validators.append(
                validator_class(min=setting.extra["min"])
            )

        if "max" in setting.extra:
            
            field_validators.append(
                validator_class(max=setting.extra["max"])
            )

        
        
        if setting.value_type == SettingValueType.integer:
            setattr(
                SettingsForm, setting.key,
                IntegerField(setting.name, validators=field_validators,
                             description=setting.description)
            )
        
        elif setting.value_type == SettingValueType.float:
            setattr(
                SettingsForm, setting.key,
                FloatField(setting.name, validators=field_validators,
                           description=setting.description)
            )

        
        elif setting.value_type == SettingValueType.string:
            setattr(
                SettingsForm, setting.key,
                TextField(setting.name, validators=field_validators,
                          description=setting.description)
            )

        
        elif setting.value_type == SettingValueType.selectmultiple:
            
            if "coerce" in setting.extra:
                coerce_to = setting.extra['coerce']
            else:
                coerce_to = str

            setattr(
                SettingsForm, setting.key,
                SelectMultipleField(
                    setting.name,
                    choices=setting.extra['choices'](),
                    coerce=coerce_to,
                    description=setting.description
                )
            )

        
        elif setting.value_type == SettingValueType.select:
            
            if "coerce" in setting.extra:
                coerce_to = setting.extra['coerce']
            else:
                coerce_to = str

            setattr(
                SettingsForm, setting.key,
                SelectField(
                    setting.name,
                    coerce=coerce_to,
                    choices=setting.extra['choices'](),
                    description=setting.description)
            )

        
        elif setting.value_type == SettingValueType.boolean:
            setattr(
                SettingsForm, setting.key,
                BooleanField(setting.name, description=setting.description)
            )

    return SettingsForm
