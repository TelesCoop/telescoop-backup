import datetime
import os
import shutil
import subprocess

from django.conf import settings

import boto3

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
    SQLITE_DUMP_COMMAND = (
        """sqlite3 '{source_file}' ".backup '{backup_file}'" """.format(
            source_file=db_file_path, backup_file=DATABASE_BACKUP_FILE
        )
    )
    FILE_FORMAT = f"{DATE_FORMAT}_db.sqlite"
KEEP_N_DAYS = getattr(settings, "BACKUP_KEEP_N_DAYS", 31)
if getattr(settings, "BACKUP_USE_AWS", None) and (
    region := getattr(settings, "BACKUP_REGION", None)
):
    host = f"s3.{region}.amazonaws.com"
else:
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
    for root, dirs, files in os.walk(path):
        for file in files:
            path_no_base = os.path.join(root, file)
            dest = os.path.normpath(os.path.join(remote_path, path_no_base))
            backup_file(path_no_base, dest, connexion=connexion, skip_if_exists=True)


def dump_database():
    """Dump the database to a file."""
    if IS_POSTGRES:
        import pexpect

        db_name = settings.DATABASES["default"]["NAME"]
        db_user = settings.DATABASES["default"]["USER"]
        db_password = settings.DATABASES["default"].get("PASSWORD")
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


def get_backups(connexion=None):
    if connexion is None:
        connexion = boto_client()

    date_format = FILE_FORMAT

    backups = []

    for backup_key in connexion.list_objects(Bucket=BUCKET)["Contents"]:
        try:
            file_date = datetime.datetime.strptime(backup_key["Key"], date_format)
        except ValueError:
            # is not a database backup
            continue
        backups.append({"key": backup_key, "date": file_date})

    backups = sorted(backups, key=lambda backup: backup["date"])

    return backups


def load_postgresql_dump(path):
    import fileinput
    import re
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
    db_password = settings.DATABASES["default"].get("PASSWORD")
    shell_cmd = f"psql -d {db_name} -U {db_user} < {path} &> /dev/null"

    if db_password:
        import pexpect

        child = pexpect.spawn("/bin/bash", ["-c", shell_cmd])
        child.expect(f"Password for user {db_user}:")
        child.sendline(db_password)
        child.wait()
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

    with open(DATABASE_BACKUP_FILE, "wb") as f:
        f.write(key["Body"].read())

    if IS_POSTGRES:
        load_postgresql_dump(DATABASE_BACKUP_FILE)
        return

    # we now assume sqlite DB
    # copy to database file
    shutil.copy(db_file_path, "db_before_recovery.sqlite")
    shutil.copy(DATABASE_BACKUP_FILE, db_file_path)
    os.remove(DATABASE_BACKUP_FILE)


def list_saved_databases():
    """Prints the backups to stdout."""
    backups = get_backups()

    for backup in backups:
        print(backup["key"]["Key"])


def db_name() -> str:
    return datetime.datetime.now().strftime(FILE_FORMAT)
