import ast
import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import User

from api.helper import get_cell_by_id, create_cell_lock, get_cell_lock_by_cell, remove_cell_lock, get_user, \
    reorder_columns, send_to_demon_proxy
from api.utils import send_cell_lock_update, send_cell_lock_remove, register_user, \
    un_register_user, get_online_users


class TableUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("table_list_updates", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("table_list_updates", self.channel_name)

    async def table_updated(self, event):
        await self.send_json({
            "type": "table_update",
            "id": event["data"]["id"],
            "entity": event["data"]["entity"],
        })

    async def table_created(self, event):
        await self.send_json({
            "type": "table_create",
            "id": event["data"]["id"],
            "entity": event["data"]["entity"],
        })


class CellUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        args_str = str(self.scope.get('query_string'))
        content = args_str[2:-1]
        args_str.split("b'")
        params = {}
        for pair in content.split('&'):
            if len(pair.split('=')) > 1:
                key, value = pair.split('=')
                params[key] = value
        user = await User.objects.aget(id=params.get("userId"))
        table_id = params.get('table_id')
        await register_user(user, table_id)
        online_users = await get_online_users(table_id)
        await self.accept()
        await self.channel_layer.group_add("cell_list_updates", self.channel_name)

        await self.send_json({
            "type": "get_online_users",
            "table_id": table_id,
            "users": json.dumps(online_users)
        })

    async def disconnect(self, close_code):
        args_str = str(self.scope.get('query_string'))
        content = args_str[2:-1]
        args_str.split("b'")
        params = {}
        for pair in content.split('&'):
            if len(pair.split('=')) > 1:
                key, value = pair.split('=')
                params[key] = value
        user = await User.objects.aget(id=params.get("userId"))
        table_id = params.get('table_id')
        await un_register_user(user, table_id)
        await self.channel_layer.group_discard("cell_list_updates", self.channel_name)

    async def cell_updated(self, event):
        await self.send_json({
            "type": "cell_update",
            "id": event["data"]["id"],
            "entity": event["data"]["entity"],
        })

    async def user_disconected(self, event):
        await self.send_json({
            "type": "user_disconected",
            "id": event["data"]["id"],
            "table_id": event["data"]["table_id"],
            "entity": event["data"]["entity"],
        })

    async def user_conected(self, event):
        await self.send_json({
            "type": "user_conected",
            "id": event["data"]["id"],
            "table_id": event["data"]["table_id"],
            "entity": event["data"]["entity"],
        })

    async def send_row(self, event):
        await self.send_json({
            "type": "send_row",
            "id": event["data"]["id"],
            "entity": event["data"]["entity"],
        })

    async def cells_updated(self, event):
        await self.send_json({
            "type": "cells_update",
            "entities": event["data"]["entities"],
        })

    async def user_online_updated(self, event):
        await self.send_json({
            "type": "user_online_updated",
            "entities": event["data"]["entities"],
        })

    async def receive(self, text_data):
        # {type: "update", cell_id: 123, value: "some val"}
        data = ast.literal_eval(text_data)
        if data["type"] == 'column_reorder':
           await reorder_columns(data["table_id"], data["old_index"], data["new_index"])


class CellLockUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("cell_lock_updates", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("cell_lock_updates", self.channel_name)

    async def cell_lock_updated(self, event):
        await self.send_json({
            "type": "cell_lock_update",
            "id": event["data"]["id"],
            "entity": event["data"]["entity"],
        })

    async def cell_lock_removed(self, event):
        await self.send_json({
            "type": "cell_lock_remove",
            "id": event["data"]["id"],
            "entity": event["data"]["entity"],
        })

    async def receive(self, text_data):
        # {type: "remove\create", cell_id: 123, user_id: 1}
        data = ast.literal_eval(text_data)
        cell_id = data["cell_id"]
        cell = await get_cell_by_id(cell_id)
        lock_type = data['type']
        # user = self.scope["user"]
        user = await get_user(data['user_id'])
        if user.is_anonymous:
            await self.close()
            return

        if lock_type == "create":
            # Перед созданием блокировки, удаляем все другие блокировки пользователя
            cell_lock = await create_cell_lock(cell, user)
            await send_cell_lock_update(cell_lock)
        elif lock_type == "remove":
            cell_lock = await get_cell_lock_by_cell(cell)
            if cell_lock:
                await send_cell_lock_remove(cell_lock)
                await remove_cell_lock(cell_lock)


class DemonConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("demon", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("demon", self.channel_name)

    async def send_signal(self, event):
        await self.send_json({
            "type": "demon",
            "username": event['data']['username'],
            "path": event['data']['path'],
        })

    async def receive(self, text_data):
        # {username: 123, path: 1}
        data = ast.literal_eval(text_data)
        username = data["username"]
        path = data["path"]
        await send_to_demon_proxy(username, path)
