import datetime

from django.conf import settings

import swiftclient

DATE_FORMAT = "%Y-%m-%dT%H:%M"
FILE_FORMAT = f"{DATE_FORMAT}_db.sqlite"
FILE_PATH = "{project_name}/{file_name}"
DEFAULT_AUTH_VERSION = 2
DEFAULT_CONTAINER_NAME = "db-backups"


def get_project_name():
    """
    Get the name of the project from BASE_DIR.

    Could cause conflicts if two projects have the same name.
    """
    return settings.BASE_DIR.name


def db_name() -> str:
    return datetime.datetime.now().strftime(FILE_FORMAT)


def parse_db_date_from_file_name(file_name: str) -> datetime.datetime:
    return datetime.datetime.strptime(file_name, FILE_FORMAT)


def retrieve_openstack_configuration():
    """Retrieve configuaration from settings.py."""
    try:
        url = getattr(settings, "BACKUP_AUTH_URL")
        user = getattr(settings, "BACKUP_USER")
        key = getattr(settings, "BACKUP_KEY")
        tenant_name = getattr(settings, "BACKUP_TENANT_NAME")
        auth_version = getattr(settings, "BACKUP_AUTH_VERSION", 2)
        container_name = getattr(settings, "BACKUP_CONTAINER_NAME")
    except AttributeError as e:
        missing_attribute = e.args[0].split('attribute ')[1]
        raise AttributeError(f"You must define '{missing_attribute}' in your settings.")

    return url, user, key, tenant_name, auth_version, container_name


def backup_db() -> None:
    url, user, key, tenant_name, auth_version, container_name = retrieve_openstack_configuration()

    db_engine = settings.DATABASES["default"]["ENGINE"]
    db_file_path = settings.DATABASES["default"]["NAME"]

    if not ("sqlite" in db_engine or "spatialite" in db_engine):
        raise ValueError(f"Can only backup sqlite database. Engine is '{db_engine}'.")

    remote_path = FILE_PATH.format(get_project_name(), db_name())

    with open(db_file_path, "r") as db_file:
        with swiftclient.client.Connection(authurl=url, user=user, key=key, blabla=blabla) as connection:
            connection.put_object(container_name, remote_path, db_file.read())

    print(f"DB backed up at path {remote_path} in container {container_name}")


def remove_old_databases():
    keep_databases_days = getattr(settings, "BACKUP_DATABASE_KEEP_N_DAYS", 30)
    # TODO :
    #  - list databases
    #  - parse date from name
    #  - remove old ones
