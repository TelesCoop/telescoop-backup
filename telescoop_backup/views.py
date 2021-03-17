from datetime import datetime

from django.http import HttpResponse

from telescoop_backup.backup import get_latest_backup, DATE_FORMAT


def check_backup_is_recent(request, hours):
    last_backup = get_latest_backup()
    now = datetime.now()
    if last_backup and (now - last_backup).total_seconds() / 3600 / 24 < hours:
        return HttpResponse("yes", status=200)
    else:
        return HttpResponse("no", status=500)


def show_last_backup(request):
    last_backup = get_latest_backup()
    response = last_backup.strftime(DATE_FORMAT)
    if not last_backup:
        response = "no backup yet"
    return HttpResponse(response, status=200)
