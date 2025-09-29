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
BACKUP_HOST = None  # Optional, default to s3.fr-par.scw.cloud (Scaleway Storage in Paris)
BACKUP_USE_AWS = False # True if you want to use Amazon s3

# Optional, for compressing the backup
BACKUP_COMPRESS = True
BACKUP_RECOVER_N_WORKERS = 4  # Optional, default to 1

# Optional, security backup settings - for duplicating files to a second location
SECURITY_BACKUP_PATH_LIST = ['/path/to/media']  # List of paths to backup
SECURITY_BACKUP_BUCKET = 'my_project_security_backup'  # Destination bucket
SECURITY_BACKUP_DESTINATION = 'security_backup'  # Optional, prefix in destination bucket
SECURITY_BACKUP_HOST = 's3.fr-par.scw.cloud'  # Optional, defaults to BACKUP_HOST
SECURITY_BACKUP_REGION = 'fr-par'  # Optional, defaults to BACKUP_REGION
BACKUP_MAX_PAGINATION_ITERATIONS = 10000  # Optional, safety limit for S3 pagination
```

By default, old backups are removed in order not to take up too much space.
If you don't want them removed, just set a very large value for BACKUP_KEEP_N_DAYS.

### Backup

You can now backup with the `backup_db` management command :

- `python manage.py backup_db backup` to back up current database
- `python manage.py backup_db backup_media` to back up `settings.MEDIA_ROOT`
- `python manage.py backup_db list` to list previous backups
- `python manage.py backup_db recover [file_name]` to recover previous database

### View last backup and if it is recent

- `/backup/last-backup` shows the latest backup
- `/backup/backup-is-less-than-XX-hours-old` answers
  `yes` (status 200) or `no` (status 500). This route can be used with a service
  such as uptimerobot.com.

### Security Backup

This solution duplicates media files currently stored directly on S3, providing a backup in case of accidental deletion (for example, due to a misconfigured Ansible script). This is designed to mitigate this specific risk, as Scaleway already provides data redundancy (3 copies by default, even in case of hardware failure).

### Gitignore

If you use it in local environment, ignore the backup files

```
.telescoop_backup_last_backup
*.sqlite
```
