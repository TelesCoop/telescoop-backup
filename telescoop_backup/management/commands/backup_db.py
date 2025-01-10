import sys

from django.core.management import BaseCommand

from telescoop_backup.backup import (
    backup_database,
    list_saved_databases,
    recover_database,
    backup_media, backup_database_and_media, recover_database_and_media, backup_zipped_media, list_saved_zipped_media,
    recover_zipped_media,
)

COMMAND_HELP = """

usage:
     `python backup_database.py backup`
         to back up current db
  or `python backup_database.py list`
         to list already backed up files
  or `python backup_database.py recover xx_db@YYYY-MM-DDTHH:MM.sqlite`
         to recover from specific file

"""


class Command(BaseCommand):
    help = "Backup database on AWS"
    missing_args_message = COMMAND_HELP

    def not_implemented(self):
        self.stdout.write("Not implemented yet")

    def add_arguments(self, parser):
        parser.add_argument(
            "action", type=str, help="on of `backup`, `list` or `recover`"
        )

        parser.add_argument(
            "file",
            nargs="?",
            help="if action is `recover`, name of file to recover from",
        )

        parser.add_argument(
            "timestamp",
            nargs="?",
            help="if action is `recover`, timestamp of database file to recover from",
        )
        parser.add_argument(
            "--zipped",
            action='store_true',
            help="use this to have zipped media files",
        )

    def handle(self, *args, **options):
        if not options["action"]:
            usage_error()

        is_zipped = options["zipped"]
        if options["action"] in ["backup", "backup_db"]:
            backup_database()
        elif options["action"] == "backup_media":
            if is_zipped:
                backup_zipped_media()
            else:
                backup_media()
        elif options["action"] == "backup_db_and_media":
            backup_database_and_media()
        elif options["action"] == "list":
            list_saved_databases()
        elif options["action"] == "list_media":
            if is_zipped:
                list_saved_zipped_media()
            else:
                self.not_implemented()
        elif options["action"] == "recover":
            if not len(sys.argv) > 3:
                usage_error()
            db_file = sys.argv[3]
            recover_database(db_file)
        elif options["action"] == "recover_media":
            file = options.get("file")
            if is_zipped:
                recover_zipped_media(file)
            else:
                self.not_implemented()
        elif options["action"] == "recover_db_and_media":
            timestamp = options.get("timestamp")
            recover_database_and_media(timestamp)
        else:
            usage_error()


def usage_error():
    print(COMMAND_HELP)
    exit(1)
