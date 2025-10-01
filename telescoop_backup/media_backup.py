import datetime
import os
import shutil
from django.conf import settings

from .backup import (
    boto_client,
    BackupType,
    backup_file,
    backup_folder,
    get_backups,
    BUCKET,
    DATE_FORMAT,
)


# Media backup settings
ZIPPED_BACKUP_FILE = os.path.join(settings.BASE_DIR, "media.zip")
ZIPPED_MEDIA_FILE_FORMAT = f"{DATE_FORMAT}_media.zip"


def backup_media():
    """Backup media folder to remote storage."""
    media_folder = settings.MEDIA_ROOT
    backup_folder(media_folder, "media")


def backup_zipped_media(date=None):
    """Backup media folder as a zipped archive."""
    media_folder = settings.MEDIA_ROOT
    filename, extension = ZIPPED_BACKUP_FILE.split(".")
    shutil.make_archive(filename, extension, media_folder)

    backup_file(ZIPPED_BACKUP_FILE, zipped_media_file_name(date))
    os.remove(ZIPPED_BACKUP_FILE)


def recover_zipped_media(file_name=None):
    """Recover media from a zipped backup."""
    connexion = boto_client(BackupType.MAIN)
    if file_name is None or file_name == "latest":
        backups = get_backups(connexion, ZIPPED_MEDIA_FILE_FORMAT)
        if not len(backups):
            raise ValueError("Could not find any media backup")
        file_name = backups[-1]["key"]["Key"]

    key = connexion.get_object(Bucket=BUCKET, Key=file_name)
    if not key:
        raise ValueError(f"Wrong input zipped media {file_name}")

    connexion.download_file(Bucket=BUCKET, Key=file_name, Filename=ZIPPED_BACKUP_FILE)

    shutil.unpack_archive(ZIPPED_BACKUP_FILE, settings.MEDIA_ROOT)
    os.remove(ZIPPED_BACKUP_FILE)


def list_saved_zipped_media():
    """List all saved zipped media backups."""
    backups = get_backups(date_format=ZIPPED_MEDIA_FILE_FORMAT)

    for backup in backups:
        print(backup["key"]["Key"])


def zipped_media_file_name(date=None) -> str:
    """Generate filename for zipped media backup."""
    if date is None:
        date = datetime.datetime.now()
    return date.strftime(ZIPPED_MEDIA_FILE_FORMAT)


def backup_database_and_media(zipped_media=True, overwrite=False):
    """Backup database and media files, then create security backup."""
    from .backup import backup_database
    from .security_backup import security_backup

    date = datetime.datetime.now()
    backup_database(date)
    if zipped_media:
        backup_zipped_media(date)
    else:
        backup_media()

    # Create security backup after regular backup
    security_backup(overwrite=overwrite)


def recover_database_and_media(file_name=None, db_file=None):
    """Recover both database and media files."""
    from .backup import recover_database

    recover_database(db_file)
    recover_zipped_media(file_name)
