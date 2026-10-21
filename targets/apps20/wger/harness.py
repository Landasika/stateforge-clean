from __future__ import annotations
import datetime
import os
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "wger"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.local_dev")
_DB = Path(os.environ.get("SF_DB", REPO / f".sf_db_{os.getpid()}.sqlite3"))
sys.path.insert(0, str(REPO))
import django  
django.setup()
from django.conf import settings  
settings.DATABASES["default"]["NAME"] = str(_DB)
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver", "localhost"]

from django.core.management import call_command  

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)
for _fixture in ("languages", "licenses", "setting_repetition_units", "setting_weight_units"):
    call_command("loaddata", _fixture, verbosity=0)


from django.contrib.auth import get_user_model  

_USER, _PASS = "probe", "Passw0rd!"
User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    _u = User(username=_USER, email="probe@wger.local", is_superuser=True, is_staff=True)
    _u.set_password(_PASS)
    _u.save()
user = User.objects.get(username=_USER)

from wger.config.models import GymConfig  
if not GymConfig.objects.filter(pk=1).exists():
    GymConfig.objects.create(pk=1)

from wger.core.models import Language  
from wger.exercises.models import Exercise, ExerciseCategory, Translation  

_lang = Language.objects.get(short_name="en")
_cat = ExerciseCategory.objects.first()
if _cat is None:
    _cat = ExerciseCategory.objects.create(name="Probe Category")
_exercise = Exercise.objects.filter(category=_cat).first()
if _exercise is None:
    _exercise = Exercise.objects.create(category=_cat)
_translation = Translation.objects.filter(exercise=_exercise).first()
if _translation is None:
    _translation = Translation.objects.create(
        exercise=_exercise,
        name="Probe Exercise",
        description_source="Probe exercise description " + "x" * 45,
        language=_lang,
    )
from wger.manager.models import Routine  

_today = datetime.date.today()
_routine = Routine.objects.filter(user=user).first()
if _routine is None:
    _routine = Routine(
        user=user,
        name="Probe Routine",
        description="probe",
        start=_today,
        end=_today + datetime.timedelta(days=30),
    )
    _routine.save()

from wger.nutrition.models import NutritionPlan  

_plan = NutritionPlan.objects.filter(user=user).first()
if _plan is None:
    _plan = NutritionPlan(user=user, description="Probe plan")
    _plan.save()

from django.test import Client  

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

ROUTINE_ID = _routine.pk
PLAN_ID = _plan.pk
EXERCISE_ID = _exercise.pk
USER_ID = user.pk


ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/en/", "public"),                          
    ("GET", "/en/user/login", "public"),
    ("GET", "/en/user/registration", "public"),
    ("GET", "/account/login/", "public"),               
    ("GET", "/en/dashboard", "session"),
    ("GET", "/en/user/preferences", "session"),
    ("GET", "/en/user/api-key", "session"),
    ("GET", "/en/user/demo-entries", "session"),
    ("GET", "/en/user/list", "session"),
    ("GET", f"/en/user/{USER_ID}/overview", "session+db"),   
    ("GET", "/en/routine/overview", "session"),
    ("GET", "/en/routine/add", "session"),
    ("GET", f"/en/routine/{ROUTINE_ID}/view", "session+db"),  
    ("GET", f"/en/routine/{ROUTINE_ID}/edit", "session+db"),
    ("GET", f"/en/routine/{ROUTINE_ID}/logs", "session+db"),
    ("GET", f"/en/routine/{ROUTINE_ID}/table", "session+db"),
    ("GET", f"/en/routine/{ROUTINE_ID}/statistics", "session+db"),
    ("GET", "/en/routine/calendar", "session"),
    ("GET", "/en/routine/templates/overview/private", "session"),
    ("GET", "/en/routine/templates/overview/public", "public"),
    ("GET", "/en/weight/overview", "session"),
    ("GET", "/en/weight/export-csv/", "session"),
    ("GET", "/en/weight/import-csv/", "session"),
    ("GET", "/en/nutrition/overview/", "session"),
    ("GET", f"/en/nutrition/{PLAN_ID}/view/", "session+db"),  
    ("GET", f"/en/nutrition/{PLAN_ID}/pdf", "session+db"),
    ("GET", "/en/nutrition/ingredient/overview/", "public"),
    ("GET", "/en/nutrition/calculator/bmi/", "public"),
    ("GET", "/en/exercise/overview/", "public"),
    ("GET", f"/en/exercise/{EXERCISE_ID}/view", "public+db"),
    ("GET", "/en/software/about-us", "public"),
    ("GET", "/en/software/features", "public"),
    ("GET", "/en/software/api", "public"),
    ("GET", "/en/language/list", "public"),
    ("GET", "/sitemap.xml", "public"),
    ("GET", "/robots.txt", "public"),
    
    ("GET", "/api/v2/", "api-auth"),
    ("GET", "/api/v2/routine/", "api-auth"),
    ("GET", "/api/v2/exercise/", "api-auth"),
    ("GET", "/en/user/logout", "session"),              
]


def smoke() -> list[tuple[str, int]]:
    
    out = []
    for method, path, auth in ROUTES:
        try:
            r = CLIENT.get(path) if method == "GET" else CLIENT.post(path)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                 
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
