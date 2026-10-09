from io import BytesIO

import openpyxl
import pandas as pd
from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models.aggregates import Max
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.renderers import BrowsableAPIRenderer
from datetime import datetime
from api.formula_parser import calculate_formula
from api.utils import send_table_create, send_cell_update, send_to_demon
from tables.models import Cell, Filial, ColumnFilialPermission
from tables.models import TablePermission, TableFilialPermission, Profile, RowPermission, RowFilialPermission, Table, \
    Row, Column, CellLock, User, ColumnPermission


def get_table_ids_permissions(user):
    permissions_user = set(TablePermission.objects.filter(user=user).values_list('table__id', flat=True))
    filial_code = (Profile.objects
                 .filter(user=user)
                 .select_related('employee')
                 .values_list('employee__id_filial', flat=True)
                 .first())
    filial = Filial.objects.get(code=filial_code)
    permissions_filial = set(
        TableFilialPermission.objects.filter(filial__id=filial.id).values_list('table__id', flat=True))
    all_permissions = permissions_user | permissions_filial
    return all_permissions

def get_row_ids_permissions(user):
    permissions_user = set(RowPermission.objects.filter(user=user.id).values_list('row', flat=True))
    filial_id = (Profile.objects
                 .filter(user=user)
                 .select_related('employee')
                 .values_list('employee__id_filial', flat=True)
                 .first())
    permissions_filial = set(RowFilialPermission.objects.filter(filial=filial_id).values_list('row', flat=True))
    all_permissions = permissions_user | permissions_filial
    return all_permissions

def get_columns_ids_permissions(user):
    permission_user = set(ColumnPermission.objects.filter(user=user).values_list('column', flat=True))
    filial_id = (Profile.objects
                 .filter(user=user)
                 .select_related('employee')
                 .values_list('employee__id_filial', flat=True)
                 .first())
    filial = Filial.objects.get(code=filial_id)
    permission_filial = set(ColumnFilialPermission.objects.filter(filial=filial).values_list('column', flat=True))
    all_permissions = permission_user | permission_filial
    return all_permissions

class FileUploadBrowsableRenderer(BrowsableAPIRenderer):
    def get_rendered_html_form(self, data, view, method, request):
        if method == 'POST':
            html = '''
            <div class="form-wrapper">
                <form enctype="multipart/form-data" method="post">
                    <div class="form-group">
                        <label for="file">Выберите файл:</label>
                        <input type="file" id="file" name="file" required>
                    </div>
                    <input type='text' id='table_name' name="table_name" required/>
                    <button type="submit" class="btn btn-primary">Загрузить</button>
                </form>
            </div> 
            <style>
                .form-wrapper { margin: 20px; }
                .form-group { margin-bottom: 15px; }
                input[type="file"] { display: block; margin-top: 5px; }
                .btn { padding: 8px 15px; background: #007bff; color: white; border: none; border-radius: 4px; }
            </style>
            '''
            return mark_safe(html)  # Помечаем HTML как безопасный
        return super().get_rendered_html_form(data, view, method, request)

def determine_column_types(rows_sample):
    """Определяем тип данных для каждой колонки на основе первых 10 строк"""
    if not rows_sample:
        return []

    # sample_size = min(10, len(rows_sample))
    column_types = []

    for col_idx in range(len(rows_sample[0])):
        # values = [row[col_idx] for row in rows_sample[:sample_size] if row[col_idx] is not None]
        col_type = Column.ColumnType.TEXT
        # if not values:
        #     column_types.append(Column.ColumnType.TEXT)
        #     continue
        #
        # # Проверяем типы данных
        # if all(isinstance(v, bool) for v in values):
        #     col_type = Column.ColumnType.BOOLEAN
        # elif all(isinstance(v, int) for v in values) and not any(isinstance(v, bool) for v in values):
        #     col_type = Column.ColumnType.INTEGER
        # elif all(isinstance(v, (int, float)) for v in values) and not any(isinstance(v, bool) for v in values):
        #     col_type = Column.ColumnType.FLOAT
        # elif all(isinstance(v, date) for v in values):
        #     col_type = Column.ColumnType.DATE
        # else:
        #     col_type = Column.ColumnType.TEXT

        column_types.append(col_type)

    return column_types

