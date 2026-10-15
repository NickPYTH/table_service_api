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

def send_row_insert(data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "update_service",
        {
            "type": "row.inserted",
            "data": {
                "entity": data,
                "message": "Row inserted",
            }
        }
    )

def send_column_insert(data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "update_service",
        {
            "type": "column.inserted",
            "data": {
                "entity": data,
                "message": "Column inserted",
            }
        }
    )
