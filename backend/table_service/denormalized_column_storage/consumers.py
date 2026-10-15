from channels.generic.websocket import AsyncJsonWebsocketConsumer


class DenormalizedColumnStorageConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("update_service", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("update_service", self.channel_name)

    async def cell_updated(self, event):
        await self.send_json({
            "type": "cell_update",
            "entity": event["data"]["entity"],
        })

    async def row_inserted(self, event):
        await self.send_json({
            "type": "row_insert",
            "entity": event["data"]["entity"],
        })

    async def column_inserted(self, event):
        await self.send_json({
            "type": "column_insert",
            "entity": event["data"]["entity"],
        })