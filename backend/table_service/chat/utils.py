import json

from asgiref.sync import sync_to_async, async_to_sync
from channels.layers import get_channel_layer

from chat.serializers import MessageSerializer, ChatSerializer


@sync_to_async(thread_sensitive=False)
def get_chat_data(instance=None):
    chat = instance[0]
    channel_layer = get_channel_layer()

    chat_serializer = ChatSerializer(chat)

    messages = []
    for message in chat_serializer.get_messages(chat):
        message_serializer = MessageSerializer(message)
        message_serialized_data = message_serializer.data
        messages.append(message_serialized_data)

    async_to_sync(channel_layer.group_send)(
        "chats",
        {
            "type": "get.chat.data",
            "data": {
                "table_id": chat.table.id if chat else None,
                "chat_id": chat.id if chat else None,
                "messages": json.dumps(messages),
            }
        }
    )


@sync_to_async(thread_sensitive=False)
def get_user_typing(table_id, user_name):
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "chats",
        {
            "type": "get.user.typing",
            "data": {
                "user_name": user_name,
                "table_id": table_id,
            }
        }
    )
