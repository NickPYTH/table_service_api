from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from api.helper import normalize_columns
from api.utils import send_user_disconected, send_user_conected
from tables.models import Column, TableUserOnline


@receiver(post_delete, sender=Column)
def track_column_deletion(sender, instance, **kwargs):
    normalize_columns(instance.table_id)


@receiver(post_delete, sender=TableUserOnline)
def track_user_online_deletion(sender, instance, **kwargs):
    send_user_disconected(instance.table.id, instance.user)


@receiver(post_save, sender=TableUserOnline)
def track_user_online_save(sender, instance, **kwargs):
    send_user_conected(instance.table.id, instance.user)