def prepare_cell(row, column, table, value):
    #if value is None:
    #    return None

    cell = Cell(row=row.id, column=column.id,table_id=table.id, value=value)

    return cell

def import_table(file, name, user):
    try:
        with transaction.atomic():
            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active

            table = Table.objects.create(title=name, owner=user)
            TablePermission.objects.create(
                table=table, user=user,
                can_view=True, can_edit=True, role='owner'
            )


            rows_data = list(ws.iter_rows(values_only=True))
            if not rows_data:
                return table


            sample = rows_data[1:min(len(rows_data), 5000)]
            headers = [str(header).strip() for header in rows_data[0]]
            column_types = determine_column_types(sample)

            # Создаём колонки
            columns = []
            for order, (header, data_type) in enumerate(zip(headers, column_types), start=1):
                col = Column(table=table, name=header[:299], order=order, data_type=data_type)
                columns.append(col)
            Column.objects.bulk_create(columns)

            # Права на колонки
            ColumnPermission.objects.bulk_create([
                ColumnPermission(column=col.id, user=user.id, table=table.id) for col in columns
            ])

            # Создаём строки
            def row_generator():
                for idx, _ in enumerate(rows_data[1:], start=0):
                    yield Row(table=table, order=idx, created_by=user)

            Row.objects.bulk_create(row_generator(), batch_size=20000)  # увеличил размер


            created_rows = list(Row.objects.filter(table=table).order_by('order'))


            def row_perm_generator():
                for row_obj in created_rows:
                    yield RowPermission(
                        row=row_obj.id,
                        user=user.id,
                        table=table.id,
                        can_edit=True,
                        can_delete=True
                    )


            def cell_generator():
                for row_obj, row_values in zip(created_rows, rows_data[1:]):
                    for col_obj, value in zip(columns, row_values):
                        # Преобразуем дату в строку, если нужно
                        if isinstance(value, datetime):
                            value = value.strftime('%d.%m.%Y')
                        cell = prepare_cell(row_obj, col_obj, table, value)
                        if cell:
                            yield cell

            RowPermission.objects.bulk_create(row_perm_generator(), batch_size=20000, ignore_conflicts=True)
            Cell.objects.bulk_create(cell_generator(), batch_size=20000)

            return table

    except Exception as e:
        raise

def import_to_existing_table(file, table_id, user):
    try:
        with transaction.atomic():
            # Получаем таблицу и проверяем права
            table = Table.objects.get(id=table_id)
            if not table.permissions.filter(user=user, can_view=True).exists():
                raise PermissionDenied("У вас нет прав на редактирование этой таблицы")

            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active
            rows_data = list(ws.iter_rows(values_only=True))

            if not rows_data:
                return table

            # Получаем существующие колонки
            existing_columns = list(table.columns.all().order_by('order'))
            if len(rows_data[0]) != len(existing_columns):
                raise ValueError("Количество колонок в файле не совпадает с таблицей")

            # Определяем порядковый номер для новых строк
            last_order = Row.objects.filter(table=table).aggregate(Max('order'))['order__max'] or 0

            # Подготавливаем новые строки
            new_rows = []
            for row_order, row_values in enumerate(rows_data[1:], start=last_order + 1):
                row = Row(
                    table=table,
                    order=row_order,
                    created_by=user
                )
                new_rows.append(row)

            Row.objects.bulk_create(new_rows)

            # Получаем ID созданных строк
            created_rows = list(Row.objects.filter(table=table, order__gt=last_order).order_by('order'))

            # Подготавливаем ячейки и права
            cells = []
            row_permissions = []

            for row_obj, row_values in zip(created_rows, rows_data[1:]):
                row_permissions.append(
                    RowPermission(
                        row=row_obj.id,
                        user=user.id,
                        can_edit=True,
                        can_delete=True,
                        table=table.id
                    )
                )

                for column, value in zip(existing_columns, row_values):
                    cell = prepare_cell(row_obj, column,table, value)
                    if cell:
                        cells.append(cell)

            # Массовое создание
            RowPermission.objects.bulk_create(row_permissions)
            Cell.objects.bulk_create(cells)
            send_table_create(table)
            return table
    except Exception as e:
    # Логируем ошибку (можно использовать logging.exception(e))
        raise  #

