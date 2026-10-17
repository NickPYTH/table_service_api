import io

import openpyxl
from django.contrib.auth.models import User
from django.db import connection
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from tables.models import Profile
from .models import TableV2, ColumnV2, TableUserPermissionV2, RoleV2
from .request_validate import create_from_file_request_validate, get_table_data_request_validate, \
    delete_table_request_validate, \
    get_table_info_request_validate, update_table_request_validate
from .row_views import STEP
from .utils import build_order_by_sql, build_filter_sql, escape_tsv, col_letter


@api_view(['GET'])
def get_table_list(request):
    tables = TableV2.objects.all()
    response_data = []
    for table in tables:
        response_data.append({
            'id': table.id,
            'title': table.alternative_name,
            'system_name': table.system_name,
            'version': 2
        })
    return Response(response_data)


@api_view(['POST'])
def create_from_file(request):
    try:
        user = User.objects.get(pk=request.user.pk)
        file, table_name = create_from_file_request_validate(request)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

    wb = openpyxl.load_workbook(
        io.BytesIO(file.read()),
        read_only=True,
        data_only=True
    )
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    columns = [str(h).strip() for h in header]

    buffer = io.StringIO()  # заполняем tsv форматом table sep format
    for i, row in enumerate(rows):
        tmp = [v for v in row]
        tmp.append({user.id})  # Права пользователей
        tmp.append({})  # Права филиалов
        tmp.append(i * STEP)  # Позиция *100 для вставок
        if len(tmp) != len(columns) + 3:
            continue
        buffer.write("\t".join(escape_tsv(record) for record in tmp) + "\n")
    buffer.seek(0)  # для курсора отматываем буфер обратно тк после записи указатель в конце

    columns_str_with_type = ''
    columns_str = ''
    for i, column in enumerate(columns, start=1):
        columns_str_with_type += f'"{col_letter(i)}" VARCHAR(255),'
        columns_str += f'"{col_letter(i)}",'
    columns_str_with_type += 'allowed_users  INTEGER[],\nallowed_filials   INTEGER[],position BIGINT NOT NULL DEFAULT 0,\nid BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY'
    columns_str += 'allowed_users, allowed_filials, position'

    create_table_sql = f"CREATE TABLE {table_name} ({columns_str_with_type}) WITH (fillfactor = 70);"
    create_user_index = f"CREATE INDEX idx_allowed_users_{table_name} ON {table_name} USING GIN (allowed_users);"
    create_filial_index = f"CREATE INDEX idx_allowed_filials_{table_name} ON {table_name} USING GIN (allowed_filials);"
    create_position_index = f"CREATE INDEX idx_position_{table_name} "f"ON {table_name}(position, id);"

    with connection.cursor() as cursor:
        cursor.execute(create_table_sql)
        cursor.execute(create_user_index)
        cursor.execute(create_filial_index)
        cursor.execute(create_position_index)

    with connection.cursor() as cursor:
        cursor.copy_expert(
            f"COPY {table_name} ({columns_str}) FROM STDIN",
            buffer
        )

    # Создаем модели
    table = TableV2.objects.create(
        system_name=table_name,
        alternative_name=table_name,
        owner=user
    )
    table.save()
    owner_role = RoleV2.objects.get(name='owner')
    TableUserPermissionV2.objects.create(table=table, user=user, role=owner_role)
    for i, column in enumerate(columns, start=1):
        column_model = ColumnV2.objects.create(
            table=table,
            system_name=col_letter(i),
            position=i,
            alternative_name=column,
            type='text'
        )
        column_model.save()

    return Response({'table_id': table.id}, status=201)


@api_view(['POST'])
def get_table_info(request):
    # Проверка входных параметров
    table_id = get_table_info_request_validate(request)
    try:
        table = TableV2.objects.get(id=table_id)
    except Exception as e:
        return Response({
            "error": str(e)
        }, status=404)
    user = request.user
    try:
        role = TableUserPermissionV2.objects.get(table=table, user=user).role
    except Exception as e:
        return Response({
            "error": str(e)
        }, status=403)
    return Response({
        "table_name": table.alternative_name,
        "role": role.name
    }, status=200)


