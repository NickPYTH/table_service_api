from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from denormalized_column_storage.models import TableV2
from denormalized_column_storage.ws_sender import send_row_insert

STEP = 1 << 32


@api_view(['POST'])
def insert_row(request):
    table_id = request.data.get('table_id')
    before_id = request.data.get('before_id')
    after_id = request.data.get('after_id')
    values = request.data.get('values', {}) or {}

    if table_id is None:
        return Response({'error': 'table_id is required'}, status=400)

    table = TableV2.objects.get(id=table_id)

    table_name = table.system_name

    with connection.cursor() as cursor:
        # Вычисляем позицию
        if before_id is not None:
            cursor.execute(f"SELECT position FROM {table_name} WHERE id = {before_id}")
            row = cursor.fetchone()
            if not row:
                return Response({'error': 'before_id not found'}, status=404)
            next_pos = row[0]

            cursor.execute(f"SELECT MAX(position) FROM {table_name} WHERE position < {next_pos}")
            prev_pos = cursor.fetchone()[0]

            new_pos = (prev_pos + next_pos) // 2 if prev_pos is not None else next_pos - STEP

        elif after_id is not None:
            cursor.execute(f"SELECT position FROM {table_name} WHERE id = {after_id}")
            row = cursor.fetchone()
            if not row:
                return Response({'error': 'after_id not found'}, status=404)
            prev_pos = row[0]

            cursor.execute(
                f"SELECT MIN(position) FROM {table_name} WHERE position > %s",
                [prev_pos],
            )
            next_pos = cursor.fetchone()[0]

            new_pos = (prev_pos + next_pos) // 2 if next_pos is not None else prev_pos + STEP

        else:
            # аппенд в конец
            cursor.execute(f"SELECT MAX(position) FROM {table_name}")
            max_pos = cursor.fetchone()[0]
            new_pos = (max_pos + STEP) if max_pos is not None else 0

        # Cобираем insert sql
        columns = []
        placeholders = []
        params = []

        for col_system_name, value in values.items():
            columns.append(f'"{col_system_name}"')
            placeholders.append('%s')
            params.append(value)

        columns.append('position')
        placeholders.append('%s')
        params.append(new_pos)

        # дефолтные права  как в create_from_file TODO
        columns.append('allowed_users')
        placeholders.append('%s')
        params.append([request.user.id])

        columns.append('allowed_filials')
        placeholders.append('%s')
        params.append([])
        # -----

        sql = (
            f"INSERT INTO {table_name} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) "
            f"RETURNING id, position"
        )
        cursor.execute(sql, params)
        new_id, returned_pos = cursor.fetchone()
    send_row_insert({
        "table_id": table_id,
        "position": returned_pos,
        "values": values
    })
    return Response({
        'result': 'success',
        'id': new_id,
        'position': returned_pos,
    }, status=201)
