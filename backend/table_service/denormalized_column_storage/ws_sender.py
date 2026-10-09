from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def send_cell_update(data):
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "update_service",
        {
            "type": "cell.updated",
            "data": {
                "entity": data,
                "message": "Cell updated",
            }
        }
    )
# xs
