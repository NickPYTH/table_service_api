import datetime

from django.contrib.auth.models import User
from django.db import models

from tables.models import Table


class Chat(models.Model):
    id = models.AutoField(primary_key=True)
    table = models.ForeignKey(Table, on_delete=models.CASCADE)

class Message(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField(max_length=500)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    send_at = models.DateTimeField(default=datetime.datetime.now())
    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    edit_at = models.DateTimeField(default=datetime.datetime.now(), blank=True, null=True)