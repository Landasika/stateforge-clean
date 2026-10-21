from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from introduction import views as v
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('introduction.urls')),
    path('',include("django.contrib.auth.urls")),
    path('register',v.register,name="Registration"),
    path('accounts/', include('allauth.urls')),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('challenge/', include('challenge.urls')),
]
