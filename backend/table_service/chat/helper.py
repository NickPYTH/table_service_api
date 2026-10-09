from asgiref.sync import sync_to_async

from chat.models import Chat, Message
from django.contrib.auth.models import User

from tables.models import Table


@sync_to_async(thread_sensitive=False)
def get_chat(table_id):
    return Chat.objects.get_or_create(table_id=table_id)

@sync_to_async(thread_sensitive=False)
def create_message(table_id, user_id, message):
    user = User.objects.get(id=user_id)
    table = Table.objects.get(id=table_id)
    chat = Chat.objects.get(table=table)
    message = Message.objects.create(
        user=user,
        text=message,
        chat=chat,
    )
    message.save()
