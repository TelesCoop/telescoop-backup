from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class BackupStorage(S3Boto3Storage):
    bucket_name = getattr(settings, "BACKUP_S3_BUCKET_NAME")
    access_key = getattr(settings, "BACKUP_S3_ACCESS_KEY")
    secret_key = getattr(settings, "BACKUP_S3_SECRET_KEY")

    region_name = getattr(settings, "BACKUP_S3_REGION_NAME")
    endpoint_url =  getattr(settings, "BACKUP_S3_ENDPOINT_URL")
    signature_version = getattr(settings, "BACKUP_S3_SIGNATURE")

