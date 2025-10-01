import datetime
import os
import shutil
import subprocess
import re

from django.conf import settings
from tqdm import tqdm
from enum import Enum
import humanize

import boto3
from botocore.exceptions import ClientError


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
KEEP_N_DAYS = getattr(settings, "BACKUP_KEEP_N_DAYS", 31)
region = getattr(settings, "BACKUP_REGION", None)
if getattr(settings, "BACKUP_USE_AWS", None) and region:
    host = f"s3.{region}.amazonaws.com"
else:
    region = region or "fr-par"
    host = getattr(settings, "BACKUP_HOST", "s3.fr-par.scw.cloud")
LAST_BACKUP_FILE = os.path.join(settings.BASE_DIR, ".telescoop_backup_last_backup")
BUCKET = settings.BACKUP_BUCKET

# Security backup settings
SECURITY_BACKUP_HOST = getattr(settings, "SECURITY_BACKUP_HOST", host)
SECURITY_BACKUP_REGION = getattr(settings, "SECURITY_BACKUP_REGION", region)
MAX_PAGINATION_ITERATIONS = getattr(settings, "BACKUP_MAX_PAGINATION_ITERATIONS", 10000)


class BackupType(Enum):
    MAIN = "main"
    SECURITY = "security"


CLIENT_PARAMS_BY_BACKUP = {
    BackupType.MAIN: {
        "endpoint_url": f"https://{host}",
        "region_name": region,
    },
    BackupType.SECURITY: {
        "endpoint_url": f"https://{SECURITY_BACKUP_HOST}",
        "region_name": SECURITY_BACKUP_REGION,
    },
}


def boto_client(backup_type=BackupType.MAIN):
    """Connect to AWS S3."""

    return boto3.client(
        "s3",
        aws_access_key_id=settings.BACKUP_ACCESS,
        aws_secret_access_key=settings.BACKUP_SECRET,
        **CLIENT_PARAMS_BY_BACKUP[backup_type],
    )


def _list_objects_paginated(connexion, bucket, prefix=""):
    """List all objects in a bucket with pagination support."""
    all_objects = []
    continuation_token = None
    iteration_count = 0

    while iteration_count < MAX_PAGINATION_ITERATIONS:
        list_kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            list_kwargs["ContinuationToken"] = continuation_token

        objects = connexion.list_objects_v2(**list_kwargs)

        if "Contents" in objects:
            all_objects.extend(objects["Contents"])

        has_more_objects = objects.get("IsTruncated", False)
        continuation_token = objects.get("NextContinuationToken")

        # Check if there are more objects to fetch
        if not (has_more_objects and continuation_token):
            break

        iteration_count += 1

    if iteration_count >= MAX_PAGINATION_ITERATIONS:
        print(
            f"Warning: Reached maximum iteration limit ({MAX_PAGINATION_ITERATIONS}) in _list_objects_paginated"
        )

    return all_objects


def _file_exists_in_bucket(connexion, bucket, key):
    """Check if a file exists in the bucket."""
    try:
        connexion.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def _copy_objects_with_progress(objects, copy_func, progress_desc):
    """Copy objects with progress bar and error handling."""
    with tqdm(objects, desc=progress_desc) as pbar:
        for obj in pbar:
            success = copy_func(obj, pbar)
            if success:
                pbar.write(f"Successfully processed {obj.get('Key', 'object')}")


def backup_file(file_path: str, remote_key: str, connexion=None, skip_if_exists=False):
    """Backup backup_file on third-party server."""
    if connexion is None:
        connexion = boto_client()

    if skip_if_exists and _file_exists_in_bucket(connexion, BUCKET, remote_key):
        return
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
            env = os.environ.copy()
            env["PGPASSWORD"] = db_password
            subprocess.check_output(shell_cmd, shell=True, env=env)
        else:
            subprocess.check_output(shell_cmd, shell=True)
    else:
        subprocess.check_output(SQLITE_DUMP_COMMAND, shell=True)


def remove_old_database_files():
    """Remove files older than KEEP_N_DAYS days."""
    connexion = boto_client(BackupType.MAIN)
    backups = get_backups(connexion)

    now = datetime.datetime.now()

    for backup in backups:
        try:
            if (now - backup["date"]).total_seconds() > KEEP_N_DAYS * 3600 * 24:
                print("removing old file {}".format(backup["key"]["Key"]))
                connexion.delete_object(Bucket=BUCKET, Key=backup["key"]["Key"])
            else:
                print("keeping {}".format(backup["key"]["Key"]))
        except ClientError:
            print("error removing {}, ignoring".format(backup["key"]["Key"]))


def upload_to_online_backup(date=None):
    """Upload the database file online."""
    backup_file(
        file_path=DATABASE_BACKUP_FILE,
        remote_key=db_name(date),
        connexion=boto_client(BackupType.MAIN),
    )


def update_latest_backup():
    """Update the timestamp of the latest backup."""
    with open(LAST_BACKUP_FILE, "w") as fh:
        fh.write(datetime.datetime.now().strftime(DATE_FORMAT))


def get_latest_backup():
    """Get the timestamp of the latest backup."""
    if not os.path.isfile(LAST_BACKUP_FILE):
        return None
    with open(LAST_BACKUP_FILE, "r") as fh:
        return datetime.datetime.strptime(fh.read().strip(), DATE_FORMAT)


def backup_database(date=None):
    """Backup the database."""
    dump_database()
    upload_to_online_backup(date)
    remove_old_database_files()
    update_latest_backup()


def delete_files(connexion=None, file_regex=None):
    """Delete files matching a regex pattern."""
    if connexion is None:
        connexion = boto_client()

    regex = re.compile(file_regex)
    for backup_key in connexion.list_objects_v2(Bucket=BUCKET)["Contents"]:
        if regex.match(backup_key["Key"]):
            connexion.delete_object(Bucket=BUCKET, Key=backup_key["Key"])


def get_backups(connexion=None, date_format=FILE_FORMAT):
    """Get list of all backups with date and size information."""
    if connexion is None:
        connexion = boto_client()
    backups = []

    for backup_key in connexion.list_objects_v2(Bucket=BUCKET)["Contents"]:
        try:
            file_date = datetime.datetime.strptime(backup_key["Key"], date_format)
        except ValueError:
            # is not a database backup
            continue
        backups.append({
            "key": backup_key,
            "date": file_date,
            "size": backup_key.get("Size", 0),
        })

    backups = sorted(backups, key=lambda backup: backup["date"])

    return backups


def prepare_sql_dump(path, db_name, db_user):
    """Prepare SQL dump for loading."""
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
    """Prepare compressed dump for loading."""
    shell_cmd = f"pg_restore -U {db_user} --dbname {db_name} -v {path} --jobs {BACKUP_RECOVER_N_WORKERS} --clean --if-exists --no-owner --role={db_user}"
    return (shell_cmd, "Password:")


def load_postgresql_dump(path):
    """Load PostgreSQL dump from file."""
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
       env = os.environ.copy()
       env["PGPASSWORD"] = db_password
       subprocess.check_output(shell_cmd, shell=True, env=env)
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


def list_backups(date_format):
    """List backups with a specific date format and human-readable sizes."""
    backups = get_backups(date_format=date_format)

    for backup in backups:
        size_human = humanize.naturalsize(backup["size"], binary=True)
        print(f"{backup['key']['Key']} ({size_human})")


def list_saved_databases():
    """List all saved database backups."""
    list_backups(date_format=FILE_FORMAT)


def db_name(date=None) -> str:
    """Generate filename for database backup."""
    if date is None:
        date = datetime.datetime.now()
    return date.strftime(FILE_FORMAT)
