from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from denormalized_column_storage.models import TableV2, ColumnV2, ColumnV2SelectValues
from denormalized_column_storage.request_validate import get_column_request_validate, update_column_request_validate, \
    insert_column_request_validate
from denormalized_column_storage.utils import col_letter, rename_column_sql, insert_column_sql
from denormalized_column_storage.ws_sender import send_column_insert


@api_view(['GET'])
def get_columns_by_table(request):
    table_id = request.GET.get('table_id')
    table = TableV2.objects.get(id=table_id)
    response_data = []
    for column in ColumnV2.objects.filter(table=table).order_by('position'):
        response_data.append({
            "id": column.id,
            "position": column.position,
            "system_name": column.system_name,
            "alternative_name": column.alternative_name,
            "type": column.type,
            'required': column.required,
            'hidden': column.hidden,
            'readonly': column.readonly
        })
    return Response(response_data)


@api_view(['GET'])
def get_column(request):
    table_id, system_name = get_column_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    column = ColumnV2.objects.get(table=table, system_name=system_name)
    return Response({
        'id': column.id,
        'position': column.position,
        'table_id': column.table.id,
        'system_name': column.system_name,
        'alternative_name': column.alternative_name,
        'type': column.type,
        'required': column.required,
        'hidden': column.hidden,
        'readonly': column.readonly
    })


@api_view(['POST'])
def update_column(request):
    table_id, column_system_name, column_alternative_name, column_type, hidden, required, readonly = update_column_request_validate(
        request)
    table = TableV2.objects.get(id=table_id)
    column = ColumnV2.objects.get(table=table, system_name=column_system_name)
    column.type = column_type
    column.alternative_name = column_alternative_name
    column.readonly = readonly
    column.required = required
    column.hidden = hidden
    column.save()
    return Response({'result': 'success'})


@api_view(['POST'])
@transaction.atomic
def insert_column(request):
    table_id, neighborhood_system_name, position_name, alternative_name, column_type, hidden, required, readonly = insert_column_request_validate(
        request)
    table = TableV2.objects.get(id=table_id)
    columns = ColumnV2.objects.filter(table=table_id).order_by('position')  # position 1 ... n
    # Вычисляем позицию
    if position_name == 'before_id':
        neighborhood_column = ColumnV2.objects.get(table=table_id, system_name=neighborhood_system_name)
        position = neighborhood_column.position
    elif position_name == 'after_id':
        neighborhood_column = ColumnV2.objects.get(table=table_id, system_name=neighborhood_system_name)
        position = neighborhood_column.position + 1
    else:
        if len(columns) == 0:
            position = 1
        else:
            position = columns.last().position+1
        pass
    # -----

    # Двигаем колонки для вставки новой и переименовываем
    columns_to_update = []
    for column in columns.reverse():
        if column.position >= position:
            column.position += 1
            old_system_name = column.system_name
            column.system_name = col_letter(column.position)
            rename_column_sql(table.system_name, old_system_name, column.system_name)
            columns_to_update.append(column)
    ColumnV2.objects.bulk_update(columns_to_update, ['position', 'system_name'])
    # -----

    # Создаем новую колонку в нужной позиции
    column_system_name = col_letter(position)
    ColumnV2.objects.create(
        table=table,
        system_name=column_system_name,
        position=position,
        alternative_name=alternative_name,
        type=column_type,
        hidden=hidden,
        required=required,
        readonly=readonly
    )
    insert_column_sql(table.system_name, column_system_name)
    # -----

    # Отправляем уведомление
    send_column_insert({
        "table_id": table_id
    })

    return Response({'result': 'success'})


@api_view(['GET'])
def get_column_select_list(request):
    column_id = request.GET.get('column_id')
    column = ColumnV2.objects.get(id=column_id)
    response_data = []
    for record in ColumnV2SelectValues.objects.filter(column=column):
        response_data.append({
            "id": record.id,
            "value": record.value
        })
    return Response({'rows': response_data})


@api_view(['POST'])
def create_column_select_list(request):
    column_id = request.data['column_id']
    column = ColumnV2.objects.get(id=column_id)
    value = request.data['value']
    ColumnV2SelectValues.objects.create(column=column, value=value)
    return Response()


@api_view(['PATCH'])
def update_column_select_list(request):
    id = request.data['id']
    value = request.data['value']
    ColumnV2SelectValues.objects.filter(id=id).update(value=value)
    return Response()


@api_view(['DELETE'])
def delete_column_select_list(request):
    id = request.GET.get('id')
    ColumnV2SelectValues.objects.filter(id=id).delete()
    return Response()
