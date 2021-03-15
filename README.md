# Telescoop Backup

Backup your sqlite database to an S3 compatible provider.

## Quick start

1. Add "Telescop Auth" to your INSTALLED_APPS setting like this::

```python
INSTALLED_APPS = [
    ...
    'telescoop_backup',
]
```

2. Include the Telescop Auth URLconf in your project urls.py like this::

```python
    path('backup/', include('telescoop_backup.urls')),
```
   
3. Define the following settings in `settings.py`

```python
BACKUP_ACCESS = 'my_access'  # S3 ACCESS
BACKUP_SECRET = 'my_secret'  # S3 SECRET KEY
BACKUP_BUCKET = 'my_project_backup'  # S3 Bucket
BACKUP_KEEP_N_DAYS = 31  # Optional, defaults to 31
BACKUP_REGION = None  # Optional, defaults to eu-west-3 (Paris)
BACKUP_HOST = None  # Optional, default to s3.{BACKUP_REGIOn}.amazonaws.com
```

By default, old backups are removed in order not to take up too much space.
If you don't want them removed, just set a very large value for BACKUP_KEEP_N_DAYS.