@api_view(['POST'])
def get_table_data(request):
    table_id, page, page_size, sort, filter, group_fields, group_keys = get_table_data_request_validate(request)
    try:
        table = TableV2.objects.get(id=table_id)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

    # отдаём все группы сразу
    is_group_level = bool(group_fields) and len(group_keys) < len(group_fields)

    with connection.cursor() as cursor:
        if is_group_level:
            # группа
            current_field = group_fields[len(group_keys)]  # поле текущего уровня

            # WHERE по уже раскрытым ключам
            where_parts = []
            params = []
            for i, key in enumerate(group_keys):
                where_parts.append(f'"{group_fields[i]}" = %s')
                params.append(key)
            where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

            # кол-во групп на этом уровне
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT "{current_field}")
                FROM {table.system_name}
                {where_sql}
                """,
                params,
            )
            total = cursor.fetchone()[0]


            path_fields = group_fields[:len(group_keys) + 1]
            id_expr = " || '-' || ".join(f'"{f}"' for f in path_fields) # id группы (весь путь чтоб не было конфликта)

            cursor.execute(
                f"""
                SELECT
                    'group-' || {id_expr} AS id,
                    "{current_field}" AS name,
                    COUNT(*) AS "childrenCount"
                FROM {table.system_name}
                {where_sql}
                GROUP BY {', '.join(f'"{f}"' for f in path_fields)}
                ORDER BY "{current_field}"
                """,
                params,
            )

        elif group_fields and len(group_keys) == len(group_fields):
            # Листья строки под раскрытыми ключами
            where_parts = []
            params = []
            for i, key in enumerate(group_keys):
                where_parts.append(f'"{group_fields[i]}" = %s')
                params.append(key)
            where_sql = " AND ".join(where_parts)

            cursor.execute(
                f"SELECT COUNT(*) FROM {table.system_name} WHERE {where_sql}",
                params,
            )
            total = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT *,
                       ROW_NUMBER() OVER (ORDER BY position, id) - 1 AS position_humanity
                FROM {table.system_name}
                WHERE {where_sql}
                ORDER BY position, id
                LIMIT %s OFFSET 0
                """,
                params + [page_size],
            )

        else:
            # Без группировки
            cursor.execute(
                f"SELECT COUNT(*) FROM {table.system_name} WHERE allowed_users @> ARRAY[{[1]}]"
            )
            total = cursor.fetchone()[0]

            offset = page * page_size
            order_sql = build_order_by_sql(sort, table.system_name)
            cursor.execute(f"""
                        SELECT *,
                        ROW_NUMBER() OVER ({order_sql}) - 1 AS position_humanity
                        FROM {table.system_name}
                        {build_filter_sql(table.system_name, filter)}
                        {order_sql}
                        LIMIT {page_size} OFFSET {offset}
                    """)

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    data = [dict(zip(columns, row)) for row in rows]

    total_pages = int(total / page_size) if total % page_size == 0 else int(total / page_size) + 1

    return Response({
        "rows": data,
        "paginator": {
            "page": 0 if is_group_level else page,
            "pageSize": total if is_group_level else page_size,
            "total": total,
            "totalPages": 1 if is_group_level else total_pages,
            "hasNext": False if is_group_level else page + 1 < total_pages,
            "hasPrev": False if is_group_level else page + 1 > 1,
        }
    }, status=200)

@api_view(['DELETE'])
def delete_table(request):
    table_name = delete_table_request_validate(request)
    table = TableV2.objects.get(system_name=table_name)
    TableUserPermissionV2.objects.filter(table=table).delete()
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM denormalized_column_storage_cellformula WHERE table_name = '{table_name}'",
        )
        cursor.execute(
            f"DELETE FROM denormalized_column_storage_formuladeps WHERE table_name = '{table_name}'",
        )
        cursor.execute(
            f"DELETE FROM denormalized_column_storage_columnv2 WHERE table_id = {table.id}",
        )
        cursor.execute(
            f"DELETE FROM denormalized_column_storage_tablepermissionv2 WHERE table_id = {table.id}",
        )
        cursor.execute(
            f"DELETE FROM denormalized_column_storage_tablev2 WHERE id = {table.id}",
        )
        cursor.execute(
            f"DROP TABLE {table_name}",
        )

    return Response({"result": "success"})


@api_view(['POST'])
def update_table_info(request):
    table_id, alternative_name = update_table_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    table.alternative_name = alternative_name
    table.save()

    return Response({'result': 'success'})


@api_view(['GET'])
def search_user(request):
    search_query = request.query_params.get('search_query')
    profiles = Profile.objects.select_related('employee').all()
    profiles_filtered = profiles.filter(
        Q(employee__firstname__icontains=search_query) |
        Q(employee__secondname__icontains=search_query) |
        Q(employee__lastname__icontains=search_query) |
        Q(employee__email__icontains=search_query)
    )
    response = []
    for profile in profiles_filtered:
        response.append({
            "value": profile.user.username
        })
    return Response(response)
