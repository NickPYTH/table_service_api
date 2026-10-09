from rest_framework import serializers

from chat.models import Chat, Message

from api.serializers import TableDetailSerializer, UserSerializer

class MessageSerializer(serializers.ModelSerializer):
    send_at_formatted = serializers.SerializerMethodField()
    edit_at_formatted = serializers.SerializerMethodField()
    user_info = UserSerializer(source='user', read_only=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'user',
            'user_info',
            'text',
            'chat',
            'send_at',
            'send_at_formatted',
            'is_deleted',
            'is_edited',
            'edit_at',
            'edit_at_formatted'
        ]
        read_only_fields = ['id', 'send_at', 'edit_at']

    def get_send_at_formatted(self, obj):
        if obj.send_at:
            return obj.send_at.strftime('%d.%m.%Y')
        return None

    def get_edit_at_formatted(self, obj):
        if obj.edit_at and obj.is_edited:
            return obj.edit_at.strftime('%d.%m.%Y')
        return None

class ChatSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    table = TableDetailSerializer(read_only=True)
    messages = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = '__all__'

    def get_messages(self, obj):
        return Message.objects.filter(chat_id=obj.id)