@sync_to_async(thread_sensitive=False)
def get_cell_by_id(cell_id):
    cell = get_object_or_404(Cell, pk=cell_id)
    return cell

def recalculate_formulas(table_id):
    cells_with_formulas = Cell.objects.filter(table_id=table_id, value__istartswith="=")
    for cell in cells_with_formulas:
        calculate_formula(cell)
        send_cell_update(cell)

def normalize_columns(table_id):
    columns = Column.objects.filter(table_id=table_id).order_by('order')
    for index, column in enumerate(columns):
        if column.order != index+1:
            Column.objects.filter(id=column.id).update(order=index+1)

@sync_to_async(thread_sensitive=False)
def create_cell_lock(cell,user):
    CellLock.objects.filter(user=user).delete()
    if CellLock.objects.filter(cell=cell, user=user).count() > 0:
        return CellLock.objects.filter(cell=cell, user=user)[0]
    cell_lock = CellLock.objects.create(cell=cell, user=user)

    return cell_lock

@sync_to_async(thread_sensitive=False)
def get_cell_lock_by_cell(cell):
    try:
        cell_lock = CellLock.objects.get(cell=cell)
        return cell_lock
    except:
        return None

@sync_to_async(thread_sensitive=False)
def remove_cell_lock(cell_lock):
    cell_lock.delete()
    cell_ids = Cell.objects.all().values_list('id', flat=True)
    cell_locks = CellLock.objects.filter(cell_id__in=cell_ids)
    result = [{'cell_id':lock.cell_id,'user_id':lock.user_id} for lock in cell_locks]
    return result

@sync_to_async(thread_sensitive=False)
def get_user(user_id):
    user = User.objects.get(id=user_id)
    return user

def export_table(request, table_id, format_type):
    table = get_object_or_404(Table, pk=table_id)

    columns = table.columns.all().order_by('order')
    rows = table.rows.all().order_by('order')

    data = {col.name: [] for col in columns}
    for row in rows:
        cells_dict = {}
        for cell in Cell.objects.filter(row=row.id):
            cells_dict[cell.column] = cell
        for col in columns:
            cell = cells_dict.get(col.id)
            value = ""
            if cell.value is not None:
                if cell.value.startswith("="):
                    value = cell.formula_value
                else:
                    value = cell.value
            data[col.name].append(value)
    df = pd.DataFrame(data)
    filename = 'unknown'
    if format_type == 'csv':
        response = HttpResponse(df.to_csv(index=False), content_type='text/csv')
        filename = f"{table.title}.csv"

    elif format_type == 'xls':
        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='xlwt')
        response = HttpResponse(buffer.getvalue(), content_type='application/vnd.ms-excel')
        filename = f"{table.title}.xls"

    elif format_type == 'xlsx':
        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        response = HttpResponse(buffer.getvalue(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = f"{table.title}.xlsx"

    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@sync_to_async(thread_sensitive=False)
def reorder_columns(table_id, old_index, new_index):
    table = Table.objects.get(id=table_id)
    column_a = Column.objects.get(table=table, order=old_index)
    column_b = Column.objects.get(table=table, order=new_index)
    column_a.order = new_index
    column_b.order = old_index
    column_a.save()
    column_b.save()

@sync_to_async(thread_sensitive=False)
def send_to_demon_proxy(username, path):
    send_to_demon(username, path)
