import datetime
import os
import shutil
import subprocess
import re

from django.conf import settings

import boto3

IS_POSTGRES = any(
    db_type in settings.DATABASES["default"]["ENGINE"]
    for db_type in ["postgres", "postgis"]
)

DATE_FORMAT = "%Y-%m-%dT%H:%M"
DEFAULT_AUTH_VERSION = 2
DEFAULT_CONTAINER_NAME = "db-backups"
if IS_POSTGRES:
    COMPRESS_DATABASE_BACKUP = getattr(settings, "BACKUP_COMPRESS", False)
    if COMPRESS_DATABASE_BACKUP:
        DATABASE_BACKUP_FILE = os.path.join(settings.BASE_DIR, "compress.dump")
        FILE_FORMAT = f"{DATE_FORMAT}_postgres_backup.dump"
        BACKUP_RECOVER_N_WORKERS = getattr(settings, "BACKUP_RECOVER_N_WORKERS", 1)
    else:
        DATABASE_BACKUP_FILE = os.path.join(settings.BASE_DIR, "dump.sql")
        FILE_FORMAT = f"{DATE_FORMAT}_postgres_dump.sql"
    SELECT_ALL_PUBLIC_TABLES_QUERY = """select 'drop table if exists "' || tablename || '" cascade;' from pg_tables where schemaname = 'public';"""
else:
    db_file_path = settings.DATABASES["default"]["NAME"]
    DATABASE_BACKUP_FILE = os.path.join(os.path.dirname(db_file_path), "backup.sqlite")
    SQLITE_DUMP_COMMAND = (
        """sqlite3 '{source_file}' ".backup '{backup_file}'" """.format(
            source_file=db_file_path, backup_file=DATABASE_BACKUP_FILE
        )
    )
    FILE_FORMAT = f"{DATE_FORMAT}_db.sqlite"
ZIPPED_BACKUP_FILE = os.path.join(settings.BASE_DIR, "media.zip")
ZIPPED_MEDIA_FILE_FORMAT = f"{DATE_FORMAT}_media.zip"
KEEP_N_DAYS = getattr(settings, "BACKUP_KEEP_N_DAYS", 31)
region = getattr(settings, "BACKUP_REGION", None)
if getattr(settings, "BACKUP_USE_AWS", None) and region:
    host = f"s3.{region}.amazonaws.com"
else:
    region = region or "fr-par"
    host = getattr(settings, "BACKUP_HOST", "s3.fr-par.scw.cloud")
LAST_BACKUP_FILE = os.path.join(settings.BASE_DIR, ".telescoop_backup_last_backup")
BUCKET = settings.BACKUP_BUCKET


def boto_client():
    """Connect to AWS S3."""
    return boto3.client(
        "s3",
        aws_access_key_id=settings.BACKUP_ACCESS,
        aws_secret_access_key=settings.BACKUP_SECRET,
        endpoint_url=f"https://{host}",
        region_name=region,
    )


def backup_file(file_path: str, remote_key: str, connexion=None, skip_if_exists=False):
    """Backup backup_file on third-party server."""
    if connexion is None:
        connexion = boto_client()

    if skip_if_exists:
        try:
            connexion.head_object(Bucket=BUCKET, Key=remote_key)
            return
        except connexion.exceptions.ClientError as e:
            if e.response["Error"]["Code"] != "404":
                raise
    connexion.upload_file(file_path, BUCKET, remote_key)


def backup_folder(path: str, remote_path: str, connexion=None):
    """Recursively backup entire folder. Ignores paths that were already backup up."""
    if connexion is None:
        connexion = boto_client()
    number_of_files = sum([len(files) for root, dirs, files in os.walk(path)])
    if number_of_files > 100:
        print(
            "Warning: you are about to backup a large number of files. You may want to use --zipped option."
        )
    for root, dirs, files in os.walk(path):
        for file in files:
            path_no_base = os.path.join(root, file)
            dest = os.path.join(remote_path, os.path.relpath(path_no_base, start=path))
            backup_file(path_no_base, dest, connexion=connexion, skip_if_exists=True)


