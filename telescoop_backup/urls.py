from django.urls import path

from . import views

app_name = "telescoop_backup"
urlpatterns = [
    path("login", views.frontend_login),
    path("logout", views.frontend_logout),
    path("profile", views.who_am_i, name="auth_profile"),
    path("signup", views.frontend_signup),
    path("user/activation", views.user_activation),
]
