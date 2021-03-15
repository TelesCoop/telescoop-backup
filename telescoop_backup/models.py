from django.db import models


class Backup(models.Model):
    date = models.DateTimeField(auto_now=True)
    path = models.CharField(max_length=100)
    deleted = models.BooleanField(default=False)
