import base64
import hashlib
import re
from datetime import datetime
from itertools import product

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.db import transaction, connection
from django.db.models.expressions import F
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import NotFound, ValidationError

from tables.models import CellEditLog, Filial, Employee, Department, Profile, Admin, Table, Column, Cell, Row, \
    RowPermission, \
    TablePermission, TableFilialPermission, RowFilialPermission, CellLock, ColumnPermission, ColumnFilialPermission, \
    SelectType, CellComment, CellFileHistory, CellFile, RowValuePermission
from .formula_parser import calculate_formula


def notify_table_update():
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "table_updates",
        {
            "type": "table.updated",
            "message": "Table data updated",
        }
    )

def numberToChar(num):
    if num < 1:
        return "T"
    result = ""
    while num > 0:
        num -= 1
        result = chr(num % 26 + 65) + result
        num //= 26
    return result

def increment_multiple_letters_with_numbers(text,index):
    def increment(match):
        letters = match.group(1)
        number = int(match.group(2))
        return f"{letters}{number + index}"

    pattern = r'\b([A-Za-z]+)(\d+)'
    return re.sub(pattern, increment, text)

def update_auto_with_related_number(auto_column, rows_ids):
    related_column_id = auto_column.related_number_column_id
    default_value = int(auto_column.default_value) if auto_column.default_value and auto_column.default_value.isdigit() else 1

    rows_with_values = []
    for row_id in rows_ids:
        cell = Cell.objects.filter(column=related_column_id, row=row_id).first()
        current_value = cell.value if cell else None
        rows_with_values.append((row_id, current_value))

    number = default_value
    previous_value = None

    for row_id, current_value in rows_with_values:
        if current_value != previous_value:
            number = default_value
            previous_value = current_value

        Cell.objects.filter(column=auto_column.id, row=row_id).update(value=str(number))
        number += 1

def update_auto_with_related_columns(auto_column, rows_ids):
    column_ids = auto_column.related_column_ids
    default_value = int(auto_column.default_value) if auto_column.default_value and auto_column.default_value.isdigit() else 1

    columns_dict = []
    for row_id in rows_ids:
        row_value_list = []
        for column_id in column_ids:
            cell = Cell.objects.filter(column=column_id, row=row_id).first()
            column_value = cell.value if cell else None
            row_value_list.append(column_value)
        columns_dict.append(tuple(row_value_list))

    unique_rows = list(set(columns_dict))
    for unique_row in unique_rows:
        indices = [x for x, item in enumerate(columns_dict) if item == unique_row]
        number = default_value
        for index in indices:
            Cell.objects.filter(column=auto_column.id, row=rows_ids[index]).update(value=str(number))
            number += 1

def update_auto_column(table_id):
    auto_column = Column.objects.filter(table_id=table_id, data_type='auto').first()
    if not auto_column:
        return

    rows_ids = Table.objects.prefetch_related('rows').get(id=table_id).rows.all().values_list('id', flat=True)
    cells = Cell.objects.filter(row__in=rows_ids, column=auto_column.id)
    cells.update(value="")

    if auto_column.related_number_column_id:
        update_auto_with_related_number(auto_column, rows_ids)
    else:
        update_auto_with_related_columns(auto_column, rows_ids)

    return cells

def normalize_row_orders(table):
    rows = Row.objects.filter(table=table).order_by('order')
    for index, row in enumerate(rows):
        if row.order != index:
            Row.objects.filter(id=row.id).update(order=index)

class UserSerializer(serializers.ModelSerializer):
    second_name = serializers.CharField(read_only=True)
    filial = serializers.SerializerMethodField()

    def get_filial(self, obj):
        if 'request' in self.context:
            current_user = self.context['request'].user
            filial = Filial.objects.get(code=Profile.objects.filter(user_id=current_user.id).first().employee.id_filial)
            return filial.code
        return None

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',  'second_name', 'filial']


class FilialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Filial
        fields = '__all__'
        extra_kwargs = {
            'id': {'read_only': True},
            'set_date': {'format': '%Y-%m-%d'},
            'end_date': {'format': '%Y-%m-%d'}
        }


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = '__all__'
        extra_kwargs = {
            'set_date': {'format': '%Y-%m-%d'},
            'end_date': {'format': '%Y-%m-%d'}
        }


class EmployeeSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(source='id_department', read_only=True)
    filial = FilialSerializer(source='id_filial', read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'
        extra_kwargs = {
            'set_date': {'format': '%Y-%m-%d'},
            'end_date': {'format': '%Y-%m-%d'},
            'id_filial': {'write_only': True},
            'id_department': {'write_only': True}
        }


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    employee = EmployeeSerializer()

    class Meta:
        model = Profile
        fields = '__all__'


class AdminSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = Admin
        fields = '__all__'
        extra_kwargs = {
            'created_at': {'format': '%Y-%m-%d %H:%M:%S'}
        }


class ProfileCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'


class ColumnSerializer(serializers.ModelSerializer):
    select_values = serializers.SerializerMethodField(required=False)
    related_column_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    class Meta:
        model = Column
        fields = ['id',
                  'name',
                  'order',
                  'data_type',
                  "table",
                  'select_values',
                  'related_column_ids',
                  'default_value',
                  'default_value_from_user_filial_code',
                  'default_value_from_prev_row',
                  'available_if_confirm_mode_enabled',
                  'hidden',
                  'disabled',
                  'required'
                  ]
        extra_kwargs = {
            'id': {'required': False},
            'table': {'required': False},
            'name': {'required': False},
            'order': {'required': False},
            'data_type': {'required': False},
            'default_value': {'required': False},
        }

    def normalize_columns(self, table_id):
        columns = Column.objects.filter(table_id=table_id).order_by('order')
        for index, column in enumerate(columns):
            if column.order != index+1:
                Column.objects.filter(id=column.id).update(order=index+1)

    #Попробовать реализовать логику с автоинкрементом здесь в методе update
    def update(self, instance, validated_data):
        table_id = Column.objects.get(id=instance.id).table.id
        if validated_data.get('data_type') == 'select':
            column_values = Cell.objects.filter(column=instance.id).exclude(value__isnull=True).exclude(
                value="").values_list('value', flat=True)
            column_dict_select = []
            for column_value in column_values:
                select_type = SelectType(column_id=instance.id, name=column_value)
                column_dict_select.append(select_type)
            SelectType.objects.bulk_create(column_dict_select, ignore_conflicts=True)
        elif validated_data.get('data_type') == 'auto':
            super().update(instance, validated_data)
            update_auto_column(table_id)
        else:
            if 'default_value' in validated_data and validated_data['default_value'] is not None and validated_data.get('data_type') == 'auto':
                table_id = instance.table.id
                rows_ids = Table.objects.prefetch_related('rows').get(id=table_id).rows.all().values_list('id',
                                                                                                          flat=True)
                Cell.objects.filter(
                    row__in=rows_ids,
                    column=instance.id
                ).update(value=str(validated_data['default_value']))

            SelectType.objects.filter(column_id=instance.id).delete()

        self.normalize_columns(table_id)
        return super().update(instance, validated_data)

    def create(self, validated_data):
        notify_table_update()
        table = validated_data['table']
        columns = Column.objects.filter(table=table)
        user = self.context['request'].user
        request_data = self.context['request'].data
        current_column_id = request_data.get('id')
        with_copy = request_data.get('withCopy')
        position = request_data.get('order')

        # Создание столбца
        if current_column_id:
            original_column = Column.objects.get(id=current_column_id)
            columns_count = columns.count()
            if isinstance(position, int):
                if position < 0:
                    position = 0
                elif position > columns_count:
                    position = columns_count
                order = position
                Column.objects.filter(table=table, order__gte=position).update(order=F('order') + 1)
            else:
                order = columns_count
            column = Column.objects.create(table=table,order=order,name=original_column.name + ' - копия')
        else:
            column = super().create(validated_data)


        #Создание строки если столбец в таблице первый
        if len(columns) == 0:
            Row.objects.create(table=column.table, created_by=user)


        #Создание ячеек
        rows = column.table.rows.all()

        cells = [
            Cell(
                row=row.id,
                column=column.id,
                table_id=table.id,
                value=column.default_value
            )
            for row in rows
        ]

        created_cells = Cell.objects.bulk_create(cells)

        if column.default_value and column.default_value[0] == "=":
            for i, cell in enumerate(created_cells):
                old_value = cell.value
                try:
                    cell.value = increment_multiple_letters_with_numbers(cell.value, i)
                    calculate_formula(cell)
                except:
                    cell.value = old_value
                    calculate_formula(cell)
        else:
            for cell in created_cells:
                if cell.value and '=' in cell.value:
                    calculate_formula(cell)


        #Копируем если есть перенос
        if with_copy:
            cells_for_copy = Cell.objects.filter(column=current_column_id)
            for cell_for_copy in cells_for_copy:
                for cell in cells:
                    if cell.row == cell_for_copy.row:
                        cell.value = cell_for_copy.value
                        cell.save()

        normalize_row_orders(table)

        # Накидываем права на новый столбец
        user_ids = TablePermission.objects.filter(table=table, can_edit=True).values_list('user_id', flat=True)
        profiles = {p.user_id:p for p in Profile.objects.filter(user_id__in=user_ids).only("id", "user_id", "employee_id")}
        filial_ids = {p.employee.id_filial for p in profiles.values() if p.employee_id}
        filial_by_id = {f.code:f for f in Filial.objects.filter(code__in=filial_ids).only("id")}
        with transaction.atomic():
            column_permissions = [
                ColumnPermission(
                    user=uid,
                    column=column.id,
                    table=table.id,
                    can_edit=True,
                    can_view=True,
                )
                for uid in user_ids
            ]
            ColumnPermission.objects.bulk_create(column_permissions, ignore_conflicts=True)
            column_filial_permissions = []
            for uid in user_ids:
                profile = profiles.get(uid)
                if not profile or not profile.employee_id:
                    continue
                filial = filial_by_id.get(profile.employee.id_filial)
                if not filial:
                    continue
                column_filial_permissions.append(
                    ColumnFilialPermission(
                        table=table.id,
                        filial=filial,
                        column=column,
                        can_edit=True,
                        can_delete=True,
                    )
                )
            ColumnFilialPermission.objects.bulk_create(
                column_filial_permissions, ignore_conflicts=True
            )


        #Для автоинкремента
        update_auto_column(table.id)

        return column

    def get_select_values(self, obj):
        values = SelectType.objects.filter(column_id=obj.id).exclude(name__isnull=True).exclude(name="").values('name', 'filial_owner_code')
        return values


class CellFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CellFile
        fields = '__all__'
        read_only_fields = ['id', 'uploaded_at', 'updated_at', 'version', 'file_extension', 'file_size']

    def create(self, validated_data):
        """Создание новой записи файла - НЕ проверяем существование файла"""
        # Убираем проверку на существование файла для ячейки
        # Разрешено множество файлов на ячейку

        # Обрабатываем файл
        file_content = validated_data.pop('file', None)
        filename = validated_data.get('filename', 'unnamed_file')

        if file_content:
            # Вычисляем размер и расширение
            file_size = len(file_content)
            file_extension = ''
            if '.' in filename:
                file_extension = filename.split('.')[-1].lower()

            validated_data['file_size'] = file_size
            validated_data['file_extension'] = file_extension

        validated_data['version'] = 1
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Обновление (замена) файла - создаем новую версию"""
        # Сохраняем текущую версию в историю
        self._save_to_history(instance)

        # Обрабатываем новый файл
        file_content = validated_data.pop('file', None)

        if file_content:
            instance.file = file_content
            instance.file_size = len(file_content)
            instance.version += 1

            # Обновляем имя если нужно
            if 'filename' in validated_data:
                instance.filename = validated_data['filename']
                if '.' in instance.filename:
                    instance.file_extension = instance.filename.split('.')[-1].lower()

        # Обновляем остальные поля
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def _save_to_history(self, instance):
        """Сохранение текущей версии в историю"""
        try:
            CellFileHistory.objects.create(
                cell_file=instance,
                file=instance.file,
                filename=instance.filename,
                version=instance.version,
                replaced_by=instance.uploaded_by
            )
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")


class CellSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Cell
        fields = ['id', 'column', 'row', 'value', 'formula_value', 'files', 'color']
        extra_kwargs = {
            'column': {'required': False},
            'row': {'required': False},
        }

    def get_files(self, obj):
        """Возвращает список файлов с их download_url внутри"""
        if hasattr(obj, 'prefetched_files') and obj.prefetched_files:
            return obj.prefetched_files
        return []

    def update(self, instance, validated_data):
        super().update(instance, validated_data)
        user = self.context['request'].user
        table_id = Cell.objects.get(id=instance.id).table_id
        update_auto_column(table_id)

        # Логируем изменения
        cell_edit_log_record = CellEditLog(
            cell_id=instance.id,
            user_id=user.id,
            old_value="",
            new_value=instance.value,
            row_id=instance.row
        )
        cell_edit_log_record.save()

        return instance

    def get_files_download_urls(self, obj):
        """Возвращает список URL для скачивания всех файлов"""
        if hasattr(obj, 'prefetched_files') and obj.prefetched_files:
            return [f'https://sco1-vapp-09.sgp.ru/table_service/api/cellfiles/{file.id}/download/' for file in obj.prefetched_files]
        return []

    def get_current_file(self, obj):
        """Возвращает последний (текущий) файл для обратной совместимости"""
        if hasattr(obj, 'prefetched_files') and obj.prefetched_files:
            current = obj.prefetched_files[0]  # Первый файл (самый новый из-за order_by)
            return {
                'id': current.id,
                'filename': current.filename,
                'file_size': current.file_size,
                'file_extension': current.file_extension,
                'content_type': current.content_type,
                'version': current.version,
                'uploaded_at': current.uploaded_at,
                'updated_at': current.updated_at,
                'uploaded_by': current.uploaded_by,
                'description': current.description,
            }
        return None


class RowSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    order = serializers.IntegerField(read_only=True)
    id = serializers.IntegerField(read_only=True)
    cells = serializers.SerializerMethodField()
    cells_list = serializers.SerializerMethodField()

    class Meta:
        model = Row
        fields = ['id', 'order', 'created_by', "table", "cells", "cells_list", 'created_date']
        extra_kwargs = {
            'created_date': {'read_only': True},
        }

    def get_cells(self, obj):
        """Супер-оптимизация - только файловые колонки и один запрос к файлам"""

        # Получаем ID файловых колонок
        file_column_ids = set(Column.objects.filter(
            table=obj.table,
            data_type='file'
        ).values_list('id', flat=True))

        if not file_column_ids:
            # Если нет файловых колонок, возвращаем ячейки без файлов
            cells = Cell.objects.filter(row=obj.id).values(
                'id', 'column', 'row', 'value', 'formula_value', 'color'
            )
            return list(cells)

        # Получаем все ячейки строки
        cells = list(Cell.objects.filter(row=obj.id).values(
            'id', 'column', 'row', 'value', 'formula_value', 'color'
        ))

        if not cells:
            return []

        # Получаем ID только файловых ячеек
        file_cell_ids = [cell['id'] for cell in cells if cell['column'] in file_column_ids]

        # Если есть файловые ячейки - загружаем файлы
        files_by_cell = {}
        if file_cell_ids:
            request = self.context.get('request')

            files = CellFile.objects.filter(cell_id__in=file_cell_ids).values(
                'id', 'cell_id', 'filename', 'file_size', 'file_extension',
                'content_type', 'version', 'uploaded_at', 'updated_at',
                'uploaded_by', 'description'
            ).order_by('-uploaded_at')

            # Группируем и добавляем URL для скачивания прямо в файл
            for file in files:
                cell_id = file['cell_id']
                if cell_id not in files_by_cell:
                    files_by_cell[cell_id] = []

                # Формируем объект файла с URL для скачивания
                file_data = {
                    'id': file['id'],
                    'filename': file['filename'],
                    'file_size': file['file_size'],
                    'file_extension': file['file_extension'],
                    'content_type': file['content_type'],
                    'version': file['version'],
                    'uploaded_at': file['uploaded_at'],
                    'updated_at': file['updated_at'],
                    'uploaded_by': file['uploaded_by'],
                    'description': file['description'],
                    'download_url': f'https://sco1-vapp-09.sgp.ru/api/cellfiles/{file["id"]}/download/'
                    #'download_url': f'http://localhost:8003/api/cellfiles/{file["id"]}/download/'
                }

                files_by_cell[cell_id].append(file_data)

        # Формируем результат
        result = []

        for cell in cells:
            cell_id = cell['id']
            is_file_column = cell['column'] in file_column_ids

            cell_data = {
                'id': cell['id'],
                'column': cell['column'],
                'row': cell['row'],
                'value': cell['value'],
                'formula_value': cell['formula_value'],
                'files': files_by_cell.get(cell_id, []) if is_file_column else [],
                'color': cell['color'],
            }

            result.append(cell_data)

        return result

    def get_cells_list(self, obj):
        """Аналогичная оптимизация для cells_list"""
        return self.get_cells(obj)

    def create(self, validated_data):
        table = validated_data.pop('table')
        position = None
        row_for_copy = None
        with_copy = False
        user = None

        if 'withCopy' in self.context['request'].data:
            with_copy = self.context['request'].data['withCopy']
            normalize_row_orders(table)
        if 'currentRowId' in self.context['request'].data:
            current_row_id = self.context['request'].data['currentRowId']
            row_for_copy = Row.objects.get(id=current_row_id)
        if 'position' in self.context['request'].data:
            position = self.context['request'].data['position']
        owner = self.context['request'].user

        # Нормализуем порядок перед вставкой тк при удалении остаются дырки
        all_rows = Row.objects.filter(table=table).order_by('order')
        rows_count = all_rows.count()

        if isinstance(position, int):
            if position < 0:
                position = 0
            elif position > rows_count:
                position = rows_count
            order = position
            Row.objects.filter(table=table, order__gte=position).update(order=F('order') + 1)
        else:
            last_row = Row.objects.filter(table=table).last()
            order = last_row.order + 1 if last_row else 0

        row = Row.objects.create(table=table, created_by=owner, order=order)
        request = self.context.get('request')

        if request and hasattr(request, 'user'):
            user = request.user
            row.created_by = user
            row.save()

        columns = table.columns.all()
        filial_code = Profile.objects.get(user=owner).employee.id_filial
        cells = [Cell(row=row.id, column=column.id, table_id=table.id, value=filial_code if column.default_value_from_user_filial_code else column.default_value) for column in
                 columns]

        prev_row = Row.objects.filter(table=table, order=row.order - 1).first()

        if prev_row:
            for cell in cells:
                column = Column.objects.get(id=cell.column)
                # Если указано свойство значение по умолчанию из ячейки пред строки, то ищем пред строку и берем формулу оттуда
                if column.default_value_from_prev_row:
                    prev_cell = Cell.objects.filter(row=prev_row.id, column=column.id).first()
                    if prev_cell and prev_cell.value and prev_cell.value.startswith('='):
                        update_value = increment_multiple_letters_with_numbers(prev_cell.value, 1)
                        cell.value = update_value
                        calculate_formula(cell, False)

        Cell.objects.bulk_create(cells)

        if row_for_copy and with_copy:
            cells_for_copy = Cell.objects.filter(row=row_for_copy.id)
            for cell_for_copy in cells_for_copy:
                for cell in cells:
                    if cell.column == cell_for_copy.column:
                        cell.value = cell_for_copy.value
                        cell.save()

        # Добавил ограничение по филиалу
        if user and hasattr(user, 'profile') and user.profile.employee:
            filial_code = user.profile.employee.id_filial
            filial_id = Filial.objects.get(code=filial_code).id
            RowFilialPermission.objects.create(row=row.id, filial=filial_id)

        # Всегда добавляем владельцу и админам права на строку
        for table_permission in TablePermission.objects.filter(table_id=table, role__in=['owner', 'admin']):
            RowPermission.objects.create(
                table=table.id,
                row=row.id,
                user=table_permission.user.id,
                can_edit=True,
                can_delete=True
            )

        # Для автоинкремента
        update_auto_column(table.id)

        return row


class TableDetailSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    created_at = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    id = serializers.IntegerField(read_only=True)


    class Meta:
        model = Table
        fields = ['id','title','owner','created_at','share_token', 'with_cell_confirm', 'with_cell_logging','delete_row', 'role', 'show_locked_row',
                  'allow_user_insert_row', 'allow_user_insert_column', 'open_last_page_by_default']
        extra_kwargs = {
            'share_token': {'read_only': True},
            'created_at': {'read_only': True},
            'with_cell_confirm': {'required': False},
            'with_cell_logging': {'required': False},
            'delete_row': {'required': False},
        }

    def get_role(self, obj):
        if 'request' not in self.context:
            return None
        current_user = self.context['request'].user
        # Сначал просто проверка на наличие направленных прав
        if len(TablePermission.objects.filter(table=obj, user_id=current_user.id)) > 0:
            return TablePermission.objects.get(table=obj, user_id=current_user.id).role
        else:
            # Если есть филиальные права, то возвращаем роль user (подойдет для большинства)
            filial_code = Profile.objects.filter(user=current_user).select_related('employee').values_list('employee__id_filial', flat=True).first()
            filial = Filial.objects.get(code=filial_code)
            if len(TableFilialPermission.objects.filter(table=obj, filial=filial)) > 0:
                return 'user'
            else:
                return  ''


    def get_created_at(self, obj):
        return int(obj.created_at.timestamp()) * 1000


class TableListSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    created_at = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Table
        fields  = ['id','title','owner','created_at','share_token', 'with_cell_confirm', 'with_cell_logging','delete_row', 'profile']
        extra_kwargs = {
            'share_token': {'read_only': True},
            'created_at': {'read_only': True},
            'delete_row': {'required': False},
        }

    def get_created_at(self, obj):
        return int(obj.created_at.timestamp()) * 1000

    def get_profile(self, obj):
        profile = Profile.objects.get(user=obj.owner)
        return ProfileSerializer(profile).data


    def create(self, validated_data):
        owner = self.context['request'].user
        created_at = datetime.now()
        title = validated_data.pop('title')
        with_cell_confirm = validated_data.pop('with_cell_confirm')
        with_cell_logging = validated_data.pop('with_cell_logging')
        table = Table.objects.create(owner=owner, title=title, created_at=created_at, with_cell_confirm=with_cell_confirm, with_cell_logging=with_cell_logging)
        TablePermission.objects.create(table=table, user=owner, role='owner')
        notify_table_update()
        return table


class TablePermissionsSerializer(serializers.ModelSerializer):
    # В модельке сделать уникальный ключ по двум полям, может быть задвоение
    user_id = serializers.IntegerField()
    user = UserSerializer(read_only=True)
    class Meta:
        model = TablePermission
        fields = ['id','user_id','can_view', 'can_edit', 'table', 'user', 'role']

    def create(self, validated_data):
        user = get_object_or_404(User,id=validated_data['user_id'])
        table = validated_data['table']
        table_id = table.id

        with transaction.atomic():
            permissions = TablePermission.objects.create(user=user, **validated_data)
            with connection.cursor() as cursor:
                cursor.execute(
                    '''
                        INSERT INTO tables_rowpermission 
                            ("user", "row", "table", can_edit, can_delete)
                        SELECT %s, r.id, %s, TRUE, TRUE
                        FROM tables_row AS r 
                        WHERE r.table_id = %s
                        ON CONFLICT DO NOTHING
                    ''', [user.id, table_id, table_id]
                )

                cursor.execute(
                    """
                        INSERT INTO tables_columnpermission
                             ("user", "column", "table", can_view, can_edit)
                        SELECT %s, c.id, %s, TRUE, TRUE
                        FROM tables_column AS c
                        WHERE c.table_id = %s
                        ON CONFLICT DO NOTHING
                    """, [user.id, table_id, table_id]
                )


            return permissions


    def update(self, request, pk=None):
        with transaction.atomic():
            table_permission = get_object_or_404(TablePermission, id=request.id)

            table_permission.can_edit = pk.get('can_edit')
            table_permission.role = pk.get('role')
            table_permission.save()
            can_edit = pk.get('can_edit') if pk.get('can_edit') else True
            can_delete = pk.get('can_delete') if pk.get('can_delete') else True
            can_view = pk.get('can_view') if pk.get('can_view') else True
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                        UPDATE tables_rowpermission
                        SET can_edit = %s, can_delete = %s
                        WHERE "table" = %s and "user" = %s
                    """, [can_edit, can_delete, request.table_id, request.user_id]
                )
                cursor.execute(
                    """
                        UPDATE tables_columnpermission
                        SET can_view = %s, can_edit = %s
                        WHERE "table" = %s and "user" = %s
                    """, [can_view, can_edit, request.table_id, request.user_id]
                )
        return table_permission



