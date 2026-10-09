import io
import json
import re
from io import BytesIO
from collections import defaultdict
from itertools import product

import openpyxl
from django import forms
from django.db import transaction
from django.shortcuts import get_object_or_404
from openpyxl import Workbook
from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
import pandas as pd
import requests
from django.contrib.auth.models import User
from django.db.models import Q, Exists, OuterRef
from django.http import HttpResponse, FileResponse
from django.http import JsonResponse
from openpyxl.utils import get_column_letter
from requests import Request
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.formula_parser import calculate_formula
from api.serializers import ProfileSerializer, normalize_row_orders, UserSerializer
from api.utils import send_cells_update
from tables.models import Profile, Cell, TablePermission, Column, Row, Table, RowPermission, Filial, \
    RowFilialPermission, Employee, Company, ColumnPermission, ColumnFilialPermission, TableFilialPermission
from tables.models import SelectType
from .helper import import_table


def increment_multiple_letters_with_numbers(text,index):
    def increment(match):
        letters = match.group(1)
        number = int(match.group(2))
        return f"{letters}{number + index}"

    pattern = r'([A-Za-z]+)(\d+)'
    return re.sub(pattern, increment, text)


@api_view(['POST'])
def search_user(request):
    id = request.data.get('id')
    type = request.data.get('type')
    search_text = request.data.get('text')
    queryset = Profile.objects.select_related('employee').all()
    queryset = queryset.filter(
        Q(employee__firstname__icontains=search_text) |
        Q(employee__secondname__icontains=search_text) |
        Q(employee__lastname__icontains=search_text) |
        Q(employee__email__icontains=search_text)
    )

    table = None
    if type == 'column':
        column = Column.objects.get(id=id)
        table = column.table

    if type == 'row':
        row = Row.objects.get(id=id)
        table = row.table

    if table is None:
        serializer = ProfileSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        queryset = queryset.filter(
            Exists(TablePermission.objects.filter(
                table=table,
                user=OuterRef('user')
            ))
        )

        serializer = ProfileSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def clear_range(request):
    cells = []
    for cell in Cell.objects.filter(id__in=request.data.get('cells_ids')):
        cell.formula_value = None
        cell.value = None
        cells.append(cell)
    Cell.objects.bulk_update(cells, ['value', 'formula_value'], 100)
    send_cells_update(cells)
    return Response({}, status=status.HTTP_200_OK)


@api_view(['POST'])
def update_range(request):
    cells = []
    ids = []
    value = ""
    formula_value = ""
    for cell in request.data.get('cells'):
        value = cell.get('value')
        formula_value = cell.get('formula_value')
        ids.append(cell.get('id'))
    for index, cell in enumerate(Cell.objects.filter(id__in=ids)):
        if not formula_value:
            cell.value = value
            cell.formula_value = formula_value
            cells.append(cell)
        else:
            updated_value = increment_multiple_letters_with_numbers(value,index)
            cell.value = updated_value
            cell.formula_value = formula_value
            calculate_formula(cell)
            cells.append(cell)
    Cell.objects.bulk_update(cells, ['value', 'formula_value'], 100)
    send_cells_update(cells)
    return Response({}, status=status.HTTP_200_OK)

@api_view(['GET'])
def recalculate_formulas(request):
    table_id = request.query_params.get('table_id')
    cells_with_formulas = Cell.objects.filter(table_id=table_id, value__istartswith="=")
    cells_to_update=[]
    for cell in cells_with_formulas:
        calculate_formula(cell)
        cells_to_update.append(cell)
    send_cells_update(cells_to_update)

    return Response({}, status=status.HTTP_200_OK)

# Метод вызова принудительной нормализации нумерации таблицы
@api_view(['GET'])
def normalize_numbers(request):
    table_id = request.query_params.get('table_id')
    table = Table.objects.get(id=table_id)
    normalize_row_orders(table)

    return Response({}, status=status.HTTP_200_OK)


