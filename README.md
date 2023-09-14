# Telescoop Backup

Backup your sqlite database to an Open Stack Swift compatible provider.

## Quick start

1. Add "Telescoop Backup" to your INSTALLED_APPS setting like this::
```python
INSTALLED_APPS = [
    ...
    'telescoop_backup',
]

BACKUP_S3_BUCKET_NAME = "<backup_bucket_name>"
BACKUP_S3_ACCESS_KEY = "<backup_access_key>"
BACKUP_S3_SECRET_KEY = "<backup_secret_key>"
BACKUP_S3_REGION_NAME = "<backup_region_name>"
BACKUP_S3_ENDPOINT_URL= "<backup_endpont_url"
BACKUP_S3_SIGNATURE = "<backup_signature"

```
To retrieve access keys for OVH : 
https://docs.ovh.com/gb/en/public-cloud/getting_started_with_the_swift_S3_API/

2. Include the Telescop Auth URLconf in your project urls.py like this::

    path('backup/', include('telescoop_backup.urls')),

3. Run ``python manage.py migrate`` to create the auth models.