class TableFilialPermissionsSerializer(serializers.ModelSerializer):
    filial_id = serializers.IntegerField()
    filial = FilialSerializer(read_only=True)
    class Meta:
        model = TableFilialPermission
        fields = ['id','table','filial_id','can_view','filial']

    def create(self, validated_data):
        filial_id = validated_data.pop('filial_id')
        filial = get_object_or_404(Filial, id=filial_id)
        table = validated_data['table']

        with transaction.atomic():
            permissions = TableFilialPermission.objects.create(filial=filial, **validated_data)

            with connection.cursor() as cursor:
                cursor.execute(
                    '''
                    INSERT INTO tables_columnfilialpermission
                        ("filial_id", "column_id", "table", can_delete, can_edit)
                    SELECT %s, c.id, %s, TRUE, TRUE
                    FROM tables_column AS c
                    WHERE c.table_id = %s ON CONFLICT DO NOTHING
                    ''',
                    [filial.id, table.id, table.id]
                )
                cursor.execute(
                    """
                    INSERT INTO tables_rowfilialpermission
                        ("filial", "row", can_delete, can_edit)
                    SELECT %s, r.id, TRUE, TRUE
                    FROM tables_row AS r
                    WHERE r.table_id = %s ON CONFLICT DO NOTHING
                    """,
                    [filial.id, table.id]
                )

        return permissions


class RowPermissionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    user = serializers.IntegerField()
    row = serializers.IntegerField()
    table = serializers.IntegerField()
    user_model = serializers.SerializerMethodField()
    class Meta:
        model = RowPermission
        fields = ['id','row','user', 'table', 'can_edit', 'can_delete', 'user_model']

    def create(self, validated_data):
        permissions = RowPermission.objects.create(row=validated_data['row'], user=validated_data['user'], table=validated_data['table'])
        return permissions

    def get_user_model(self, obj):
        user = User.objects.get(id=obj.user)
        return UserSerializer(user).data


class RowFilialPermissionSerializer(serializers.ModelSerializer):
    row = serializers.IntegerField()
    id = serializers.IntegerField(read_only=True)
    filial_id = serializers.SerializerMethodField()
    class Meta:
        model = RowFilialPermission
        fields = ['id', 'filial_id', 'filial','can_edit','can_delete', 'row']

    def get_filial_id(self, obj):
        return obj.filial



    def create(self, validated_data):
        permissions = RowFilialPermission.objects.create(filial=validated_data['filial'], row=validated_data['row'], can_edit=validated_data['can_edit'], can_delete=validated_data['can_delete'])
        return permissions


class CellLockSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    cell = CellSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    class Meta:
        model = CellLock
        fields = ['id','cell','user','locked_at']


class FileUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(
        max_length=1024,
        allow_empty_file=False,
        help_text='KEK'
    )
    name = serializers.CharField()
    # class Meta:
    #     fields = ['name','file']
    #     # model = File
    #     serializers.raise_errors_on_nested_writes = False


class ColumnPermissionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    can_view = serializers.BooleanField(required=False)
    can_edit = serializers.BooleanField(required=False)
    table = serializers.IntegerField()
    user = serializers.IntegerField()
    column = serializers.IntegerField()
    user_model = serializers.SerializerMethodField()

    class Meta:
        model = ColumnPermission
        fields = ['id','column','user','table','can_view','can_edit', 'user_model']

    def create(self, validated_data):
        permissions = ColumnPermission.objects.create(column=validated_data['column'],
                                                      user=validated_data['user'],
                                                      table=validated_data['table'],
                                                      can_view=validated_data['can_view'],
                                                      can_edit=validated_data['can_edit'],
                                                      )
        return permissions

    def get_user_model(self, obj):
        user = User.objects.get(id=obj.user)
        return UserSerializer(user).data


class ColumnFilialPermissionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    can_delete = serializers.BooleanField(required=False)
    can_edit = serializers.BooleanField(required=False)
    filial_id = serializers.IntegerField()
    column_id = serializers.IntegerField(write_only=True)
    table_id = serializers.IntegerField(write_only=True)
    class Meta:
        model = ColumnFilialPermission
        fields = ['id','column_id', 'filial_id', 'filial', 'can_delete', 'can_edit', 'table', 'table_id']

    def create(self, validated_data):
        column = get_object_or_404(Column,id=validated_data['column_id'])
        filial = get_object_or_404(Filial,id=validated_data['filial_id'])
        if filial and column:
            permissions = ColumnFilialPermission.objects.create(filial=filial, column=column, table=validated_data['table_id'])
            return permissions
        return None


class SelectTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelectType
        fields = '__all__'


class CellEditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CellEditLog
        fields = ['id', 'user', 'old_value', 'new_value', 'cell']
    user = serializers.SerializerMethodField()
    cell = serializers.SerializerMethodField()

    def get_user(self, obj):
        user = User.objects.get(id=obj.user_id)
        return user.last_name + " " + user.first_name

    def get_cell(self, obj):
        cell = Cell.objects.filter(id=obj.cell_id).first()
        if cell is not None:
            row = Row.objects.get(id=cell.row)
            column = Column.objects.get(id=cell.column)
            return numberToChar(column.order) + "" + str(row.order+1)
        return "??"


class CellCommentSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = CellComment
        fields = ['id','cell_id','user_id','text','date', 'user']

    def get_user(self, obj):
        try:
            user = User.objects.get(id=obj.user_id)
            return UserSerializer(user).data
        except User.DoesNotExist:
            return None


class CellFileSerializer(serializers.ModelSerializer):
    """Сериализатор для файлов ячейки"""

    # Поле для приема файла в base64 (для JSON) или как UploadedFile
    file_data = serializers.CharField(write_only=True, required=False, help_text="Файл в base64")
    uploaded_file = serializers.FileField(write_only=True, required=False, help_text="Загружаемый файл")

    # Читаемые поля
    cell_info = serializers.SerializerMethodField(read_only=True)
    file_size_kb = serializers.SerializerMethodField(read_only=True)
    is_large_file = serializers.BooleanField(read_only=True)

    class Meta:
        model = CellFile
        fields = [
            'id', 'cell', 'cell_info', 'filename', 'file_extension',
            'file_size', 'file_size_kb', 'content_type', 'is_large_file',
            'uploaded_at', 'updated_at', 'version', 'previous_file_hash',
            'uploaded_by', 'description', 'file_data', 'uploaded_file'
        ]
        read_only_fields = ['id', 'uploaded_at', 'updated_at', 'version',
                            'file_extension', 'file_size', 'previous_file_hash']

    def get_cell_info(self, obj):
        """Информация о связанной ячейке"""
        return {
            'id': obj.cell.id,
            'row': obj.cell.row,
            'column': obj.cell.column,
            'value_preview': obj.cell.value[:50] if obj.cell.value else None
        }

    def get_file_size_kb(self, obj):
        """Размер файла в килобайтах"""
        if obj.file_size:
            return round(obj.file_size / 1024, 2)
        return None

    def get_is_large_file(self, obj):
        """Флаг большого файла (> 1MB)"""
        return obj.file_size and obj.file_size > 1024 * 1024

    def validate(self, data):
        """Валидация входных данных"""
        # Проверка, что передан либо file_data, либо uploaded_file
        has_file_data = 'file_data' in data and data['file_data']
        has_uploaded_file = 'uploaded_file' in data and data['uploaded_file']

        if not has_file_data and not has_uploaded_file:
            raise serializers.ValidationError(
                "Необходимо передать file_data (base64) или uploaded_file"
            )

        return data

    def _process_file(self, file_content, filename):
        """Обработка файла: вычисление размера, хеша и т.д."""
        file_size = len(file_content)

        # Вычисляем хеш файла
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Определяем расширение
        file_extension = ''
        if '.' in filename:
            file_extension = filename.split('.')[-1].lower()

        # Определяем MIME-тип (простой вариант)
        content_type = self._get_content_type(file_extension)

        return {
            'file_content': file_content,
            'file_size': file_size,
            'file_hash': file_hash,
            'file_extension': file_extension,
            'content_type': content_type
        }

    def _get_content_type(self, extension):
        """Определение MIME-типа по расширению"""
        mime_types = {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'txt': 'text/plain',
            'csv': 'text/csv',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }
        return mime_types.get(extension, 'application/octet-stream')

    def create(self, validated_data):
        """Создание новой записи файла"""
        # Извлекаем данные файла
        file_data = validated_data.pop('file_data', None)
        uploaded_file = validated_data.pop('uploaded_file', None)

        # Получаем содержимое файла
        if file_data:
            # Декодируем base64
            import base64
            try:
                file_content = base64.b64decode(file_data)
                filename = validated_data.get('filename', 'unnamed_file')
            except Exception as e:
                raise serializers.ValidationError(f"Ошибка декодирования base64: {str(e)}")
        else:
            # Работа с загруженным файлом
            file_content = uploaded_file.read()
            filename = uploaded_file.name

        # Обрабатываем файл
        file_info = self._process_file(file_content, filename)

        # Проверяем, существует ли уже файл для этой ячейки
        cell = validated_data.get('cell')

        # Создаем запись
        validated_data['file'] = file_info['file_content']
        validated_data['file_size'] = file_info['file_size']
        validated_data['file_extension'] = file_info['file_extension']
        validated_data['content_type'] = file_info['content_type']
        validated_data['filename'] = filename
        validated_data['version'] = 1

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Обновление (замена) файла"""
        # Сохраняем текущую версию в историю (опционально)
        self._save_to_history(instance)

        # Извлекаем данные нового файла
        file_data = validated_data.pop('file_data', None)
        uploaded_file = validated_data.pop('uploaded_file', None)

        if file_data or uploaded_file:
            # Получаем новое содержимое
            if file_data:
                file_content = base64.b64decode(file_data)
                filename = validated_data.get('filename', instance.filename)
            else:
                file_content = uploaded_file.read()
                filename = uploaded_file.name

            # Обрабатываем новый файл
            file_info = self._process_file(file_content, filename)

            # Сохраняем хеш предыдущего файла
            old_file_hash = hashlib.sha256(instance.file).hexdigest()

            # Обновляем поля
            instance.file = file_info['file_content']
            instance.file_size = file_info['file_size']
            instance.file_extension = file_info['file_extension']
            instance.content_type = file_info['content_type']
            instance.filename = filename
            instance.version += 1
            instance.previous_file_hash = old_file_hash

        # Обновляем остальные поля
        for attr, value in validated_data.items():
            if attr not in ['file_data', 'uploaded_file']:
                setattr(instance, attr, value)

        instance.save()
        return instance

    def _save_to_history(self, instance):
        """Сохранение текущей версии в историю"""
        try:
            CellFileHistory.objects.create(
                cell_file=instance,
                file=instance.file,
                filename=instance.filename,
                version=instance.version,
                replaced_by=instance.uploaded_by
            )
        except Exception as e:
            # Логируем ошибку, но не прерываем обновление
            print(f"Ошибка сохранения истории: {e}")


class CellFileListSerializer(serializers.ModelSerializer):
    """Упрощенный сериализатор для списка файлов"""

    cell_location = serializers.SerializerMethodField()

    class Meta:
        model = CellFile
        fields = ['id', 'filename', 'file_extension', 'file_size',
                  'version', 'uploaded_at', 'cell_location']

    def get_cell_location(self, obj):
        return f"{obj.cell.row}:{obj.cell.column}"



@transaction.atomic
def add_side_permission_for_row_value_permissions(table_id:int, user_ids:list[int]):
    table = get_object_or_404(Table, pk=table_id)
    column_ids = list(Column.objects.filter(table=table).values_list('id', flat=True))
    table_permissions = []
    column_permissions = []
    for user_id in user_ids:
        try:
            user = get_object_or_404(User, pk=user_id)
            table_permission = TablePermission(
                table=table,
                user=user,
            )
            table_permissions.append(table_permission)
        except User.DoesNotExist:
            continue
    for column in product(user_ids, column_ids):
        column_permission = ColumnPermission(
            table=table_id,
            user=column[0],
            column=column[1],
        )
        column_permissions.append(column_permission)
    TablePermission.objects.bulk_create(table_permissions, ignore_conflicts=True)
    ColumnPermission.objects.bulk_create(column_permissions, ignore_conflicts=True)


@transaction.atomic
def update_row_permission_for_value_permissions(table_id:int):
    rowvalue_permissions = RowValuePermission.objects.filter(table_id=table_id)
    if not rowvalue_permissions.exists():
        raise ValidationError(detail="Такая таблица не найдена")
    flat_rowvalue_permissions = rowvalue_permissions.values_list("column_id", "cell_value", "user_ids")
    row_ids_to_update = []
    for flat_permission in flat_rowvalue_permissions:
        rows = Cell.objects.filter(table_id=table_id, column=flat_permission[0], value=flat_permission[1]).values_list("row",
                                                                                                                 flat=True)
        if rows.exists():
            row_ids_to_update.append({'rows': rows, 'user_ids': flat_permission[2]})
    if len(row_ids_to_update) == 0:
        raise ValidationError("Отсутвуют данные для обновления")
    rows_permission_to_update = []
    for item in row_ids_to_update:
        for row, user_id in product(item['rows'], item['user_ids']):
            rows_permission_to_update.append({'row': row, 'user_id': user_id})
    if len(rows_permission_to_update) == 0:
        raise ValidationError("Отсутвуют права для обновления")
    row_permission_to_update = []
    for row in row_ids_to_update:
        user_ids = row['user_ids']
        rows = row['rows']
        all_combinations = list(product(rows, user_ids))
        for combination in all_combinations:
            row_permission_to_update.append(RowPermission(table=table_id, row=combination[0], user=combination[1]))
    RowPermission.objects.bulk_create(row_permission_to_update, ignore_conflicts=True)



class RowValuePermissionSerializer(serializers.ModelSerializer):

    class Meta:
        model = RowValuePermission
        fields = ['id', 'table_id', 'column_id', 'user_ids', 'cell_value']
        read_only_fields = ['id']

    def create(self, validated_data):
        instance = super().create(validated_data)
        table = instance.table_id
        user_ids = instance.user_ids
        add_side_permission_for_row_value_permissions(table.id, user_ids)
        update_row_permission_for_value_permissions(table.id)
        return instance


    def update(self, instance, validated_data):
        instance = super().validated_data(instance, validated_data)
        table = instance.table_id
        user_ids = instance.user_ids
        add_side_permission_for_row_value_permissions(table.id, user_ids)
        update_row_permission_for_value_permissions(table.id)
        return instance

