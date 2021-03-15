# Telescoop Backup

Backup your sqlite database to an Open Stack Swift compatible provider.

## Quick start

1. Add "Telescop Auth" to your INSTALLED_APPS setting like this::
```python
INSTALLED_APPS = [
    ...
    'telescoop_backup',
]
```

2. Include the Telescop Auth URLconf in your project urls.py like this::

    path('backup/', include('telescoop_auth.urls')),

3. Run ``python manage.py migrate`` to create the auth models.
