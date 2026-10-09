from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from api.serializers import TableDetailSerializer, CellSerializer, CellLockSerializer, RowSerializer, UserSerializer
from tables.models import TableUserOnline, Table


@sync_to_async(thread_sensitive=False)
def get_user_from_session_id(session_id):
    try:
        session = Session.objects.get(session_key=session_id)
        session_data = session.get_decoded()

        # Получаем ID пользователя из сессии
        user_id = session_data.get('_auth_user_id')

        if user_id:
            return User.objects.get(id=user_id)
    except (Session.DoesNotExist, User.DoesNotExist):
        return None

@sync_to_async(thread_sensitive=False)
def register_user(user, table_id):
    table = Table.objects.get(id=table_id)
    if TableUserOnline.objects.filter(user=user, table=table).count() == 0:
        online_record = TableUserOnline(user=user, table=table)
        online_record.save()

@sync_to_async(thread_sensitive=False)
def get_online_users(table_id):
    table = Table.objects.get(id=table_id)
    current_online = []
    for online in TableUserOnline.objects.filter(table=table):
        serializer = UserSerializer(online.user)
        serialized_data = serializer.data
        current_online.append(serialized_data)
    return current_online

@sync_to_async(thread_sensitive=False)
def un_register_user(user, table_id):
    table = Table.objects.get(id=table_id)
    TableUserOnline.objects.filter(user=user, table=table).delete()

def send_table_update(instance=None):
    channel_layer = get_channel_layer()

    serializer = TableDetailSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "table_list_updates",
        {
            "type": "table.updated",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "message": "Table list updated",
            }
        }
    )

def send_table_create(instance=None):
    channel_layer = get_channel_layer()

    serializer = TableDetailSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "table_list_updates",
        {
            "type": "table.created",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "message": "Table list created",
            }
        }
    )

def send_cell_update(instance=None):
    channel_layer = get_channel_layer()

    serializer = CellSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "cell_list_updates",
        {
            "type": "cell.updated",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "message": "Cell updated",
            }
        }
    )

def send_row(instance=None):
    channel_layer = get_channel_layer()

    serializer = RowSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "cell_list_updates",
        {
            "type": "send.row",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "message": "Row created",
            }
        }
    )

def send_cells_update(cells_list=None):
    channel_layer = get_channel_layer()

    serialized_data = []

    for cell in cells_list:
        serializer = CellSerializer(cell)
        serialized_data.append(serializer.data)

    async_to_sync(channel_layer.group_send)(
        "cell_list_updates",
        {
            "type": "cells.updated",
            "data": {
                "entities": serialized_data,
                "message": "Cells updated",
            }
        }
    )

@sync_to_async(thread_sensitive=False)
def send_cell_lock_update(instance=None):
    channel_layer = get_channel_layer()

    serializer = CellLockSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "cell_lock_updates",
        {
            "type": "cell.lock.updated",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "message": "Cell lock updated",
            }
        }
    )

@sync_to_async(thread_sensitive=False)
def send_cell_lock_remove(instance=None):
    channel_layer = get_channel_layer()

    serializer = CellLockSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "cell_lock_updates",
        {
            "type": "cell.lock.removed",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "message": "Cell lock removed",
            }
        }
    )

def send_to_demon(username, path):
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "demon",
        {
            "type": "send.signal",
            "data": {
                "username": username,
                "path": path,
            }
        }
    )

def send_user_disconected(table_id, instance=None):
    channel_layer = get_channel_layer()

    serializer = UserSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "cell_list_updates",
        {
            "type": "user.disconected",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "table_id": table_id,
                "message": "User disconected",
            }
        }
    )

def send_user_conected(table_id, instance=None):
    channel_layer = get_channel_layer()

    serializer = UserSerializer(instance)
    serialized_data = serializer.data

    async_to_sync(channel_layer.group_send)(
        "cell_list_updates",
        {
            "type": "user.conected",
            "data": {
                "id": instance.id if instance else None,
                "entity": serialized_data,
                "table_id": table_id,
                "message": "User conected",
            }
        }
    )
