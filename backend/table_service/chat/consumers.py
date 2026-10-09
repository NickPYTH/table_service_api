import ast

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat.helper import get_chat, create_message
from chat.utils import get_chat_data, get_user_typing


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("chats", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("chats", self.channel_name)

    async def get_chat_data(self, event):
        await self.send_json({
            "type": "get_chat_data",
            "chat_id": event["data"]["chat_id"],
            "table_id": event["data"]["table_id"],
            "messages": event["data"]["messages"],
        })

    async def get_user_typing(self, event):
        await self.send_json({
            "type": "user_typing",
            "table_id": event["data"]["table_id"],
            "user_name": event["data"]["user_name"],
        })

    async def receive(self, text_data):
        # {type: "get_chat_data", table_id: 123}
        data = ast.literal_eval(text_data)
        if data["type"] == "get_chat_data":
            table_id = data["table_id"]
            chat = await get_chat(table_id)
            await get_chat_data(chat)
        elif data["type"] == "send_message":
            table_id = data["table_id"]
            user_id = data["user_id"]
            message = data["message"]
            await create_message(table_id, user_id, message)
            chat = await get_chat(table_id)
            await get_chat_data(chat)
        elif data["type"] == "user_typing":
            table_id = data["table_id"]
            user_name = data["user_name"]
            await get_user_typing(table_id, user_name)
        else:
            pass
