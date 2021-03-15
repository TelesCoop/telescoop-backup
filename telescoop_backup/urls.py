from django.urls import path

from . import views

app_name = "telescoop_backup"
urlpatterns = [
    path("backup-is-less-than-<int:hours>-hours-old", views.check_backup_is_recent),
    path("last-backup", views.show_last_backup),
]
