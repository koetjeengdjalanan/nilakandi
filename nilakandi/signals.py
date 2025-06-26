import logging

from django.db.backends.signals import connection_created
from django.dispatch import receiver

logger = logging.getLogger("django.db")


@receiver(connection_created)
def log_db_connection(sender, connection, **kwargs):
    db_name = connection.settings_dict.get("NAME", "Unknown DB")
    db_user = connection.settings_dict.get("USER", "Unknown User")
    logger.debug(f"Database connection established: {db_name} as user {db_user}")