@api_view(['POST'])
def create_table(request):
    username = request.data.get('username')
    data = request.data.get('data')
    title = request.data.get('title')
    if not username or not data:
        return Response(
            {'error': 'username и data обязательны'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not isinstance(data, list) or len(data) == 0:
        return Response(
            {'error': 'data должен быть непустым массивом'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(username=username)

        df = pd.DataFrame(data)

        for col in df.columns:
            if df[col].dtype == 'datetime64[ns]':
                df[col] = df[col].dt.strftime('%d.%m.%Y')
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col]).dt.strftime('%d.%m.%Y')

        output = BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Автогенерация')
        output.seek(0)

        wb = openpyxl.load_workbook(output, data_only=True)

        import tempfile
        table_id = None
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            wb.save(tmp_file.name)
            tmp_file.flush()
            table = import_table(tmp_file.name, title, user)
            table_id = table.id
            import os
            os.unlink(tmp_file.name)

        return Response({
            'success': True,
            'table_id': table.id,
            'table_title': title,
            'message': f'Таблица успешно создана'
        }, status=status.HTTP_201_CREATED)

    except User.DoesNotExist:
        return Response(
            {'error': f'Пользователь {username} не найден'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST', 'GET'])
def proxy(request):
    target_url = request.GET.get('url')
    if not target_url:
        return JsonResponse({'error': 'Missing url parameter'}, status=400)
    method = request.method
    headers = {}
    for key, value in request.headers.items():
        if key.lower() in ['accesskey']:
            headers[key] = value
    body = request.body
    try:
        response = requests.request(
            method=method,
            url=target_url,
            headers=headers,
            data=body,
            verify=False,
        )
        return HttpResponse(
            content=response.content,
            status=response.status_code,
            content_type=response.headers.get('content-type', 'application/json')
        )

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error':str(e)}, status=500)

@api_view(['GET'])
def set_all_permission(request):
    table_id = request.query_params.get('table_id')
    user_id = request.query_params.get('user_id')
    table = Table.objects.get(id=table_id)
    user = User.objects.get(id=user_id)

    # Предварительно удаляем все права пользователя
    RowPermission.objects.filter(table=table.id, user=user.id).delete()

    # Выдаем права на все строки
    row_permissions = []
    for row in Row.objects.filter(table_id=table_id):
        row_permission = RowPermission.objects.create(table=table.id, row=row.id, user=user.id, can_edit=True, can_delete=True)
        row_permissions.append(row_permission)

    RowPermission.objects.abulk_create(row_permissions)

    return Response({}, status=status.HTTP_200_OK)


@api_view(['GET'])
def remove_all_permission(request):
    table_id = request.query_params.get('table_id')
    user_id = request.query_params.get('user_id')

    # Предварительно удаляем все права пользователя
    RowPermission.objects.filter(table=table_id, user=user_id).delete()

    return Response({}, status=status.HTTP_200_OK)


@api_view(['GET'])
def set_permissions_by_filial_code_column(request):
    column_id = request.query_params.get('column_id')
    cell_list = Cell.objects.filter(column=column_id)
    if len(cell_list) == 0:
        return Response({}, status=status.HTTP_400_BAD_REQUEST)
    test_filial_code = cell_list[0].value
    filial = Filial.objects.get(code=test_filial_code)
    if filial is None:
        return Response({}, status=status.HTTP_400_BAD_REQUEST)
    permissions = []
    for cell in cell_list:
        filial = Filial.objects.get(code=cell.value)
        if filial is None:
            continue
        if len(RowFilialPermission.objects.filter(row=cell.row, filial=filial.id)) > 0:
            continue
        permission = RowFilialPermission(row=cell.row, filial=filial.id, can_edit=True, can_delete=True)
        permissions.append(permission)

    RowFilialPermission.objects.bulk_create(permissions)

    return Response({}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def update_general_formula_by_column(request):
    column_id = request.data.get('column_id')
    formula = request.data.get('formula')
    column = Column.objects.get(id=column_id)
    table_id = column.table.id

    rows = Row.objects.filter(table_id=table_id).order_by('order')
    row_ids_in_order = list(rows.values_list('id', flat=True))

    cells = list(Cell.objects.filter(column=column_id))

    cell_dict = {cell.row: cell for cell in cells}
    sorted_cells = [cell_dict[row_id] for row_id in row_ids_in_order if row_id in cell_dict]
    cells_to_update = []
    i = 0
    for cell in sorted_cells:
        cell.value = increment_multiple_letters_with_numbers(formula, i)
        # Пересчет функций отдельный действием админа
        #calculate_formula(cell, False)
        cells_to_update.append(cell)
        i+=1
    Cell.objects.bulk_update(cells_to_update, ['value'], 100)
    return Response({}, status=status.HTTP_200_OK)


@api_view(['POST'])
def update_inn(request):
    try:
        # Получаем сырые данные
        body_str = request.body.decode('utf-8')
        print(f"Raw body: {body_str[:500]}")

        # Пробуем распарсить JSON
        try:
            data = json.loads(body_str)
            print("JSON parsed successfully")
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")

            # Если не получилось, пробуем исправить вручную
            # Ищем и экранируем кавычки внутри значений полей
            def fix_json_manually(text):
                result = []
                i = 0
                in_string = False
                current_char = ''

                while i < len(text):
                    char = text[i]

                    if char == '"' and (i == 0 or text[i - 1] != '\\'):
                        # Проверяем, не является ли это частью имени поля
                        # Ищем, что было до этого
                        prev_part = text[max(0, i - 20):i]
                        # Если перед кавычкой была запятая или открывающая скобка,
                        # и после кавычки идет двоеточие - это имя поля
                        if ':' in prev_part and ':' not in text[i:i + 10]:
                            # Это имя поля - не экранируем
                            pass
                        else:
                            # Это значение - экранируем если нужно
                            pass
                        in_string = not in_string

                    result.append(char)
                    i += 1

                return ''.join(result)

            # Альтернативный простой фикс - заменяем все кавычки внутри ShortName
            # Находим "ShortName": "..." и экранируем внутренние кавычки
            def fix_shortname(match):
                full = match.group(0)
                # Извлекаем значение
                start = full.find('"') + 1
                end = full.rfind('"')
                if start < end:
                    value = full[start:end]
                    # Экранируем кавычки внутри
                    value_fixed = value.replace('"', '\\"')
                    return f'"ShortName": "{value_fixed}"'
                return full

            # Применяем фикс для всех ShortName
            import re
            pattern = r'"ShortName":\s*"[^"]*"'
            fixed_body = re.sub(pattern, fix_shortname, body_str)

            # Пробуем парсить снова
            try:
                data = json.loads(fixed_body)
                print("Fixed JSON parsed successfully")
            except json.JSONDecodeError as e2:
                print(f"Still cannot parse: {e2}")
                return Response({
                    'error': 'Invalid JSON format',
                    'detail': str(e),
                    'received': body_str[:500]
                }, status=400)

        # Проверяем структуру
        if 'data' not in data:
            return Response({'error': 'Missing "data" field'}, status=400)

        items = data['data']
        print(f"Processing {len(items)} items")

        # Сохраняем в базу
        created_count = 0
        updated_count = 0
        errors = []

        for idx, item in enumerate(items):
            try:
                # Извлекаем данные
                inn = str(item.get('Inn', '')).strip()
                if not inn:
                    errors.append({
                        'index': idx,
                        'error': 'INN is required',
                        'data': item
                    })
                    continue

                # Подготавливаем данные для сохранения
                company_data = {
                    'inn': inn,
                    'ogrn': str(item.get('Ogrn', '')).strip() or None,
                    'kpp': str(item.get('Kpp', '')).strip() or None,
                    'okpo': str(item.get('Okpo', '')).strip() or None,
                    'okved': str(item.get('Okved', '')).strip() or None,
                    'address': str(item.get('Address', '')).strip() or None,
                    'short_name': str(item.get('ShortName', '')).strip() or None,
                }

                # Создаем или обновляем компанию
                company, created = Company.objects.update_or_create(
                    inn=inn,
                    defaults=company_data
                )

                if created:
                    created_count += 1
                    print(f"✓ Created: {company.inn} - {company.short_name}")
                else:
                    updated_count += 1
                    print(f"✓ Updated: {company.inn} - {company.short_name}")

            except Exception as e:
                error_msg = str(e)
                errors.append({
                    'index': idx,
                    'error': error_msg,
                    'data': item
                })
                print(f"✗ Error processing item {idx}: {error_msg}")

        # Формируем ответ
        response_data = {
            'status': 'success',
            'created': created_count,
            'updated': updated_count,
            'total': len(items),
            'errors': errors if errors else None
        }

        print(f"=== RESULT: Created {created_count}, Updated {updated_count} ===")
        return Response(response_data)

    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=500)


@api_view(['POST'])
def load_select_list(request):
    """
    Загрузка значений для выпадающего списка из XLSX файла
    ВНИМАНИЕ: Все предыдущие значения для этой колонки будут удалены!
    Ожидается файл с 1 листом:
    - Колонка A: название (обязательно)
    - Колонка B: код филиала (опционально)
    """
    # Получаем column_id из параметров запроса
    column_id = request.query_params.get('columnId')
    if not column_id:
        return Response(
            {'error': 'Не указан columnId'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Проверяем, что файл был передан
    if 'file' not in request.FILES:
        return Response(
            {'error': 'Файл не найден'},
            status=status.HTTP_400_BAD_REQUEST
        )

    file = request.FILES['file']

    # Проверяем расширение файла
    if not file.name.endswith('.xlsx'):
        return Response(
            {'error': 'Поддерживаются только XLSX файлы'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Загружаем файл через openpyxl
    try:
        workbook = openpyxl.load_workbook(file, data_only=True)
    except Exception as e:
        return Response(
            {'error': f'Не удалось прочитать файл: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Проверяем, что в файле только 1 лист
    if len(workbook.sheetnames) != 1:
        return Response(
            {'error': 'Файл должен содержать ровно 1 лист'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Получаем первый лист
    sheet = workbook.active

    # Проверяем, что лист не пустой
    if sheet.max_row == 0 or sheet.max_column == 0:
        return Response(
            {'error': 'Лист не должен быть пустым'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Собираем данные из файла
    data_rows = []
    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, max_col=2):
        # Получаем значение из колонки A (название)
        name_cell = row[0] if len(row) > 0 else None
        name_value = str(name_cell.value).strip() if name_cell and name_cell.value is not None else None

        # Проверяем, что название присутствует
        if not name_value:
            continue

        # Получаем значение из колонки B (код филиала, опционально)
        filial_code = None
        if len(row) > 1:
            filial_cell = row[1]
            if filial_cell and filial_cell.value is not None:
                filial_code = str(filial_cell.value).strip()
                # Если код филиала пустая строка, считаем как None
                if filial_code == '':
                    filial_code = None

        data_rows.append({
            'name': name_value,
            'filial_owner_code': filial_code
        })

    if not data_rows:
        return Response(
            {'error': 'В файле не найдено значений для загрузки'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Удаляем ВСЕ предыдущие значения для этой колонки
    deleted_count, _ = SelectType.objects.filter(column_id=column_id).delete()

    # Создаем новые записи для всех значений из файла
    select_types_to_create = []
    # Используем tuple (name, filial_owner_code) для уникальности
    unique_items = set()

    for item in data_rows:
        key = (item['name'], item['filial_owner_code'])
        if key not in unique_items:
            unique_items.add(key)
            select_types_to_create.append(
                SelectType(
                    column_id=column_id,
                    name=item['name'],
                    filial_owner_code=item['filial_owner_code']
                )
            )

    # Создаем все записи одним bulk запросом
    if select_types_to_create:
        created_count = len(select_types_to_create)
        SelectType.objects.bulk_create(select_types_to_create)
    else:
        created_count = 0

    # Подсчет статистики
    total_loaded = len(data_rows)
    unique_loaded = len(unique_items)
    with_filial = sum(1 for item in data_rows if item['filial_owner_code'] is not None)
    without_filial = total_loaded - with_filial

    return Response(
        {
            'success': True,
            'message': f'Значения для колонки {column_id} успешно обновлены',
            'deleted': deleted_count,
            'created': created_count,
            'total_loaded': total_loaded,
            'unique_loaded': unique_loaded,
            'with_filial_code': with_filial,
            'without_filial_code': without_filial,
            'column_id': column_id
        },
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
def load_select_list_with_validation(request):
    """
    Альтернативная версия с дополнительной валидацией
    Загрузка значений для выпадающего списка из XLSX файла
    ВНИМАНИЕ: Все предыдущие значения для этой колонки будут удалены!
    """
    try:
        column_id = request.query_params.get('columnId')
        if not column_id:
            return JsonResponse(
                {'error': 'Не указан columnId'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if 'file' not in request.FILES:
            return JsonResponse(
                {'error': 'Файл не найден'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file = request.FILES['file']

        # Проверка расширения
        if not file.name.endswith('.xlsx'):
            return JsonResponse(
                {'error': 'Поддерживаются только XLSX файлы'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверка размера файла (максимум 10MB)
        if file.size > 10 * 1024 * 1024:
            return JsonResponse(
                {'error': 'Размер файла не должен превышать 10MB'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Чтение файла
        try:
            workbook = openpyxl.load_workbook(file, data_only=True)
        except Exception as e:
            return JsonResponse(
                {'error': f'Ошибка чтения файла: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверка количества листов
        if len(workbook.sheetnames) != 1:
            return JsonResponse(
                {'error': 'Файл должен содержать ровно 1 лист'},
                status=status.HTTP_400_BAD_REQUEST
            )

        sheet = workbook.active

        # Проверка на пустоту
        if sheet.max_row == 0:
            return JsonResponse(
                {'error': 'Лист не должен быть пустым'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверка колонок (A до AN = 40 колонок)
        if sheet.max_column > 40:
            return JsonResponse(
                {'error': 'Данные должны быть в колонках от A до AN (максимум 40 колонок)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Сбор значений с учетом колонок A-AN
        values = []
        column_letter = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                         'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
                         'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD',
                         'AE', 'AF', 'AG', 'AH', 'AI', 'AJ', 'AK', 'AL', 'AM', 'AN']

        for row_idx in range(1, sheet.max_row + 1):
            for col_idx in range(1, min(sheet.max_column, 40) + 1):
                cell = sheet.cell(row=row_idx, column=col_idx)
                if cell.value is not None:
                    value_str = str(cell.value).strip()
                    if value_str:
                        values.append({
                            'row': row_idx,
                            'column': column_letter[col_idx - 1] if col_idx - 1 < len(column_letter) else str(col_idx),
                            'value': value_str
                        })

        if not values:
            return JsonResponse(
                {'error': 'В файле не найдено значений для загрузки'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Удаляем ВСЕ предыдущие значения для этой колонки
        deleted_count, _ = SelectType.objects.filter(column_id=column_id).delete()

        # Получаем уникальные значения из файла
        unique_values = {}
        for item in values:
            if item['value'] not in unique_values:
                unique_values[item['value']] = item

        # Подготовка новых записей
        new_records = []
        for value, item in unique_values.items():
            new_records.append(
                SelectType(
                    column_id=column_id,
                    name=value
                )
            )

        # Сохранение новых записей
        if new_records:
            SelectType.objects.bulk_create(new_records)

        # Формирование детального ответа
        response_data = {
            'success': True,
            'message': f'Значения для колонки {column_id} успешно обновлены',
            'column_id': column_id,
            'deleted': deleted_count,
            'created': len(new_records),
            'total_values': len(values),
            'unique_values': len(unique_values),
            'details': {
                'sample_values': list(unique_values.keys())[:10],  # Показываем только первые 10 для примера
            }
        }

        return JsonResponse(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return JsonResponse(
            {'error': f'Внутренняя ошибка сервера: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_email_by_tabnumber(request):
    tabnumber = request.GET.get('tabnumber')
    try:
        employee = Employee.objects.get(tabnumber=tabnumber)
        return Response(
            {"username": employee.email.split("@")[0]},
            status=status.HTTP_200_OK
        )
    except:
        return Response(
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
def get_union_permission_by_table_id(request):
    user = request.user
    filial_code = (Profile.objects
                 .filter(user=user)
                 .select_related('employee')
                 .values_list('employee__id_filial', flat=True)
                 .first())
    filial = Filial.objects.get(code=filial_code)
    table_id = request.GET.get('table_id')
    user_data = UserSerializer(user).data
    column_permissions = ColumnPermission.objects.filter(user=user.id, table=table_id)
    column_filial_permissions = ColumnFilialPermission.objects.filter(filial=filial.id, table=table_id)
    union_permissions = []
    for cp in column_permissions:
        record = {}
        record['id'] = cp.id
        record['column'] = cp.column
        record['table'] = table_id
        record['can_view'] = cp.can_view
        record['can_edit'] = cp.can_edit
        record['user_model'] = user_data
        union_permissions.append(record)
    for cfp in column_filial_permissions:
        record = {}
        record['id'] = cfp.id
        record['column'] = cfp.column.id
        record['table'] = table_id
        record['can_delete'] = cfp.can_delete
        record['can_edit'] = cfp.can_edit
        record['user_model'] = user_data
        union_permissions.append(record)


    return Response(data=union_permissions)


@api_view(['GET'])
def update_column_privelege_by_table_user(request):
    table_id = request.GET.get('table_id')
    table = Table.objects.get(id=table_id)
    table_columns = Column.objects.filter(table=table)
    for table_permission in TablePermission.objects.filter(table_id=table_id):
        for column in table_columns:
            if ColumnPermission.objects.filter(user=table_permission.user.id, column=column.id).count() == 0:
                column_permission = ColumnPermission.objects.create(
                    column=column.id,
                    user=table_permission.user.id,
                    table=table_id,
                    can_view=True,
                    can_edit=True
                )
                column_permission.save()

    for table_filial_permission in TableFilialPermission.objects.filter(table_id=table_id):
        for column in table_columns:
            if ColumnFilialPermission.objects.filter(filial=table_filial_permission.filial.id, column=column.id).count() == 0:
                column_filial_permission = ColumnFilialPermission.objects.create(
                    filial=table_filial_permission.filial,
                    column=column,
                    table=table_id,
                    can_edit=True,
                    can_delete=True
                )
                column_filial_permission.save()

    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
def get_251_report(request):
    filial_code_column = Column.objects.get(id=6394)
    ks_column = Column.objects.get(id=6378)
    complete_percent = Column.objects.get(id=6390)

    # Структура: {filial_code: {ks_name: [values]}}
    data_by_filial_ks = defaultdict(lambda: defaultdict(list))
    all_filial_codes = set()
    all_ks_names = set()

    # Получаем все ячейки complete_percent
    for cell in Cell.objects.filter(column=complete_percent.id):
        # Получаем код филиала для этой же строки
        filial_code_cell = Cell.objects.get(row=cell.row, column=filial_code_column.id)
        filial_code = filial_code_cell.value

        # Получаем КС станцию для этой же строки
        ks_cell = Cell.objects.get(row=cell.row, column=ks_column.id)
        ks_name = ks_cell.value if ks_cell.value and ks_cell.value != '' else 'Без КС'

        # Сохраняем код в множество всех кодов
        if filial_code and filial_code != '':
            all_filial_codes.add(filial_code)
            all_ks_names.add(ks_name)

        # Добавляем значение в список для конкретного филиала и КС
        if cell.value and cell.value != '':
            try:
                value = float(cell.value) if isinstance(cell.value, str) else cell.value
                data_by_filial_ks[filial_code][ks_name].append(value)
            except (ValueError, TypeError):
                pass
        else:
            data_by_filial_ks[filial_code][ks_name].append(0)

    # Формируем данные для отчета
    report_data = []
    for filial_code in sorted(all_filial_codes):
        # Получаем все КС для этого филиала
        ks_data = data_by_filial_ks.get(filial_code, {})

        for ks_name in sorted(ks_data.keys()):
            values = ks_data.get(ks_name, [])
            average = round(sum(values) / len(values), 2) if values else 0

            report_data.append({
                'ks_name': ks_name,
                'average_complete_percent': average,
                'count': len(values)
            })

    # Генерируем Excel отчет
    wb = Workbook()
    ws = wb.active
    ws.title = "Отчет по филиалам 251"

    # Стили
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    border_style = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Заголовки (без столбцов кода и наименования филиала)
    headers = ['№ п/п', 'Промплощадка', 'Средний процент выполнения', 'Количество объектов']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = border_style

    # Заполняем данные
    for row_idx, data in enumerate(report_data, 2):
        # № п/п
        ws.cell(row=row_idx, column=1, value=row_idx - 1).border = border_style
        ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")

        # КС станция
        ws.cell(row=row_idx, column=2, value=data['ks_name']).border = border_style
        ws.cell(row=row_idx, column=2).alignment = Alignment(horizontal="left")

        # Средний процент выполнения
        percent_cell = ws.cell(row=row_idx, column=3, value=data['average_complete_percent'])
        percent_cell.border = border_style
        percent_cell.alignment = Alignment(horizontal="center")
        percent_cell.number_format = '0.00"%"' if data['average_complete_percent'] > 0 else '0"%"'

        # Количество объектов
        ws.cell(row=row_idx, column=4, value=data['count']).border = border_style
        ws.cell(row=row_idx, column=4).alignment = Alignment(horizontal="center")

    # Настраиваем ширину колонок (убраны 2 колонки)
    column_widths = [10, 35, 25, 20]  # № п/п, КС станция, Средний %, Количество
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + col)].width = width

    # Сохраняем в HttpResponse
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=report_251.xlsx'

    return response

class IntListField(forms.JSONField):
    default_error_messages = {
        'not_list': 'Должен быть список',
        'not_ints': 'Все элементы должны быть целыми числами',
    }
    def clean(self, value):
        value = super().clean(value)
        if value is None:
            return value
        if not isinstance(value, list):
            raise forms.ValidationError(self.error_messages['not_list'])
        if not all(isinstance(x, int) for x in value):
            raise forms.ValidationError(self.error_messages['not_ints'])
        return value


class RequestBodyForm(forms.Form):
    table_id = forms.IntegerField(required=True)
    column_ids = IntListField(required=False)
    row_ids = IntListField(required=False)
    filial_ids = IntListField(required=False)
    user_ids = IntListField(required=False)


def create_permissions(request_data: dict, who:str="user"):
    table_id = request_data.get('table_id')
    user_ids = request_data.get('user_ids', [])
    column_ids = request_data.get('column_ids', [])
    filial_ids = request_data.get('filial_ids', [])
    row_ids = request_data.get('row_ids', [])
    if who == "user":
        users_permissions = []
        if column_ids:
            for (user_id, column_id) in product(user_ids, column_ids):
                users_permissions.append(ColumnPermission(
                    column=column_id,
                    user=user_id,
                    table=table_id,
                ))
            ColumnPermission.objects.bulk_create(users_permissions, ignore_conflicts=True)
            return
        if row_ids:
            for (user_id, row_id) in product(user_ids, row_ids):
                users_permissions.append(RowPermission(
                    row=row_id,
                    user=user_id,
                    table=table_id,
                ))
            RowPermission.objects.bulk_create(users_permissions, ignore_conflicts=True)
            return
    else:
        filial_permissions = []
        if column_ids:
            for (filial_id, column_id) in product(filial_ids, column_ids):
                filial = get_object_or_404(Filial, id=filial_id)
                column = get_object_or_404(Column, id=column_id)
                filial_permissions.append(ColumnFilialPermission(
                    column=column,
                    filial=filial,
                    table=table_id,
                ))
                ColumnFilialPermission.objects.bulk_create(filial_permissions, ignore_conflicts=True)
                return
        if row_ids:
            for (filial_id, row_id) in product(filial_ids, row_ids):
                filial_permissions.append(RowFilialPermission(
                    row=row_id,
                    filial=filial_id,
                    table=table_id,
                ))
                RowFilialPermission.objects.bulk_create(filial_permissions, ignore_conflicts=True)
                return


@api_view(['POST'])
@transaction.atomic
def create_mass_permissions(request: Request):
    request_data = RequestBodyForm(request.data)
    if not request_data.is_valid():
        return Response(request_data.errors, status=status.HTTP_400_BAD_REQUEST)
    clean_data = request_data.cleaned_data
    if clean_data.get('user_ids'):
        create_permissions(request_data=clean_data, who="user")
    if clean_data.get('filial_ids'):
        create_permissions(request_data=clean_data, who="filial")

    return Response(status=status.HTTP_200_OK)


# TODO: ОБЯЗАТЕЛЬНО ПЕРЕДЕЛАТЬ НА ПРИВЯЗКУ К ПОЛЮ МОДЕЛИ ТАБЛИЦЫ
NOTE_COL_INDEX = 13  # при Филиал = 0
def _pct(fact_sum, plan_sum) -> float:
    if plan_sum is None or pd.isna(plan_sum) or plan_sum == 0:
        return 0.0
    if fact_sum is None or pd.isna(fact_sum):
        return 0.0
    return float(fact_sum) / float(plan_sum) * 100.0
def _clean_note(v) -> str:
    if v is None:
        return ""
    text = str(v).strip()
    if text.lower() in ("", "nan", "none"):
        return ""
    return text
@api_view(["GET"])
def get_crane_cover_report(request: Request):
    """Свод филиал×объект×группы работ. Без колонки «Примечание»."""
    try:
        table = get_object_or_404(Table, pk=275)
        columns = list(Column.objects.filter(table=table).values("id", "name"))
        col_map = {c["id"]: c["name"] for c in columns}
        ordered_names = [c["name"] for c in columns]
        cells = Cell.objects.filter(table_id=table.id).values("row", "column", "value")
        rows = {}
        for cell in cells:
            row = cell["row"]
            column_name = col_map.get(cell["column"])
            if column_name is None:
                continue
            rows.setdefault(row, {})[column_name] = cell["value"]
        df = pd.DataFrame.from_dict(rows, orient="index")
        df = df.reindex(columns=ordered_names)
        def find_col(names, *keywords):
            for name in names:
                low = name.strip().lower()
                if all(k.lower() in low for k in keywords):
                    return name
            return None
        branch_col = find_col(ordered_names, "филиал")
        object_col = find_col(ordered_names, "объект")
        group_col = find_col(ordered_names, "группа", "работ")
        plan_col = find_col(ordered_names, "план")
        fact_col = find_col(ordered_names, "факт")
        missing = [
            label
            for label, col in [
                ("Филиал", branch_col),
                ("Объект", object_col),
                ("Группа работ", group_col),
                ("План", plan_col),
                ("Факт", fact_col),
            ]
            if col is None
        ]
        if missing:
            return Response(
                {
                    "ok": False,
                    "error": f'Не найдены колонки: {", ".join(missing)}',
                    "columns": ordered_names,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        df[plan_col] = pd.to_numeric(df[plan_col], errors="coerce")
        df[fact_col] = pd.to_numeric(df[fact_col], errors="coerce")
        df = df.dropna(subset=[branch_col, object_col], how="any")
        def pivot_pct(frame, index_cols):
            g = (
                frame.groupby(list(index_cols) + [group_col], dropna=False)
                .agg(fact=(fact_col, "sum"), plan=(plan_col, "sum"))
                .reset_index()
            )
            g["pct"] = [_pct(f, p) for f, p in zip(g["fact"], g["plan"])]
            piv = g.pivot_table(
                values="pct",
                index=index_cols,
                columns=group_col,
                aggfunc="first",
            )
            return piv
        detail = pivot_pct(df, [branch_col, object_col]).fillna(0)
        def add_row_total(piv, frame, index_cols):
            out = piv.copy()
            totals = (
                frame.groupby(list(index_cols), dropna=False)
                .agg(fact=(fact_col, "sum"), plan=(plan_col, "sum"))
            )
            row_pct = [
                _pct(
                    totals.loc[idx, "fact"] if idx in totals.index else 0,
                    totals.loc[idx, "plan"] if idx in totals.index else 0,
                )
                for idx in out.index
            ]
            out["Общий итог"] = row_pct
            return out
        detail = add_row_total(detail, df, [branch_col, object_col])
        branch_only = pivot_pct(df, [branch_col]).fillna(0)
        branch_only = add_row_total(branch_only, df, [branch_col])
        blocks = []
        branch_order = detail.index.get_level_values(0).unique()
        for branch in branch_order:
            branch_row = branch_only.loc[[branch]].copy()
            branch_row.index = pd.MultiIndex.from_tuples(
                [(branch, "")],
                names=[branch_col, object_col],
            )
            branch_row = branch_row.reindex(columns=detail.columns, fill_value=0)
            objects = detail.xs(branch, level=0, drop_level=False)
            blocks.append(branch_row)
            blocks.append(objects)
        summary = pd.concat(blocks)
        grand_cols = {}
        for col in detail.columns:
            if col == "Общий итог":
                continue
            part = df.loc[df[group_col] == col]
            grand_cols[col] = _pct(part[fact_col].sum(), part[plan_col].sum())
        grand_cols["Общий итог"] = _pct(df[fact_col].sum(), df[plan_col].sum())
        grand = pd.DataFrame([grand_cols], columns=detail.columns)
        grand.index = pd.MultiIndex.from_tuples(
            [("Общий итог", "")],
            names=[branch_col, object_col],
        )
        summary = pd.concat([summary, grand]).fillna(0).round(0)
        summary_to_write = summary.copy()
        summary_to_write.index.names = [branch_col, object_col]
        summary_to_write.columns.name = None
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            summary_to_write.to_excel(
                writer,
                sheet_name="Свод",
                merge_cells=True,
                freeze_panes=(1, 0),
            )
        buffer.seek(0)
        wb = load_workbook(buffer)
        ws = wb["Свод"]
        ws.sheet_properties.outlinePr.summaryBelow = False
        header_rows = 1
        legend_cols = 2
        first_data_row = header_rows + 1
        for r in range(1, header_rows + 1):
            ws.row_dimensions[r].outline_level = 0
            ws.row_dimensions[r].hidden = False
        current_row = first_data_row
        group_start = None
        def close_group(start, end):
            if start is None or end < start or end - start < 1:
                return
            ws.row_dimensions.group(
                start + 1,
                end,
                outline_level=1,
                hidden=False,
            )
        for idx in summary_to_write.index:
            branch = idx[0]
            obj = idx[1] if isinstance(idx, tuple) else ""
            if branch == "Общий итог":
                close_group(group_start, current_row - 1)
                group_start = None
                break
            if obj == "":
                close_group(group_start, current_row - 1)
                group_start = current_row
            current_row += 1
        else:
            close_group(group_start, current_row - 1)
        wrap_left = Alignment(wrap_text=True, vertical="center", horizontal="left")
        wrap_center = Alignment(wrap_text=True, vertical="center", horizontal="center")
        thick = Side(style="medium", color="000000")
        thin = Side(style="thin", color="000000")
        thick_border = Border(left=thick, right=thick, top=thick, bottom=thick)
        thin_border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="D9E2F3")
        legend_fill = PatternFill("solid", fgColor="E7E6E6")
        branch_fill = PatternFill("solid", fgColor="FFF2CC")
        percent_format = '0"%"'
        max_row = ws.max_row
        max_col = ws.max_column
        for row_idx in range(1, max_row + 1):
            for col_idx in range(1, legend_cols + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.border = thick_border
                cell.alignment = wrap_left
                if row_idx <= header_rows:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                else:
                    cell.fill = legend_fill
        for col_idx in range(legend_cols + 1, max_col + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.border = thick_border
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = wrap_center
        excel_row = first_data_row
        for idx in summary_to_write.index:
            branch, obj = idx[0], idx[1]
            is_total_row = (obj == "") or (branch == "Общий итог")
            for col_idx in range(1, legend_cols + 1):
                cell = ws.cell(row=excel_row, column=col_idx)
                cell.border = thick_border
                cell.alignment = wrap_left
                if is_total_row:
                    cell.font = Font(bold=True)
                    cell.fill = branch_fill
                else:
                    cell.fill = legend_fill
            for col_idx in range(legend_cols + 1, max_col + 1):
                cell = ws.cell(row=excel_row, column=col_idx)
                cell.border = thin_border
                cell.alignment = wrap_center
                if isinstance(cell.value, (int, float)):
                    cell.number_format = percent_format
                if is_total_row:
                    cell.font = Font(bold=True)
                    cell.fill = branch_fill
            excel_row += 1
        for col_idx in range(1, max_col + 1):
            letter = get_column_letter(col_idx)
            max_len = 0
            for row_idx in range(1, max_row + 1):
                value = ws.cell(row=row_idx, column=col_idx).value
                if value is None:
                    continue
                text = (
                    f"{int(value)}%"
                    if isinstance(value, (int, float))
                    else str(value)
                )
                max_len = max(max_len, len(text))
            ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 60)
        ws.row_dimensions[1].height = 30
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        return FileResponse(
            out,
            as_attachment=True,
            filename="crane_cover_report.xlsx",
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
    except Exception as e:
        return Response(
            {"ok": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
def build_tree_from_sorted_rows(sorted_rows):
    def nest():
        return defaultdict(nest)
    def to_float(v):
        if v in (None, ""):
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            return 0.0
    def pct(plan, fact):
        return None if not plan else fact / plan * 100.0
    tree = nest()
    for row in sorted_rows:
        if not row or len(row) < 7:
            continue
        filial, obj, group, vid, plan_raw, fact_raw, note_raw = row[:7]
        if filial is None or obj is None or group is None or vid is None:
            continue
        if filial == "" or obj == "" or group == "" or vid == "":
            continue
        note = _clean_note(note_raw)
        leaf = tree[filial][obj][group].setdefault(
            vid, {"plan": 0.0, "fact": 0.0, "note": "", "_leaf": True}
        )
        leaf["plan"] += to_float(plan_raw)
        leaf["fact"] += to_float(fact_raw)
        if note:
            if not leaf["note"]:
                leaf["note"] = note
            elif note not in leaf["note"]:
                leaf["note"] = f'{leaf["note"]}; {note}'
    def finalize(node):
        if node.get("_leaf"):
            node["pct"] = pct(node["plan"], node["fact"])
            return node["plan"], node["fact"]
        total_plan = total_fact = 0.0
        for key, child in node.items():
            if key in ("_total", "_leaf"):
                continue
            cp, cf = finalize(child)
            total_plan += cp
            total_fact += cf
        node["_total"] = {
            "plan": total_plan,
            "fact": total_fact,
            "pct": pct(total_plan, total_fact),
        }
        return total_plan, total_fact
    gp, gf = finalize(tree)
    tree["_grand_total"] = {
        "plan": gp,
        "fact": gf,
        "pct": pct(gp, gf),
    }
    def to_plain(o):
        if isinstance(o, dict):
            return {k: to_plain(v) for k, v in o.items()}
        return o
    return to_plain(tree)
SKIP_KEYS = frozenset(
    {"_total", "_grand_total", "plan", "fact", "pct", "note", "_leaf"}
)
FILL_HEADER = PatternFill("solid", fgColor="D9E2EC")
FILL_FILIAL = PatternFill("solid", fgColor="E8EEF4")
FILL_OBJECT = PatternFill("solid", fgColor="EEF3F7")
FILL_GROUP = PatternFill("solid", fgColor="F4F7FA")
FILL_VID = PatternFill("solid", fgColor="FFFFFF")
FILL_GRAND = PatternFill("solid", fgColor="DDE5EE")
FONT_HEADER = Font(bold=True, color="334E68")
FONT_FILIAL = Font(bold=True, color="243B53")
FONT_OBJECT = Font(bold=True, color="486581")
FONT_GROUP = Font(color="486581")
FONT_VID = Font(color="627D98")
FONT_GRAND = Font(bold=True, color="243B53")
THIN = Border(
    left=Side(style="thin", color="CBD2D9"),
    right=Side(style="thin", color="CBD2D9"),
    top=Side(style="thin", color="CBD2D9"),
    bottom=Side(style="thin", color="CBD2D9"),
)
FILL_BY_KIND = {
    "header": FILL_HEADER,
    "filial": FILL_FILIAL,
    "object": FILL_OBJECT,
    "group": FILL_GROUP,
    "vid": FILL_VID,
    "grand": FILL_GRAND,
}
FONT_BY_KIND = {
    "header": FONT_HEADER,
    "filial": FONT_FILIAL,
    "object": FONT_OBJECT,
    "group": FONT_GROUP,
    "vid": FONT_VID,
    "grand": FONT_GRAND,
}
def _child_keys(node):
    return [k for k in node.keys() if k not in SKIP_KEYS]
def _style_row(ws, excel_row, kind):
    fill = FILL_BY_KIND[kind]
    font = FONT_BY_KIND[kind]
    for col in range(1, 7):
        cell = ws.cell(excel_row, col)
        cell.fill = fill
        cell.font = font
        cell.border = THIN
        cell.alignment = Alignment(vertical="center", wrap_text=True)
def write_tree_to_workbook(tree):
    wb = Workbook()
    ws = wb.active
    ws.title = "Сводка"
    # Примечание ПЕРЕД вычисляемым %
    headers = ["Филиал", "Объект", "Группа", "Вид", "Примечание", "% выполнения"]
    ws.append(headers)
    _style_row(ws, 1, "header")
    ws.sheet_properties.outlinePr.summaryBelow = False
    def append_row(filial, obj, group, vid, note, pct, outline_level, kind):
        ws.append([filial, obj, group, vid, note or "", pct])
        excel_row = ws.max_row
        ws.cell(excel_row, 6).number_format = '0"%"'  # % — 6-я колонка
        if outline_level > 0:
            ws.row_dimensions[excel_row].outline_level = outline_level
        _style_row(ws, excel_row, kind)
        return excel_row
    for filial in _child_keys(tree):
        filial_node = tree[filial]
        append_row(
            filial, "", "", "",
            "",
            filial_node.get("_total", {}).get("pct", 0.0),
            0,
            "filial",
        )
        for obj in _child_keys(filial_node):
            obj_node = filial_node[obj]
            append_row(
                "", obj, "", "",
                "",
                obj_node.get("_total", {}).get("pct", 0.0),
                1,
                "object",
            )
            for group in _child_keys(obj_node):
                group_node = obj_node[group]
                append_row(
                    "", "", group, "",
                    "",
                    group_node.get("_total", {}).get("pct", 0.0),
                    2,
                    "group",
                )
                for vid in _child_keys(group_node):
                    leaf = group_node[vid]
                    append_row(
                        "", "", "", vid,
                        leaf.get("note", ""),
                        leaf.get("pct", 0.0),
                        3,
                        "vid",
                    )
    grand = tree.get("_grand_total", {})
    append_row(
        "Общий итог", "", "", "",
        "",
        grand.get("pct", 0.0),
        0,
        "grand",
    )
    for col in (1, 2, 3, 4, 6):
        letter = get_column_letter(col)
        max_len = 0
        for r in range(1, ws.max_row + 1):
            val = ws.cell(r, col).value
            max_len = max(max_len, len(str(val)) if val is not None else 0)
        ws.column_dimensions[letter].width = min(max(12, max_len + 2), 40)
    # Примечание — широкая (колонка 5)
    ws.column_dimensions[get_column_letter(5)].width = 48
    return wb
def build_excel_bytes(tree):
    wb = write_tree_to_workbook(tree)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
@api_view(["GET"])
def get_work_cover_report(request: Request):
    """Дерево Филиал→Объект→Группа→Вид. Примечание из order=13, перед %."""
    table = get_object_or_404(Table, pk=275)
    # 0 Филиал, 1 Объект, 2 Группа, 3 Вид, 6 План, 7 Факт, 13 Примечание
    columns_header = (1, 2, 3, 4, 7, 8, NOTE_COL_INDEX)
    cells = (
        Cell.objects.filter(table_id=table.id)
        .values("column", "row", "value")
        .order_by("row")
    )
    rows = {row.get("id"): [] for row in Row.objects.filter(table=table).values("id")}
    for cell in cells:
        rows[cell.get("row")].append((cell.get("column"), cell.get("value")))
    columns = Column.objects.filter(table=table).values("id").order_by("order")
    columns_index = {
        col.get("id"): column_order for column_order, col in enumerate(columns)
    }
    sorted_rows = [
        [
            x[1]
            for index, x in enumerate(
                sorted(row, key=lambda pair: columns_index.get(pair[0], 10**9))
            )
            if index in columns_header
        ]
        for row in rows.values()
    ]
    tree = build_tree_from_sorted_rows(sorted_rows)
    buf = build_excel_bytes(tree)
    return FileResponse(
        buf,
        as_attachment=True,
        filename="work_cover_report.xlsx",
    )