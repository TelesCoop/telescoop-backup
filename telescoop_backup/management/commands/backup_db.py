from django.core.management import BaseCommand

class Command(BaseCommand):
    help = "Backup sqlite database to an OpenStack Object Storage"

    def handle(self, *args, **options):
        import_data()
