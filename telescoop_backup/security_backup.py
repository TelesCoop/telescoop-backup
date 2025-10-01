from django.conf import settings
from botocore.exceptions import ClientError

from .backup import (
    boto_client,
    BackupType,
    BUCKET,
    _list_objects_paginated,
    _file_exists_in_bucket,
    _copy_objects_with_progress,
)


# Security backup settings
SECURITY_BACKUP_PATH_LIST = getattr(settings, "SECURITY_BACKUP_PATH_LIST", [])
SECURITY_BACKUP_BUCKET = getattr(settings, "SECURITY_BACKUP_BUCKET", None)
SECURITY_BACKUP_DESTINATION = (
    getattr(settings, "SECURITY_BACKUP_DESTINATION", None) or "security_backup"
)


def _get_objects_for_backup_paths(primary_connexion, backup_paths):
    """Get objects from primary bucket using prefix filtering for each backup path."""
    matching_objects = []

    for backup_path in backup_paths:
        # Remove leading slash if present for consistent comparison
        backup_path = backup_path.lstrip("/")
        print(f"Fetching objects with prefix: {backup_path}")

        try:
            path_objects = _list_objects_paginated(
                primary_connexion, BUCKET, backup_path
            )
            if path_objects:
                matching_objects.extend(path_objects)
                print(f"Found {len(path_objects)} objects for prefix '{backup_path}'")
            else:
                print(f"No objects found for prefix '{backup_path}'")
        except ClientError as e:
            print(f"Error fetching objects for prefix '{backup_path}': {e}")
            continue

    return matching_objects


def _get_existing_security_files(security_connexion):
    """Get set of existing files in security bucket."""
    try:
        all_security_objects = _list_objects_paginated(
            security_connexion,
            SECURITY_BACKUP_BUCKET,
            SECURITY_BACKUP_DESTINATION + "/",
        )
        existing_files = {obj["Key"] for obj in all_security_objects}
        print(f"Found {len(existing_files)} existing files in security bucket")
        return existing_files
    except ClientError as e:
        print(f"Warning: Could not list existing security bucket files: {e}")
        return set()


def security_backup(overwrite=False):
    """Copy files from first bucket to second bucket for security backup, filtering by SECURITY_BACKUP_PATH_LIST."""
    if not SECURITY_BACKUP_PATH_LIST:
        print("No paths defined in SECURITY_BACKUP_PATH_LIST, skipping security backup")
        return

    if not SECURITY_BACKUP_BUCKET:
        print("No SECURITY_BACKUP_BUCKET defined, skipping security backup upload")
        return

    # Create connections to both buckets
    primary_connexion = boto_client(BackupType.MAIN)
    security_connexion = boto_client(BackupType.SECURITY)

    try:
        # Get objects from primary bucket using prefix filtering for each backup path
        matching_objects = _get_objects_for_backup_paths(
            primary_connexion, SECURITY_BACKUP_PATH_LIST
        )

        if not matching_objects:
            print(f"No objects found matching any paths: {SECURITY_BACKUP_PATH_LIST}")
            return

        print(f"Total: found {len(matching_objects)} objects matching specified paths")

        # If not overwriting, get existing files in security bucket to avoid unnecessary checks
        existing_files = set()
        if not overwrite:
            existing_files = _get_existing_security_files(security_connexion)

        # Filter objects that actually need to be copied
        files_to_copy = []
        for obj in matching_objects:
            source_key = obj["Key"]
            dest_key = f"{SECURITY_BACKUP_DESTINATION}/{source_key}"

            if not overwrite and dest_key in existing_files:
                continue

            files_to_copy.append(obj)

        if not files_to_copy:
            print(
                "No files need to be copied (all files already exist in security bucket)"
            )
            return

        print(f"Need to copy {len(files_to_copy)} files to security bucket")

        def copy_to_security_bucket(obj, pbar):
            source_key = obj["Key"]
            dest_key = f"{SECURITY_BACKUP_DESTINATION}/{source_key}"
            pbar.set_postfix_str(f"Processing {source_key}")

            try:
                copy_source = {"Bucket": BUCKET, "Key": source_key}
                pbar.write(f"Copying {source_key} to security bucket as {dest_key}")
                security_connexion.copy_object(
                    CopySource=copy_source,
                    Bucket=SECURITY_BACKUP_BUCKET,
                    Key=dest_key,
                )
                return True
            except ClientError as e:
                pbar.write(f"Error copying {source_key}: {e}")
                return False

        _copy_objects_with_progress(
            files_to_copy, copy_to_security_bucket, "Copying files to security bucket"
        )

    except ClientError as e:
        print(f"Error listing objects from primary bucket: {e}")
        return


def restore_security_backup(overwrite=False):
    """Copy files from security bucket back to first bucket."""
    if not SECURITY_BACKUP_BUCKET:
        print("No SECURITY_BACKUP_BUCKET defined, skipping security backup restore")
        return

    # Create connections to both buckets
    primary_connexion = boto_client(BackupType.MAIN)
    security_connexion = boto_client(BackupType.SECURITY)

    try:
        # Get all objects from the security bucket with the security backup prefix using pagination
        all_objects = _list_objects_paginated(
            security_connexion,
            SECURITY_BACKUP_BUCKET,
            SECURITY_BACKUP_DESTINATION + "/",
        )

        if not all_objects:
            print("No objects found in security backup bucket")
            return

        print(f"Found {len(all_objects)} objects in security backup bucket")

        def restore_from_security_bucket(obj, pbar):
            security_key = obj["Key"]

            # Remove the security backup prefix to get the original key
            if not security_key.startswith(SECURITY_BACKUP_DESTINATION + "/"):
                pbar.write(f"Skipping {security_key} - not in security backup prefix")
                return False

            original_key = security_key[len(SECURITY_BACKUP_DESTINATION) + 1 :]
            pbar.set_postfix_str(f"Processing {original_key}")

            # Check if file already exists in primary bucket
            if not overwrite and _file_exists_in_bucket(
                primary_connexion, BUCKET, original_key
            ):
                pbar.write(
                    f"File {original_key} already exists in primary bucket, skipping (overwrite=False)"
                )
                return False

            try:
                # Copy object from security bucket to primary bucket
                copy_source = {"Bucket": SECURITY_BACKUP_BUCKET, "Key": security_key}
                pbar.write(
                    f"Restoring {security_key} to primary bucket as {original_key}"
                )
                primary_connexion.copy_object(
                    CopySource=copy_source,
                    Bucket=BUCKET,
                    Key=original_key,
                )
                return True
            except ClientError as e:
                pbar.write(f"Error restoring {security_key}: {e}")
                return False

        _copy_objects_with_progress(
            all_objects,
            restore_from_security_bucket,
            "Restoring files from security bucket",
        )

    except ClientError as e:
        print(f"Error listing objects from security backup bucket: {e}")
        return
