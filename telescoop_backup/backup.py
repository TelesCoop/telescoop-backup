import datetime
import os
import shutil
import subprocess

from django.conf import settings

import boto
from boto.s3.key import Key

IS_POSTGRES = "postgresql" in settings.DATABASES["default"]["ENGINE"]

DATE_FORMAT = "%Y-%m-%dT%H:%M"
DEFAULT_AUTH_VERSION = 2
DEFAULT_CONTAINER_NAME = "db-backups"
if IS_POSTGRES:
    DATABASE_BACKUP_FILE = os.path.join(settings.BASE_DIR, "dump.sql")
    FILE_FORMAT = f"{DATE_FORMAT}_postgres_dump.sql"
    SELECT_ALL_PUBLIC_TABLES_QUERY = """select 'drop table if exists "' || tablename || '" cascade;' from pg_tables where schemaname = 'public';"""
else:
    db_file_path = settings.DATABASES["default"]["NAME"]
    DATABASE_BACKUP_FILE = os.path.join(os.path.dirname(db_file_path), "backup.sqlite")
    SQLITE_DUMP_COMMAND = """sqlite3 '{source_file}' ".backup '{backup_file}'" """.format(
        source_file=db_file_path, backup_file=DATABASE_BACKUP_FILE
    )
    FILE_FORMAT = f"{DATE_FORMAT}_db.sqlite"
KEEP_N_DAYS = getattr(settings, "BACKUP_KEEP_N_DAYS", 31)
host = getattr(settings, "BACKUP_HOST", None)
if host is None:
    region = getattr(settings, "BACKUP_REGION", "eu-west-3")
    host = f"s3.{region}.amazonaws.com"
LAST_BACKUP_FILE = os.path.join(settings.BASE_DIR, ".telescoop_backup_last_backup")



def boto_connexion():
    """Connect to AWS S3."""
    return boto.connect_s3(
        settings.BACKUP_ACCESS,
        settings.BACKUP_SECRET,
        host=host,
    )


def backup_file(
    file_path: str, remote_key: str, connexion=None, bucket=None, skip_if_exists=False
):
    """Backup backup_file on third-party server."""
    if connexion is None:
        connexion = boto_connexion()
    if bucket is None:
        bucket = get_backup_bucket(connexion)

    key = Key(bucket)
    if skip_if_exists and key.exists():
        return
    key.key = remote_key
    key.set_contents_from_filename(file_path)


def backup_folder(path: str, remote_path: str, connexion=None):
    """Recursively backup entire folder. Ignores paths that were already backup up."""
    if connexion is None:
        connexion = boto_connexion()
    bucket = get_backup_bucket(connexion)
    for root, dirs, files in os.walk(path):
        # without the dot, os.path interprets the path as absolute,
        # so os.path.join has no effect
        root_no_base = "." + root.split(path, 1)[1]
        for file in files:
            path_no_base = os.path.join(root_no_base, file)
            dest = os.path.normpath(os.path.join(remote_path, path_no_base))
            backup_file(
                os.path.join(root, file),
                dest,
                bucket=bucket,
                skip_if_exists=True,
            )


def get_backup_bucket(connexion=None):
    if connexion is None:
        connexion = boto_connexion()
    return connexion.get_bucket(settings.BACKUP_BUCKET)


def dump_database():
    """Dump the database to a file."""
    if IS_POSTGRES:
        import pexpect
        db_name = settings.DATABASES["default"]["NAME"]
        db_user = settings.DATABASES["default"]["USER"]
        db_password = settings.DATABASES["default"]["PASSWORD"]
        shell_cmd = f"pg_dump {db_name} -U {db_user} > {DATABASE_BACKUP_FILE}"
        child = pexpect.spawn("/bin/bash", ["-c", shell_cmd])
        child.expect("Password:")
        child.sendline(db_password)
    else:
        subprocess.check_output(SQLITE_DUMP_COMMAND, shell=True)


def remove_old_database_files():
    """Remove files older than KEEP_N_DAYS days."""
    connexion = boto_connexion()
    backup_keys = get_backup_keys(connexion)
    bucket = get_backup_bucket(connexion)

    now = datetime.datetime.now()
    date_format = FILE_FORMAT

    for backup_key in backup_keys:
        try:
            file_date = datetime.datetime.strptime(backup_key.key, date_format)
        except ValueError:
            # is not a database backup
            continue
        if (now - file_date).total_seconds() > KEEP_N_DAYS * 3600 * 24:
            print("removing old file {}".format(backup_key.key))
            bucket.delete_key(backup_key)
        else:
            print("keeping {}".format(backup_key.key))


def backup_media():
    media_folder = settings.MEDIA_ROOT
    backup_folder(media_folder, "media")


def upload_to_online_backup():
    """Upload the database file online."""
    backup_file(file_path=DATABASE_BACKUP_FILE, remote_key=db_name())


def update_latest_backup():
    with open(LAST_BACKUP_FILE, "w") as fh:
        fh.write(datetime.datetime.now().strftime(DATE_FORMAT))


def get_latest_backup():
    if not os.path.isfile(LAST_BACKUP_FILE):
        return None
    with open(LAST_BACKUP_FILE, "r") as fh:
        return datetime.datetime.strptime(fh.read().strip(), DATE_FORMAT)


def backup_database():
    """Main function."""
    dump_database()
    upload_to_online_backup()
    remove_old_database_files()
    update_latest_backup()


def get_backup_keys(connexion=None):
    """Return the db keys."""
    bucket = get_backup_bucket(connexion)
    return list(bucket.list())


def load_postgresql_dump(path):
    import fileinput
    import re
    import pexpect
    from django.db import connection

    # transform dump to change owner
    dump_file = fileinput.FileInput(path, inplace=True)
    db_user = settings.DATABASES["default"]["USER"]
    for line in dump_file:
        line = re.sub(
            "ALTER TABLE(.*)OWNER TO (.*);",
            f"ALTER TABLE\\1OWNER TO {db_user};",
            line.rstrip(),
        )
        print(line)

    # list and remove all tables
    with connection.cursor() as cursor:
        cursor.execute(SELECT_ALL_PUBLIC_TABLES_QUERY)
        tables = cursor.fetchall()
        for (table,) in tables:
            cursor.execute(table)

    # load the dump
    db_name = settings.DATABASES["default"]["NAME"]
    db_user = settings.DATABASES["default"]["USER"]
    db_password = settings.DATABASES["default"]["PASSWORD"]
    shell_cmd = f"psql {db_name} -U {db_user} < {path}"
    child = pexpect.spawn("/bin/bash", ["-c", shell_cmd])
    child.expect(f"Password for user {db_user}:")
    child.sendline(db_password)


def recover_database(db_file):
    # download latest db_file
    bucket = get_backup_bucket()
    key = bucket.get_key(db_file)
    if not key:
        raise ValueError("wrong input file db")
    key.get_contents_to_filename(DATABASE_BACKUP_FILE)

    if IS_POSTGRES:
        load_postgresql_dump(DATABASE_BACKUP_FILE)

    # we now assume sqlite DB
    # copy to database file
    shutil.copy(db_file_path, "db_before_recovery.sqlite")
    shutil.copy(DATABASE_BACKUP_FILE, db_file_path)
    os.remove(DATABASE_BACKUP_FILE)


def list_saved_databases():
    """Prints the backups to stdout."""
    bucket = get_backup_bucket()
    backup_keys = list(bucket.list())

    for backup_key in backup_keys:
        print(backup_key.key)


def db_name() -> str:
    return datetime.datetime.now().strftime(FILE_FORMAT)