def dump_database():
    """Dump the database to a file."""
    if IS_POSTGRES:
        import pexpect

        db_name = settings.DATABASES["default"]["NAME"]
        db_user = settings.DATABASES["default"]["USER"]
        db_password = settings.DATABASES["default"].get("PASSWORD")
        if COMPRESS_DATABASE_BACKUP:
            shell_cmd = f"pg_dump -U {db_user} -d {db_name} -F c --no-acl -f {DATABASE_BACKUP_FILE}"
        else:
            shell_cmd = (
                f"pg_dump -d {db_name} -U {db_user} --inserts > {DATABASE_BACKUP_FILE}"
            )

        if db_password:
            child = pexpect.spawn("/bin/bash", ["-c", shell_cmd])
            child.expect("Password:")
            child.sendline(db_password)
            child.wait()
        else:
            subprocess.check_output(shell_cmd, shell=True)
    else:
        subprocess.check_output(SQLITE_DUMP_COMMAND, shell=True)


def remove_old_database_files():
    """Remove files older than KEEP_N_DAYS days."""
    connexion = boto_client()
    backups = get_backups(connexion)

    now = datetime.datetime.now()

    for backup in backups:
        if (now - backup["date"]).total_seconds() > KEEP_N_DAYS * 3600 * 24:
            print("removing old file {}".format(backup["key"]["Key"]))
            connexion.delete_object(Bucket=BUCKET, Key=backup["key"]["Key"])
        else:
            print("keeping {}".format(backup["key"]["Key"]))


def backup_media():
    media_folder = settings.MEDIA_ROOT
    backup_folder(media_folder, "media")


def backup_zipped_media(date=None):
    media_folder = settings.MEDIA_ROOT
    filename, extension = ZIPPED_BACKUP_FILE.split(".")
    shutil.make_archive(filename, extension, media_folder)

    backup_file(ZIPPED_BACKUP_FILE, zipped_media_file_name(date))
    os.remove(ZIPPED_BACKUP_FILE)


def recover_zipped_media(file_name=None):
    connexion = boto_client()
    if file_name is None or file_name == "latest":
        backups = get_backups(connexion, ZIPPED_MEDIA_FILE_FORMAT)
        if not len(backups):
            raise ValueError("Could not find any media backup")
        file_name = backups[-1]["key"]["Key"]

    key = connexion.get_object(Bucket=BUCKET, Key=file_name)
    if not key:
        raise ValueError(f"Wrong input file db {file_name}")

    connexion.download_file(Bucket=BUCKET, Key=file_name, Filename=ZIPPED_BACKUP_FILE)

    shutil.unpack_archive(ZIPPED_BACKUP_FILE, settings.MEDIA_ROOT)
    os.remove(ZIPPED_BACKUP_FILE)


def backup_database_and_media(zipped_media=True):
    date = datetime.datetime.now()
    backup_database(date)
    if zipped_media:
        backup_zipped_media(date)
    else:
        backup_media()


def recover_database_and_media(file_name=None, db_file=None):
    recover_database(db_file)
    recover_zipped_media(file_name)


def upload_to_online_backup(date=None):
    """Upload the database file online."""
    backup_file(file_path=DATABASE_BACKUP_FILE, remote_key=db_name(date))


def update_latest_backup():
    with open(LAST_BACKUP_FILE, "w") as fh:
        fh.write(datetime.datetime.now().strftime(DATE_FORMAT))


def get_latest_backup():
    if not os.path.isfile(LAST_BACKUP_FILE):
        return None
    with open(LAST_BACKUP_FILE, "r") as fh:
        return datetime.datetime.strptime(fh.read().strip(), DATE_FORMAT)


def backup_database(date=None):
    """Main function."""
    dump_database()
    upload_to_online_backup(date)
    remove_old_database_files()
    update_latest_backup()


