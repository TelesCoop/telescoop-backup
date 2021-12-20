# Telescoop Backup

Backup your sqlite database to an S3 compatible provider.

## Quick start

### Configuration

- Add "Telescop Backup" to your INSTALLED_APPS setting like this::

```python
INSTALLED_APPS = [
    ...
    'telescoop_backup',
]
```

- Include the Telescop Backup URLconf in your project urls.py like this::

```python
    path('backup/', include('telescoop_backup.urls')),
```
   
- Define the following settings in `settings.py`

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

### Backup

You can now backup with the `backup_db` management command :

- `python manage.py backup_db backup` to back up current database
- `python manage.py backup_db media` to back up `settings.MEDIA_ROOT`
- `python manage.py backup_db list` to list previous backups
- `python manage.py backup_db recover [file_name]` to recover previous database

### View last backup and if it is recent

- `/backup/last-backup` shows the latest backup
- `/backup/backup-is-less-than-XX-hours-old` answers
`yes` (status 200) or `no` (status 500). This route can be used with a service
such as uptimerobot.com.

### Gitignore

If you use it in local environment, ignore the backup files
```
.telescoop_backup_last_backup
*.sqlite
```
