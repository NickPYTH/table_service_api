import io

import openpyxl
from django.contrib.auth.models import User
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import TableV2, ColumnV2, TablePermissionV2, CellFormula, FormulaDeps, RoleV2
from .request_validate import update_cell_request_validate, \
    create_from_file_request_validate, get_table_data_request_validate, delete_row_request_validate, \
    delete_table_request_validate, add_table_permission_request_validate, get_table_info_request_validate, \
    get_column_request_validate, update_column_request_validate
from .utils import build_order_by_sql, build_filter_sql, escape_tsv, col_letter, calculate_formula, recursive_update, \
    update_cell
from .ws_sender import send_cell_update


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

@api_view(['GET'])
def get_table_columns(request):
    table_id = request.GET.get('table_id')
    table = TableV2.objects.get(id=table_id)
    response_data = []
    for column in ColumnV2.objects.filter(table=table).order_by('id'):
        response_data.append({
            "id": column.id,
            "system_name": column.system_name,
            "alternative_name": column.alternative_name,
            "type": column.type,
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
    for row in rows:
        tmp = [v for v in row]
        tmp.append({user.id})  # Права пользователей
        tmp.append({})  # Права филиалов
        if len(tmp) != len(columns) + 2:
            continue
        else:
            buffer.write("\t".join(escape_tsv(record) for record in tmp) + "\n")
    buffer.seek(0)  # для курсора отматываем буфер обратно тк после записи указатель в конце

    columns_str_with_type = ''
    columns_str = ''
    for i, column in enumerate(columns, start=1):
        columns_str_with_type += f'"{col_letter(i)}" VARCHAR(255),'
        columns_str += f'"{col_letter(i)}",'
    columns_str_with_type += 'allowed_users   INTEGER[],\nallowed_filials   INTEGER[],\nid BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY'
    columns_str += 'allowed_users, allowed_filials'

    create_table_sql = f"CREATE TABLE {table_name} ({columns_str_with_type}) WITH (fillfactor = 70);"
    create_user_index = f"CREATE INDEX idx_allowed_users_{table_name} ON {table_name} USING GIN (allowed_users);"
    create_filial_index = f"CREATE INDEX idx_allowed_filials_{table_name} ON {table_name} USING GIN (allowed_filials);"

    with connection.cursor() as cursor:
        cursor.execute(create_table_sql)
        cursor.execute(create_user_index)
        cursor.execute(create_filial_index)

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
    TablePermissionV2.objects.create(table=table, user=user, role=owner_role)
    for i, column in enumerate(columns, start=1):
        column_model = ColumnV2.objects.create(
            table=table,
            system_name=col_letter(i),
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
        role = TablePermissionV2.objects.get(table=table, user=user).role
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
    # Проверка входных параметров
    table_id, page, page_size, sort, filter, group_fields, group_keys = get_table_data_request_validate(request)
    try:
        table = TableV2.objects.get(id=table_id)
    except Exception as e:
        return Response({'error': str(e)}, status=400)
    offset = page * page_size
    with connection.cursor() as cursor:
        if group_fields and not group_keys:
            group_field = group_fields[0]  # например 'b' пока одноуровневая группировка
            cursor.execute(
                f"SELECT COUNT(DISTINCT {group_field}) FROM {table.system_name}"
            )
            total = cursor.fetchone()[0]
            cursor.execute(
                f"""
                SELECT 
                    'group-' || {group_field} AS id, 
                    {group_field} AS name, 
                    count(*) AS "childrenCount"
                FROM {table.system_name}
                GROUP BY {group_field}
                """
            )
        elif group_fields and group_keys:
            # Фильтруем по уже раскрытым ключам, строки по уже раскрытым ключам
            where_parts = []
            params = []
            for i, key in enumerate(group_keys):
                field = group_fields[i]
                where_parts.append(f"{field} = %s")
                params.append(key)

            where_sql = " AND ".join(where_parts)

            # Получаем кол-во записей
            cursor.execute(
                f"""
                    SELECT COUNT(*)
                    FROM {table.system_name}
                    WHERE {where_sql}
                    """,
                group_keys
            )
            total = cursor.fetchone()[0]

            params.extend([total, 0])

            cursor.execute(
                f"""
                SELECT *
                FROM {table.system_name}
                WHERE {where_sql}
                LIMIT %s OFFSET %s
                """,
                params
            )
        else:
            # Получаем кол-во записей
            cursor.execute(
                f"SELECT COUNT(*) FROM {table.system_name} WHERE allowed_users @> ARRAY[{[1]}]"
            )
            total = cursor.fetchone()[0]

            offset = page * page_size # 0 * 25 = 0 => отступ отсутствует

            cursor.execute(f"""
                        SELECT *
                        FROM {table.system_name}
                        {build_filter_sql(filter)}
                        {build_order_by_sql(sort, table.system_name)}
                        LIMIT {page_size} OFFSET {offset}
                    """)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    data = [dict(zip(columns, row)) for row in rows]

    total_pages = int(total/page_size) if total%page_size==0 else int(total/page_size)+1
    return Response({
        #"columns": columns,
        "rows": data,
        "paginator": {
            "page": 0 if group_fields and group_keys else page,
            "pageSize": total if group_fields and group_keys else page_size,
            "total": total,
            "totalPages": 1 if group_fields and group_keys else total_pages,
            "hasNext": page+1 < total_pages, # Учитываем что page с 0
            "hasPrev": page+1 > 1, # Учитываем что page с 0
        }
    }, status=200)


@api_view(['POST'])
def update_cell_request(request):
    try:
        table_id, column_name, row_id, value = update_cell_request_validate(request)
    except Exception as e:
        return Response({'error': str(e)}, status=400)
    table_name = TableV2.objects.get(id=table_id).system_name
    if value is not None:
        if value.startswith('='):
            value = calculate_formula(table_name, column_name, row_id, value)
        else:
            FormulaDeps.objects.filter(table_name=table_name, from_column=column_name, from_row_id=row_id).delete()
            CellFormula.objects.filter(table_name=table_name, column=column_name, row_id=row_id).delete()
    update_cell(table_name, column_name, row_id, value)
    # Поиск зависимых ячеек(если она зависима, значит с формулой)
    updated_cell = [{
        "table_id": table_id,
        "column_name": column_name,
        "row_id": row_id,
        "value": value
    }]
    [updated_cell.append(cell) for cell in recursive_update(table_name, table_id, column_name, row_id, [])]
    send_cell_update(updated_cell)
    return Response({"result": "success"})


@api_view(['DELETE'])
def delete_row(request):
    table_name, row_id = delete_row_request_validate(request)

    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {table_name} WHERE id = {row_id}",
        )

    return Response({"result": "success"})


@api_view(['DELETE'])
def delete_table(request):
    table_name = delete_table_request_validate(request)
    table = TableV2.objects.get(system_name=table_name)
    TablePermissionV2.objects.filter(table=table).delete()
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
def add_table_permission(request):
    """Метод для выдачи прав на таблицу(TablePermissionV2) + добавление user_id в каждую строку"""
    table_id, user_id = add_table_permission_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    user = User.objects.get(id=user_id)
    table_permission = TablePermissionV2.objects.create(
        user=user,
        table=table,
    )
    table_permission.save()

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
                UPDATE "{table.system_name}"
                SET allowed_users = array_append(allowed_users, {user_id})
                WHERE NOT ({user_id} = ANY(allowed_users))
            """,
        )

    return Response({'result': 'success'})


@api_view(['POST'])
def remove_table_permission(request):
    """Метод для удаления прав на таблицу(TablePermissionV2) + удаление user_id в каждой строке"""
    table_id, user_id = add_table_permission_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    user = User.objects.get(id=user_id)
    table_permission = TablePermissionV2.objects.get(
        user=user,
        table=table,
    )
    table_permission.delete()

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
                UPDATE "{table.system_name}"
                SET allowed_users = array_remove(allowed_users, {user_id})
                WHERE {user_id} = ANY(allowed_users)
            """,
        )

    return Response({'result': 'success'})

@api_view(['POST'])
def get_cell_formula(request):
    table_id = request.data['table_id']
    column_system_name = request.data['column_system_name']
    row_id = request.data['row_id']
    table = TableV2.objects.get(id=table_id)
    cell_formula = CellFormula.objects.filter(table_name=table.system_name, column=column_system_name, row_id=row_id)
    if cell_formula.exists():
        return Response({'formula': cell_formula[0].formula})
    return Response({'formula': None}, status=404)


@api_view(['POST'])
def update_column(request):
    table_id, column_system_name, column_alternative_name, column_type = update_column_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    column = ColumnV2.objects.get(table=table, system_name=column_system_name)
    column.type = column_type
    column.alternative_name = column_alternative_name
    column.save()
    return Response({'result': 'success'})

@api_view(['GET'])
def get_column(request):
    table_id, system_name = get_column_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    column = ColumnV2.objects.get(table=table, system_name=system_name)
    return Response({
        'table_id': column.table.id,
        'system_name': column.system_name,
        'alternative_name': column.alternative_name,
        'type': column.type
    })