def delete_files(connexion=None, file_regex=None):
    if connexion is None:
        connexion = boto_client()

    regex = re.compile(file_regex)
    for backup_key in connexion.list_objects_v2(Bucket=BUCKET)["Contents"]:
        if regex.match(backup_key["Key"]):
            connexion.delete_object(Bucket=BUCKET, Key=backup_key["Key"])


def get_backups(connexion=None, date_format=FILE_FORMAT):
    if connexion is None:
        connexion = boto_client()
    backups = []

    for backup_key in connexion.list_objects_v2(Bucket=BUCKET)["Contents"]:
        try:
            file_date = datetime.datetime.strptime(backup_key["Key"], date_format)
        except ValueError:
            # is not a database backup
            continue
        backups.append({"key": backup_key, "date": file_date})

    backups = sorted(backups, key=lambda backup: backup["date"])

    return backups


def prepare_sql_dump(path, db_name, db_user):
    import fileinput
    import re
    from django.db import connection

    # transform dump to change owner
    dump_file = fileinput.FileInput(path, inplace=True)
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

    shell_cmd = f"psql -d {db_name} -U {db_user} < {path} &> /dev/null"
    return (shell_cmd, f"Password for user {db_user}:")


def prepare_compress_dump(path, db_name, db_user):
    shell_cmd = f"pg_restore -U {db_user} --dbname {db_name} -v {path} --jobs {BACKUP_RECOVER_N_WORKERS} --clean --if-exists --no-owner --role={db_user}"
    return (shell_cmd, "Password:")


def load_postgresql_dump(path):
    # load the dump
    db_name = settings.DATABASES["default"]["NAME"]
    db_user = settings.DATABASES["default"]["USER"]
    db_password = settings.DATABASES["default"].get("PASSWORD")

    if COMPRESS_DATABASE_BACKUP:
        shell_cmd, expected_text = prepare_compress_dump(path, db_name, db_user)
    else:
        shell_cmd, expected_text = prepare_sql_dump(path, db_name, db_user)

    print("command:", shell_cmd)

    if db_password:
        import pexpect

        child = pexpect.spawn("/bin/bash", ["-c", shell_cmd])
        child.expect(expected_text)
        child.sendline(db_password)
        child.expect(pexpect.EOF, timeout=None) # pg_restore is terminating silently
    else:
        subprocess.check_output(shell_cmd, shell=True)


def recover_database(db_file=None):
    """
    Replace current database with target backup.

    If db_file is None or 'latest', recover latest database.
    """
    connexion = boto_client()

    if db_file is None or db_file == "latest":
        backups = get_backups()
        if not len(backups):
            raise ValueError("Could not find any backup")
        db_file = backups[-1]["key"]["Key"]

    key = connexion.get_object(Bucket=BUCKET, Key=db_file)
    if not key:
        raise ValueError(f"Wrong input file db {db_file}")

    connexion.download_file(Bucket=BUCKET, Key=db_file, Filename=DATABASE_BACKUP_FILE)

    if IS_POSTGRES:
        load_postgresql_dump(DATABASE_BACKUP_FILE)
        return

    # we now assume sqlite DB
    # copy to database file
    shutil.copy(db_file_path, "db_before_recovery.sqlite")
    shutil.copy(DATABASE_BACKUP_FILE, db_file_path)
    os.remove(DATABASE_BACKUP_FILE)


def list_backup(date_format):
    backups = get_backups(date_format=date_format)

    for backup in backups:
        print(backup["key"]["Key"])


def list_saved_databases():
    list_backup(date_format=FILE_FORMAT)


def list_saved_zipped_media():
    list_backup(date_format=ZIPPED_MEDIA_FILE_FORMAT)


def db_name(date=None) -> str:
    if date is None:
        date = datetime.datetime.now()
    return date.strftime(FILE_FORMAT)


def zipped_media_file_name(date=None) -> str:
    if date is None:
        date = datetime.datetime.now()
    return date.strftime(ZIPPED_MEDIA_FILE_FORMAT)
