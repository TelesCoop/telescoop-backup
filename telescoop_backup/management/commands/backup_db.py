import sys

from django.core.management import BaseCommand

from telescoop_backup.backup import (
    backup_database,
    list_saved_databases,
    recover_database,
    backup_media,
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

    def add_arguments(self, parser):
        parser.add_argument(
            "action", type=str, help="on of `backup`, `list` or `recover`"
        )

        parser.add_argument(
            "database_file",
            nargs="?",
            help="if action is `recover`, name of database file to recover from",
        )

    def handle(self, *args, **options):
        if not options["action"]:
            usage_error()

        if options["action"] in ["backup", "backup_db"]:
            backup_database()
        elif options["action"] == "backup_media":
            backup_media()
        elif options["action"] == "list":
            list_saved_databases()
        elif options["action"] == "recover":
            if not len(sys.argv) > 3:
                usage_error()
            db_file = sys.argv[3]
            recover_database(db_file)
        else:
            usage_error()


def usage_error():
    print(COMMAND_HELP)
    exit(1)
