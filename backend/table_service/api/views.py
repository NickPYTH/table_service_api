import json
import math
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from itertools import chain, product

from django.contrib.auth.models import User
from django.db import transaction, connection
from django.db.models import Q, Max, F, Min, Count
from django.http import Http404, HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework import viewsets, generics
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from .filters import ColumnFilterBackend

from tables.models import CellEditLog, Filial, Department, Employee, Profile, Admin, Table, Cell, Column, Row, \
    RowPermission, \
    TablePermission, TableFilialPermission, RowFilialPermission, CellLock, ColumnPermission, SelectType, CellComment, \
    ColumnFilialPermission, CellFile, RowValuePermission
from .formula_parser import calculate_formula
from .helper import get_table_ids_permissions, FileUploadBrowsableRenderer, import_to_existing_table, \
    export_table, import_table, get_columns_ids_permissions
from .import_utils import fast_import_table, schedule_task, schedule_task_in_db
from .serializers import (
    UserSerializer,
    FilialSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    ProfileSerializer,
    AdminSerializer,
    ProfileCreateUpdateSerializer,
    TableListSerializer, TableDetailSerializer, CellSerializer, ColumnSerializer, RowSerializer,
    RowPermissionSerializer, TablePermissionsSerializer, TableFilialPermissionsSerializer,
    RowFilialPermissionSerializer, SelectTypeSerializer, CellEditLogSerializer, update_auto_column,
    ColumnPermissionSerializer, CellCommentSerializer, normalize_row_orders, CellFileSerializer, CellFileListSerializer,
    ColumnFilialPermissionSerializer, RowValuePermissionSerializer
)
from .utils import send_table_update, send_cells_update, send_row
from .scheduler import scheduler

import logging
logger = logging.getLogger(__name__)

class CellPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'limit'
    max_page_size = 10000

    def get_paginated_response(self, data):
        search_value = self.request.query_params.get('search', '')

        response_data = {
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'search_info': {
                'value': search_value,
                'has_search': bool(search_value)
            },
            'results': data
        }

        return Response(response_data)

    def paginate_queryset(self, queryset, request, view=None):
        return super().paginate_queryset(queryset, request, view)


class RowPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'limit'
    max_page_size = 10000

    def get_paginated_response(self, data):
        search_value = self.request.query_params.get('search', '')

        response_data = {
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'search_info': {
                'value': search_value,
                'has_search': bool(search_value)
            },
            'results': data
        }

        return Response(response_data)

    def paginate_queryset(self, queryset, request, view=None):
        return super().paginate_queryset(queryset, request, view)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        table_id = self.request.query_params.get('table_id', None)
        row_id = self.request.query_params.get('row_id', None)
        column_id = self.request.query_params.get('column_id', None)
        user_ids = self.request.query_params.get('user_ids', None)
        if user_ids:
            return queryset.filter(id__in=user_ids.split(','))
        if row_id and table_id:
            user_ids_table = TablePermission.objects.filter(table_id=table_id).values_list('user_id', flat=True)
            user_ids_row = RowPermission.objects.filter(table=table_id, row=row_id).values_list('user', flat=True)
            user_ids = set(user_ids_table).difference(set(user_ids_row))
            queryset = queryset.filter(id__in=user_ids)
        elif column_id and table_id:
            user_ids_table = TablePermission.objects.filter(table_id=table_id).values_list('user_id', flat=True)
            user_ids_column = ColumnPermission.objects.filter(table=table_id, column=column_id).values_list('user', flat=True)
            user_ids = set(user_ids_table).difference(set(user_ids_column))
            queryset = queryset.filter(id__in=user_ids)
        elif table_id:
            user_ids = TablePermission.objects.filter(table_id=table_id).values_list('user__id', flat=True)
            queryset = queryset.exclude(id__in=user_ids)
        return queryset


class FilialViewSet(viewsets.ModelViewSet):
    queryset = Filial.objects.all()
    serializer_class = FilialSerializer

    # permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    def get_queryset(self):
        queryset = super().get_queryset()
        row_id = self.request.query_params.get('row_id')
        table_id = self.request.query_params.get('table_id')
        column_id = self.request.query_params.get('column_id')
        if row_id:
            row = get_object_or_404(Row, pk=row_id)
            if row:
                filial_ids = RowFilialPermission.objects.filter(row=row_id).values_list('filial', flat=True)
                queryset = queryset.exclude(id__in=filial_ids)
            else:
                return queryset.none()
        if table_id:
            table = get_object_or_404(Table, pk=table_id)
            if table:
                filial_ids = TableFilialPermission.objects.filter(table=table).values_list('filial', flat=True)
                queryset = queryset.exclude(id__in=filial_ids)
            else:
                return queryset.none()
        if column_id:
            column = get_object_or_404(Column, pk=column_id)
            filial_ids = ColumnFilialPermission.objects.filter(column=column).values_list('filial', flat=True)
            return queryset.exclude(id__in=filial_ids)

        return queryset


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    # permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer

    # permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    def get_queryset(self):
        queryset = super().get_queryset()
        filial_id = self.request.query_params.get('filial_id')
        if filial_id:
            queryset = queryset.filter(id_filial=filial_id)
        return queryset


class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()

    # permission_classes = [permissions.IsAuthenticated]
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProfileCreateUpdateSerializer
        return ProfileSerializer

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Profile.objects.all()
        return Profile.objects.filter(user=self.request.user)


class AdminViewSet(viewsets.ModelViewSet):
    queryset = Admin.objects.all()
    serializer_class = AdminSerializer
    # permission_classes = [permissions.IsAdminUser]


class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    # permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        return user


class TableListViewSet(viewsets.ModelViewSet):
    queryset = Table.objects.all()
    serializer_class = TableListSerializer

    # ПОПРОБОВАТЬ ЗАСУНУТЬ ОПРЕДЕЛНИЕ В СТАНДАРТНЫЕ ОГРАНИЧЕНИЯ Permissions
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.id == 1:
            return  queryset
        all_permissions = get_table_ids_permissions(user)
        if all_permissions:
            queryset = queryset.filter(id__in=all_permissions)
        else:
            queryset = queryset.none()
        return queryset


class TableDetailViewSet(viewsets.ModelViewSet):
    serializer_class = TableDetailSerializer
    queryset = Table.objects.all()

    @action(detail=True, methods=['get'], url_path='locks')
    def cell_lock(self, request, pk=None):
        columns_ids = Column.objects.filter(table_id=pk).values_list('id', flat=True)
        cells_ids = Cell.objects.filter(column__in=columns_ids).values_list('id', flat=True)
        cells_lock = CellLock.objects.filter(cell_id__in=cells_ids).select_related('cell')
        locks = [{'cell_id': lock.cell_id, 'user_id': lock.user_id} for lock in cells_lock]
        return Response(locks)

    @action(detail=True, methods=['get'], url_path='not_locked')
    def not_locked(self, request, pk=None):
        columns_ids = Column.objects.filter(table_id=pk).values_list('id', flat=True)
        cells_ids = Cell.objects.filter(column__in=columns_ids).values_list('id', flat=True)
        cells_locked = CellLock.objects.filter(cell_id__in=cells_ids).select_related('cell').values_list('cell_id', 'user_id', flat=True)
        cells_not_locked = set(cells_ids) - set(cells_locked)
        return Response(cells_not_locked)

    @action(detail=True, methods=['get'], url_path='remove_locks')
    def remove_locks(self, request, pk=None):
        user = self.request.user
        columns_ids = Column.objects.filter(table_id=pk).values_list('id', flat=True)
        cells_ids = Cell.objects.filter(column__in=columns_ids).values_list('id', flat=True)
        try:
            CellLock.objects.filter(cell_id__in=cells_ids, user=user).delete()
            return Response({"success": True})
        except:
            return Response({"success": False})

    @action(detail=True, methods=['get'], url_path='export/(?P<format_type>[a-z]+)')
    def export(self, request, pk=None, format_type='xlsx'):
        if format_type not in ['csv', 'xls', 'xlsx']:
            return Response({'error': 'Invalid format'}, status=400)
        try:
            response = export_table(request, pk, format_type)
            return response
        except:
            return Response({'error': 'Ошибка экспорта'}, status=400)

    @action(detail=True, methods=['post'], url_path='update_row_value_permissions')
    def update_row_value_permissions(self, request, pk=None):
        rowvalue_permissions = RowValuePermission.objects.filter(table_id=pk)
        if not rowvalue_permissions.exists():
            raise NotFound(detail="Такая таблица не найдена")
        flat_rowvalue_permissions = rowvalue_permissions.values_list("column_id", "cell_value", "user_ids")
        row_ids_to_update = []
        for flat_permission in flat_rowvalue_permissions:
            rows = Cell.objects.filter(table_id=pk, column=flat_permission[0], value=flat_permission[1]).values_list("row", flat=True)
            if rows.exists():
                row_ids_to_update.append({'rows': rows, 'user_ids': flat_permission[2]})
        if len(row_ids_to_update) == 0:
            raise Http404("Отсутвуют данные для обновления")
        rows_permission_to_update = []
        for item in row_ids_to_update:
            for row, user_id in product(item['rows'], item['user_ids']):
                rows_permission_to_update.append({'row': row, 'user_id': user_id})
        if len(rows_permission_to_update) == 0:
            raise Http404("Отсутвуют права для обновления")
        row_permission_to_update = []
        column_ids = Column.objects.filter(table__id=pk).values_list('id', flat=True)
        column_permission_to_update = []
        table_permission_to_update = []
        for row in row_ids_to_update:
            user_ids = row['user_ids']
            rows = row['rows']
            for combination in list(product(rows, user_ids)):
                row_permission_to_update.append(RowPermission(table=pk, row=combination[0], user=combination[1]))
            for combination in list(product(column_ids, user_ids)):
                column_permission_to_update.append(ColumnPermission(column=combination[0], table=pk, user=combination[1]))
            for combination in list(product([pk], user_ids)):
                table = get_object_or_404(Table, pk=combination[0])
                user = get_object_or_404(User, pk=combination[1])
                table_permission_to_update.append(TablePermission(table=table, user=user))

        TablePermission.objects.bulk_create(table_permission_to_update, ignore_conflicts=True)
        ColumnPermission.objects.bulk_create(column_permission_to_update, ignore_conflicts=True)
        RowPermission.objects.bulk_create(row_permission_to_update, ignore_conflicts=True)
        return Response({"success": True})

    @action(detail=True, methods=['get'], url_path='get_view')
    def get_view(self, request, pk=None):
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        offset = (page - 1) * page_size
        columns = Column.objects.filter(table_id=pk).order_by("order")[offset:offset + page_size]
        if not columns.exists():
            return Response({"success": False, "error":"У таблицы нет колонок"}, status=400)
        column_ids = list(columns.values_list("id", flat=True))
        column_names = list(columns.values_list("name", flat=True))

        rows = Row.objects.filter(table_id=pk).order_by("order")
        if not rows.exists():
            return Response({"success":False, "error":"У таблицы нет строк"}, status=400)
        row_ids = list(rows.values_list("id", flat=True))

        cells = Cell.objects.filter(
            table_id=pk,
            column__in=column_ids,
            row__in=row_ids,
        ).values('row', 'column', 'value')

        cells_by_row = defaultdict(dict)
        for cell in cells:
            row_id = cell['row']
            col_id = cell['column']
            value = cell['value']
            cells_by_row[row_id][col_id] = value if value is not None else " "

        result_rows = []
        for row_id in row_ids:
            row_data = cells_by_row.get(row_id, {})
            row_cells = []
            for col_id in column_ids:
                value = row_data.get(col_id, '')
                row_cells.append(value if value is not None else " ")
            result_rows.append({
                'row_id': row_id,
                'cells': row_cells,
            })


        result = []
        result += [column_names]
        for row in result_rows:
            result += [row['cells']]
        return Response({
            "success": True,
            "result": result,
        })

    @action(detail=True, methods=['post'], url_path='create_view')
    def create_view(self, request, pk=None):
        try:
            if not Table.objects.filter(id=pk).exists():
                return Response(
                    {"success": False, "error": "Таблица не найдена"},
                    status=404
                )

            columns = Column.objects.filter(table_id=pk).order_by("order")
            if not columns.exists():
                return Response(
                    {"success": False, "error": "У таблицы нет колонок"},
                    status=400
                )

            rows = Row.objects.filter(table_id=pk).order_by("order")
            if not rows.exists():
                return Response(
                    {"success": False, "error": "У таблицы нет строк"},
                    status=400
                )

            view_name = f"view_{pk}"

            with connection.cursor() as cursor:
                cursor.execute("""
                               SELECT EXISTS (SELECT 1
                                              FROM information_schema.views
                                              WHERE table_name = %s)
                               """, [view_name])
                view_exists = cursor.fetchone()[0]

                if view_exists:
                    cursor.execute(f"DROP VIEW IF EXISTS {view_name} CASCADE")

            select_parts = []

            select_parts.append("SELECT")
            select_parts.append('    "row" AS row_id')

            for column in columns:
                col_id = column.id
                # Формируем уникальное имя поля: col_{id}_{original_name}
                safe_name = column.name.replace('"', '""')
                col_name = f"col_{col_id}_{safe_name}"
                select_parts.append(
                    f'    , MAX(CASE WHEN "column" = {col_id} THEN cell_value ELSE \'\' END) AS "{col_name}"'
                )

            select_parts.append("FROM (")
            select_parts.append("    SELECT")
            select_parts.append('        "row",')
            select_parts.append('        "column",')
            select_parts.append("        COALESCE(NULLIF(formula_value, ''), value) AS cell_value")
            select_parts.append(f"    FROM tables_cell")
            select_parts.append(f"    WHERE table_id = {pk}")
            select_parts.append('        AND "row" IN (')
            select_parts.append(f"            SELECT id FROM tables_row WHERE table_id = {pk}")
            select_parts.append("        )")
            select_parts.append(") AS cell_data")
            select_parts.append('GROUP BY "row"')
            select_parts.append('ORDER BY "row"')

            create_view_sql = f"CREATE VIEW {view_name} AS\n"
            create_view_sql += "\n".join(select_parts)

            with connection.cursor() as cursor:
                cursor.execute(create_view_sql)

            return Response({
                "success": True,
                "message": f"Представление {view_name} успешно создано",
                "view_name": view_name,
                "columns": [column.name for column in columns],
                "row_count": rows.count()
            })

        except Exception as e:
            return Response(
                {"success": False, "error": f"Ошибка при создании представления: {str(e)}"},
                status=500
            )

    @action(detail=True, methods=['post'])
    def set_permission(self, request, pk=None):
        with transaction.atomic():
            user_id = request.query_params.get('user_id')
            if user_id:
                # TODO Сюда добавить потом создание колонок
                if not TablePermission.objects.filter(table_id=pk, user_id=user_id).exists():
                    TablePermission.objects.create(table_id=pk, user_id=user_id)
                row_ids = Row.objects.filter(table_id=pk).values_list('id', flat=True)
                columns_ids = Column.objects.filter(table_id=pk).values_list('id', flat=True)
                column_permissions = []
                row_permissions = []
                for column_id in columns_ids:
                    columnpermission = ColumnPermission(table_id=pk, column=column_id)
                    column_permissions.append(columnpermission)
                else:
                    ColumnPermission.objects.bulk_create(column_permissions, ignore_conflicts=True)
                for row_id in row_ids:
                    rowpermission = RowPermission(row_id=row_id, user_id=user_id)  # TODO
                    row_permissions.append(rowpermission)
                else:
                    RowPermission.objects.bulk_create(row_permissions, ignore_conflicts=True)
                return Response({"success": True})
            return Response({"success": False})

    @action(detail=True, methods=['post'])
    def set_filial_permission(self, request, pk=None):
        with transaction.atomic():
            filial_id = request.query_params.get('filial_id')
            if filial_id:
                if not TableFilialPermission.objects.filter(filial_id=filial_id, table_id=pk).exists():
                    TableFilialPermission.objects.create(filial_id=filial_id, table_id=pk)
                row_ids = Row.objects.filter(table_id=pk).values_list('id', flat=True)
                columns_ids = Column.objects.filter(table_id=pk).values_list('id', flat=True)
                column_permissions = []
                row_permissions = []
                for column_id in columns_ids:
                    columnpermission = ColumnPermission(table_id=pk, column_id=column_id)
                    column_permissions.append(columnpermission)
                else:
                    ColumnPermission.objects.bulk_create(column_permissions, ignore_conflicts=True)

                for row_id in row_ids:
                    rowpermission = RowPermission(row_id=row_id, user_id=filial_id)
                    row_permissions.append(rowpermission)
                else:
                    RowPermission.objects.bulk_create(row_permissions, ignore_conflicts=True)
                return Response({"success": True})
            return Response({"success": False})

    @action(detail=True, methods=['post'], url_path='set_cell_color')
    def set_cell_color(self, request, pk=None):
        color = request.data.get('color')
        cells_to_update = request.data.get('cells')
        if not color:
            raise ValidationError({'color': 'Это поле обязательно'})
        if not cells_to_update:
            raise ValidationError({'cells': 'Это поле обязательно'})
        cells = Cell.objects.filter(table_id=pk, id__in=cells_to_update)
        if not cells.exists():
            raise ValidationError({'Переданные ячейки cells не найдены'})
        cells.update(color=color)
        return Response({"success": True, 'updated_cells': cells.count()}, status=200)

    def get_queryset(self):
        queryset = super().get_queryset()
        table_id = self.kwargs.get('pk')
        queryset = queryset.filter(id=table_id)
        user = self.request.user
        all_permissions = get_table_ids_permissions(user)
        if all_permissions:
            queryset = queryset.filter(id__in=all_permissions)
        else:
            queryset = queryset.none()
        return queryset

    def perform_update(self, serializer):
        instance = serializer.save()
        send_table_update(instance)
        return instance


class CellViewSet(viewsets.ModelViewSet):
    queryset = Cell.objects.all()
    serializer_class = CellSerializer
    pagination_class = CellPagination
    ordering_fields = ('row',)

    def perform_create(self, serializer):
        table_id = serializer.validated_data['table'].id
        order = serializer.validated_data['order']
        if order > 0:
            column_max_order = Column.objects.filter(table_id=table_id).aggregate(max_order=Max('order'))['max_order'] + 1
            serializer.save(order=column_max_order)

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.value is None or instance.value == "":
            instance.formula_value = ""
            instance.save()
        cells_to_update = []
        if instance.value is not None:
            v = str(instance.value)
            if len(v) > 0:
                if v[0] == '=':
                    calculate_formula(instance)
        send_cells_update([instance])
        for cell in Cell.objects.filter(table_id=instance.table_id, row=instance.row):
            if cell.value is not None:
                if len(cell.value) > 0 and cell.value[0] == "=":
                    calculate_formula(cell)
                    cells_to_update.append(cell)

        #Набрасывание доп прав по значению
        value_permissions = RowValuePermission.objects.filter(table_id=instance.table_id, column_id=instance.column, cell_value=instance.value)
        if value_permissions.exists():
            users_permissions = []
            user_ids = list(chain.from_iterable(value_permissions.values_list('user_ids', flat=True)))
            for user_id in user_ids:
                users_permissions.append(RowPermission(user=user_id, row=instance.row, table=instance.table_id))
            if len(users_permissions) > 0:
                RowPermission.objects.bulk_create(users_permissions, ignore_conflicts=True)




        send_cells_update(cells_to_update)
        return instance

    def get_queryset(self):
        queryset = super().get_queryset()
        table_id = self.request.query_params.get('table')
        if table_id:
            queryset = queryset.filter(table_id=table_id).order_by('row')
        else:
            queryset.none()

        search_value = self.request.query_params.get('search', '')
        if search_value:
            queryset = queryset.filter(Q(value__icontains=search_value))

        return queryset

    @action(detail=True, methods=['get'], url_path='comments')
    def get_comments(self, request, pk=None):
        cell = self.get_object()
        comments = CellComment.objects.filter(cell_id=cell.id)

        user_ids = comments.values_list('user_id', flat=True).distinct()
        users = User.objects.filter(id__in=user_ids)
        user_dict = {user.id: user for user in users}

        serializer = CellCommentSerializer(
            comments,
            many=True,
            context={'request': request, 'user_dict': user_dict}
        )
        return Response({
            'cell_id': cell.id,
            'cell': CellSerializer(cell, context={'request': request}).data,
            'comments_count': comments.count(),
            'comments': serializer.data
        })


class ColumnViewSet(viewsets.ModelViewSet):
    queryset = Column.objects.all()
    serializer_class = ColumnSerializer
    filter_backends = (OrderingFilter,)
    ordering_fields = ('id', 'name', 'order', 'data_type',)
    ordering = ('order',)


    @action(detail=True, methods=['get'], url_path='select')
    def getSelect(self, request, pk=None):
        column = Column.objects.get(pk=pk)
        if column and column.data_type == 'select':
            select_types = SelectType.objects.filter(column_id=column.id).values_list('value', flat=True)
            return Response({"success": True, "select_values": select_types})
        return Response({"success": False})

    @action(detail=True, methods=['get'], url_path='clear_duplicates')
    def clear_duplicates(self, request, pk=None):
        column = Column.objects.get(pk=pk)
        if column and column.data_type == 'select':
            column_select_types = SelectType.objects.filter(column_id=column.id)
            duplicates = column_select_types.values('name').annotate(
                count=Count('id')
            ).filter(count__gt=1)

            deleted_count = 0
            for item in duplicates:
                keep_id = SelectType.objects.filter(
                    column_id=column.id,
                    name=item['name']
                ).aggregate(min_id=Min('id'))['min_id']

                # Удалить остальные дубликаты
                deleted, _ = SelectType.objects.filter(
                    column_id=column.id,
                    name=item['name']
                ).exclude(
                    id=keep_id
                ).delete()

                deleted_count += deleted

            return Response(status=status.HTTP_200_OK)


        return Response(status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        table_id = serializer.validated_data['table'].id
        column_max_order = Column.objects.filter(table_id=table_id).aggregate(max_order=Max('order'))['max_order']
        if column_max_order is None:
            serializer.save(order=1)
        else:
            serializer.save(order=column_max_order + 1)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        table_id = self.request.query_params.get('table')
        if table_id:
            table = Table.objects.get(id=table_id)
            if table.owner.id == user.id:
                queryset = queryset.filter(table_id=table_id)
            else:
                queryset = queryset.filter(table_id=table_id, hidden=False)

        return queryset

    def destroy(self, request, *args, **kwargs):
        try:
            column_id = self.kwargs.get('pk')
            table_id = Column.objects.get(pk=column_id).table.id
            Cell.objects.filter(column=column_id).delete()
            instance = self.get_object()
            instance.delete()
            #Для автоинкремента
            auto_column = Column.objects.filter(table_id=table_id, data_type='auto').first()
            table_columns = Column.objects.filter(table_id=table_id).values_list('id', flat=True)
            if auto_column:
                columns_ids = set(auto_column.related_column_ids)  &  set(table_columns)
                auto_column.related_column_ids = list(columns_ids)
                auto_column.save()
                update_auto_column(table_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)


class RowDetailViewSet(viewsets.ModelViewSet):
    serializer_class = RowSerializer
    queryset = Row.objects.all()

    def perform_create(self, serializer):
        instance = serializer.save()
        send_row(instance)
        #recalculate_formulas(instance.table_id)
        return instance

    def destroy(self, request, *args, **kwargs):
        row_id = self.kwargs.get('pk')
        table_id = Row.objects.get(pk=row_id).table.id
        table = Table.objects.get(id=table_id)
        if not Row.objects.filter(pk=row_id).exists():
            return Response({'error': 'Row not found'}, status=404)
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
            Cell.objects.filter(row=row_id).delete()
            RowFilialPermission.objects.filter(row=row_id).delete()
            RowPermission.objects.filter(row=row_id).delete()
            #Для автоинкеремента
            normalize_row_orders(table)
            update_auto_column(table_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)


class RowListViewSet(viewsets.ModelViewSet):
    serializer_class = RowSerializer
    queryset = Row.objects.all()
    pagination_class = RowPagination

    filter_backends = [ColumnFilterBackend]

    def _filter_numeric_cells(self, column_id, search_value, row_ids, column_type):
        matching_rows = []
        cells = Cell.objects.filter(
            column=column_id,
            row__in=row_ids
        ).only('row', 'value')

        for cell in cells:
            try:
                if column_type == 'integer':
                    cell_val = int(float(cell.value))
                else:
                    cell_val = float(cell.value)

                if '-' in search_value:
                    min_val, max_val = map(float, search_value.split('-'))
                    if min_val <= cell_val <= max_val:
                        matching_rows.append(cell.row)
                else:
                    search_val = float(search_value)
                    if column_type == 'integer':
                        search_val = int(search_val)

                    if cell_val == search_val:
                        matching_rows.append(cell.row)

            except (ValueError, TypeError, AttributeError):
                if search_value in str(cell.value):
                    matching_rows.append(cell.row)
                continue

        return matching_rows

    def _filter_date_cells(self, column_id, search_value, row_ids):
        return list(Cell.objects.filter(
            column=column_id,
            value__icontains=search_value,
            row__in=row_ids
        ).values_list('row', flat=True))

    def _filter_text_cells(self, column_id, search_value, row_ids, operator):
        if operator == 'contains':
            return list(Cell.objects.filter(
                column=column_id,
                value__icontains=search_value,
                row__in=row_ids
            ).values_list('row', flat=True))
        else:
            return list(Cell.objects.filter(
                column=column_id,
                value=search_value,
                row__in=row_ids
            ).values_list('row', flat=True))

    def _apply_filter_by_column_type(self, column_id, search_value, row_ids, column_type, operator='contains'):
        if column_type in ['integer', 'float']:
            return self._filter_numeric_cells(column_id, search_value, row_ids, column_type)
        elif column_type in ['date', 'datetime']:
            return self._filter_date_cells(column_id, search_value, row_ids)
        else:
            return self._filter_text_cells(column_id, search_value, row_ids, operator)

    def _apply_row_permissions(self, queryset, user, filial_id, table):
        if not table.show_locked_row:
            exist_rows_ids_list = set(queryset.values_list('id', flat=True))
            if exist_rows_ids_list:
                row_permissions = list(RowPermission.objects.filter(user=user.id, row__in=exist_rows_ids_list).values_list('row', flat=True))
                row_filial_permissions = list(RowFilialPermission.objects.filter(filial=filial_id, row__in=exist_rows_ids_list).values_list('row', flat=True))
                union_permissions = set(row_permissions + row_filial_permissions)
                queryset = queryset.filter(id__in=union_permissions)
        return queryset

    def sort_by_param_optimized(self, queryset, sort_field, sort_direction):
        from django.db.models import Case, When, Value, CharField, FloatField, Q
        if isinstance(sort_field, int):
            column_ids = [sort_field]
        elif isinstance(sort_field, list):
            column_ids = sort_field
        else:
            return queryset
        columns = {col.id: col for col in Column.objects.filter(id__in=column_ids)}
        if not columns:
            return queryset

        # Исходный порядок idшников
        row_ids = list(queryset.values_list('id', flat=True))
        preserved_order = Case(
            *[When(id=row_id, then=Value(pos)) for pos, row_id in enumerate(row_ids)],
            output_field=CharField()
        )
        #Сортировка
        order_by = []
        # Предварительная сортировка по всем колонкам
        for field_id in column_ids:
            column = columns[field_id]

            # Получаем значения для текущей колонки
            sort_values = Cell.objects.filter(
                column=field_id,
                row__in=row_ids
            ).values('row', 'value')

            value_map = {item['row']: item['value'] for item in sort_values}

            # Создаем аннотацию для текущей колонки
            if column.data_type in ['integer', 'float']:
                when_clauses = []
                for row_id in row_ids:
                    value = value_map.get(row_id)
                    try:
                        num_value = float(value) if value and value != '' else None
                    except (ValueError, TypeError):
                        num_value = None
                    when_clauses.append(When(id=row_id, then=Value(num_value)))

                sort_annotation = Case(
                    *when_clauses,
                    default=Value(None),
                    output_field=FloatField()
                )
            else:
                when_clauses = [
                    When(id=row_id, then=Value(value_map.get(row_id, '')))
                    for row_id in row_ids
                ]
                sort_annotation = Case(
                    *when_clauses,
                    default=Value(''),
                    output_field=CharField()
                )

            # Добавляем аннотацию и условие сортировки
            field_name = f'sort_{field_id}'
            queryset = queryset.annotate(**{field_name: sort_annotation})

            if sort_direction == 'desc':
                order_by.append(F(field_name).desc(nulls_last=True))
            else:
                order_by.append(F(field_name).asc(nulls_first=True))

        # Добавляем preserved_order для стабильности
        queryset = queryset.annotate(preserved_order=preserved_order)
        order_by.append('preserved_order')

        return queryset.order_by(*order_by)

    def get_queryset(self):
        table_id = self.request.query_params.get('table')
        table = Table.objects.get(id=table_id)
        queryset = super().get_queryset()
        if table.open_last_page_by_default:
            queryset = queryset.reverse()
        user = self.request.user
        filial_code = Profile.objects.get(user=user).employee.id_filial
        filial_id = Filial.objects.get(code=filial_code).id


        if table_id:
            queryset = queryset.filter(table=table_id).order_by('order')
        else:
            return queryset.none()

        table = Table.objects.get(id=table_id)
        sort_field = None
        if self.request.query_params.get('sort_field', None) is not None:
            sort_field = json.loads(self.request.query_params.get('sort_field', None))
        sort_direction = self.request.query_params.get('sort_direction', None)

        search_value = self.request.query_params.get('search', None)
        if search_value is not None:
            columns_with_types = Column.objects.filter(table_id=table_id).values('id', 'data_type')
            matching_row_ids = set()

            for column in columns_with_types:
                column_id = column['id']
                column_type = column['data_type']

                if column_type in ['integer', 'float']:
                    cells = Cell.objects.filter(
                        column=column_id,
                        row__in=queryset.values_list('id', flat=True)
                    )
                    for cell in cells:
                        try:
                            if search_value in str(cell.value):
                                matching_row_ids.add(cell.row)
                        except:
                            pass
                else:
                    cell_rows = Cell.objects.filter(
                        column=column_id,
                        value__icontains=search_value
                    ).values_list('row', flat=True)
                    matching_row_ids.update(cell_rows)

            result_queryset = queryset.filter(id__in=matching_row_ids)
            return self._apply_row_permissions(result_queryset, user, filial_id, table)

        queryset = self.filter_queryset(queryset)

        if sort_field is not None and sort_field != 'order':
            queryset = self.sort_by_param_optimized(queryset, sort_field, sort_direction)
        elif sort_field == 'order':
            if sort_direction == 'desc':
                queryset = queryset.order_by('-order')
            else:
                queryset = queryset.order_by('order')

        return self._apply_row_permissions(queryset, user, filial_id, table)


class TablePermissionViewSet(viewsets.ModelViewSet):
    serializer_class = TablePermissionsSerializer
    queryset = TablePermission.objects.all()


    def perform_destroy(self, instance):
        user_id = instance.user_id
        table_id = instance.table.id
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                        DELETE FROM tables_rowpermission WHERE "user" = %s AND "table" = %s
                    """, [user_id, table_id]
                )
                cursor.execute(
                    """
                        DELETE FROM tables_columnpermission WHERE "user" = %s AND "table" = %s
                    """, [user_id, table_id]
                )
            instance.delete()


    def get_queryset(self):
        queryset = super().get_queryset()
        table_id = self.request.query_params.get('table_id')
        user_id = self.request.query_params.get('user_id')
        if table_id:
            queryset = queryset.filter(table_id=table_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset


class TableFilialPermissionViewSet(viewsets.ModelViewSet):
    serializer_class = TableFilialPermissionsSerializer
    queryset = TableFilialPermission.objects.all()

    def perform_destroy(self, instance):
        filial_id = instance.filial.id
        table_id = instance.table.id
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                        DELETE FROM tables_columnfilialpermission WHERE "filial_id" = %s AND "table" = %s
                        
                    """,[filial_id, table_id]
                )
                cursor.execute(
                """
                        DELETE FROM tables_rowfilialpermission
                        WHERE "filial" = %s
                        AND "row" IN (
                        SELECT id FROM tables_row WHERE table_id = %s
                              )
                    """,[filial_id, table_id]
                )
            instance.delete()

    def get_queryset(self):
        queryset = super().get_queryset()
        filial_id = self.request.query_params.get('filial_id')
        table_id = self.request.query_params.get('table_id')
        if filial_id:
            queryset = queryset.filter(filial__id=filial_id)
        if table_id:
            queryset = queryset.filter(table__id=table_id)
        return queryset


class RowPermissionViewSet(viewsets.ModelViewSet):
    serializer_class = RowPermissionSerializer
    queryset = RowPermission.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.query_params.get('user_id')
        row_id = self.request.query_params.get('row_id')
        table_id = self.request.query_params.get('table_id')
        rows_ids = self.request.query_params.get('rows_ids')

        if row_id:
            queryset = queryset.filter(row=row_id)
        if rows_ids:
            filial_code = Profile.objects.prefetch_related("employee").get(user_id=user_id).employee.id_filial
            filial_id = Filial.objects.get(code=filial_code).id
            queryset = queryset.filter(table=table_id,user=user_id)

            filtered_permission = []
            rows_ids = json.loads(rows_ids) # На что пришел запрос с клиента
            # При добавлении строки СТАВИТЬ True в can_edit

            filial_rows_ids = list(RowFilialPermission.objects.filter(row__in=rows_ids, filial=filial_id).values_list('row', flat=True))
            row_approve_ids = list(queryset.filter( row__in=rows_ids).values_list('row', flat=True))
            updated_approve_ids = set(filial_rows_ids + row_approve_ids)

            for index in updated_approve_ids:
                permission = RowPermission(row=index,user=user_id,table=table_id)
                filtered_permission.append(permission)

            return  filtered_permission

        return queryset


class ColumnPermissionViewSet(viewsets.ModelViewSet):
    serializer_class = ColumnPermissionSerializer
    queryset = ColumnPermission.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.query_params.get('user_id')
        column_id = self.request.query_params.get('column_id')
        table_id = self.request.query_params.get('table_id')
        columns_ids = self.request.query_params.get('columns_ids')
        if table_id:
            queryset = queryset.filter(table=table_id)
        if user_id:
            queryset = queryset.filter(user=user_id)
        if column_id:
            queryset = queryset.filter(column=column_id)
        if columns_ids:
            columns_ids = json.loads(columns_ids) # На что пришел запрос с клиента
            columns_ids = list(filter(lambda item: not math.isnan(item), columns_ids))
            #queryset = queryset.filter(column__in=columns_ids)
            user_column_permissions = get_columns_ids_permissions(user_id)
            queryset = queryset.filter(column__in=user_column_permissions)
            return queryset

        return queryset



class ColumnFilialPermissionViewSet(viewsets.ModelViewSet):
    serializer_class = ColumnFilialPermissionSerializer
    queryset = ColumnFilialPermission.objects.all()

    def get_queryset(self):
        column_id = self.request.query_params.get('column_id')
        if not column_id:
            return super().get_queryset()
        column = get_object_or_404(Column, pk=column_id)
        return ColumnFilialPermission.objects.filter(column=column)


class RowFilialPermissionViewSet(viewsets.ModelViewSet):
    serializer_class = RowFilialPermissionSerializer
    queryset = RowFilialPermission.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        filial_id = self.request.query_params.get('filial_id')
        row_id = self.request.query_params.get('row_id')
        if filial_id:
            queryset = queryset.filter(filial=filial_id)
        if row_id:
            queryset = queryset.filter(row=row_id)

        return queryset


class RowUploadViewSet(viewsets.ViewSet):
    parser_classes = (MultiPartParser, FormParser)
    renderer_classes = [JSONRenderer, FileUploadBrowsableRenderer]

    @action(detail=False, methods=['post'])
    def upload(self, request):
        table_id = request.data.get('table_id')
        if table_id:
            if 'file' not in request.FILES:
                return Response(
                    {"error": "No file provided"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user = self.request.user
            file = request.FILES['file']
            filename = file.name
            extensions = os.path.splitext(filename)[1].lower()
            if extensions != '.xlsx':
                return Response(
                    {"error": "Файл должен быть в формате XLSX"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            file_data = BytesIO(file.read())
            import_to_existing_table(file_data, table_id, user)
            return Response({
                "filename": file.name,
                "size": file.size,
            })

    # @action(detail=False, methods=['post'])
    # def import_table(self, request):
    #     table_name = request.data.get('table_name')
    #     if table_name:
    #         if 'file' not in request.FILES:
    #             return Response(
    #                 {"error": "No file provided"},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #         user = self.request.user
    #         file = request.FILES['file']
    #         filename = file.name
    #         extensions = os.path.splitext(filename)[1].lower()
    #         if extensions != '.xlsx':
    #             return Response(
    #                 {"error": "Файл должен быть в формате XLSX"},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #         file_data = BytesIO(file.read())
    #
    #
    #         import_table(file_data, table_name, user)
    #
    #         return Response({
    #             "filename": file.name,
    #             "size": file.size,
    #         })

    @action(detail=False, methods=['post'])
    def import_table(self, request):
        table_name = request.data.get('table_name')
        if not table_name:
            return Response({"error": "table_name required"}, status=400)
        if 'file' not in request.FILES:
            return Response({"error": "No file provided"}, status=400)
        file = request.FILES['file']
        if not file.name.endswith('.xlsx'):
            return Response({"error": "Файл должен быть в формате XLSX"}, status=400)
        temp_dir = '/tmp/imports'
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{file.name}")
        with open(file_path, 'wb+') as f:
            for chunk in file.chunks():
                f.write(chunk)
        job_id = f"import_{uuid.uuid4().hex[:8]}"
        try:
            schedule_task_in_db(
                func=fast_import_table,
                args=[file_path, table_name, request.user.id],
                job_id=job_id,
                run_date=datetime.now() + timedelta(seconds=10),  # запас для пробуждения
                misfire_grace_time=86400,
            )
        except Exception as e:
            logger.error(f"Ошибка постановки задачи {job_id}: {e}", exc_info=True)
            if os.path.exists(file_path):
                os.remove(file_path)
            return Response({"error": f"Не удалось запланировать импорт: {e}"}, status=500)

        return Response({
            "message": "Импорт запущен в фоновом режиме",
            "job_id": job_id,
        })


class SelectTypeViewSet(viewsets.ModelViewSet):
    queryset = SelectType.objects.all()
    serializer_class = SelectTypeSerializer

    @action(detail=True, methods=['get'], url_path='column')
    def column(self, request, pk=None):
        response = []
        for selecttype in SelectType.objects.filter(column_id=pk):
            response.append(SelectTypeSerializer(selecttype).data)
        return Response(response)


class CellEditLogViewSet(viewsets.ModelViewSet):
    queryset = CellEditLog.objects.all()
    serializer_class = CellEditLogSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        row_id = self.request.query_params.get('row_id')
        if row_id:
            queryset = queryset.filter(row_id=row_id)

        return queryset


class CellCommentViewSet(viewsets.ModelViewSet):
    queryset = CellComment.objects.all()
    serializer_class = CellCommentSerializer


class CellFileViewSet(viewsets.ModelViewSet):
    """ViewSet для работы с файлами ячеек"""

    queryset = CellFile.objects.all()
    serializer_class = CellFileSerializer

    def get_serializer_class(self):
        """Выбор сериализатора в зависимости от действия"""
        if self.action == 'list':
            return CellFileListSerializer
        return CellFileSerializer

    def get_queryset(self):
        """Фильтрация по параметрам запроса"""
        queryset = super().get_queryset()

        # Фильтр по ячейке
        cell_id = self.request.query_params.get('cell_id')
        if cell_id:
            queryset = queryset.filter(cell_id=cell_id)

        # Фильтр по строке и колонке
        row = self.request.query_params.get('row')
        column = self.request.query_params.get('column')
        if row and column:
            queryset = queryset.filter(cell__row=row, cell__column=column)

        # Фильтр по типу файла
        extension = self.request.query_params.get('extension')
        if extension:
            queryset = queryset.filter(file_extension=extension)

        return queryset

    def perform_create(self, serializer):
        """Установка uploaded_by при создании"""
        serializer.save(
            uploaded_by=self.request.user.username if self.request.user.is_authenticated else 'anonymous'
        )

    def perform_update(self, serializer):
        """Установка uploaded_by при обновлении"""
        serializer.save(
            updated_by=self.request.user.username if self.request.user.is_authenticated else 'anonymous'
        )

    @action(detail=True, methods=['get'], url_path='download')
    def download_file(self, request, pk=None):
        """Скачивание файла"""
        cell_file = self.get_object()

        # Создаем response с файлом
        response = HttpResponse(
            cell_file.file,
            content_type=cell_file.content_type
        )
        response['Content-Disposition'] = f'attachment; filename="{cell_file.filename}"'
        response['Content-Length'] = cell_file.file_size

        return response

    @action(detail=True, methods=['get'], url_path='preview')
    def preview_file(self, request, pk=None):
        """Предпросмотр файла (для изображений и текста)"""
        cell_file = self.get_object()

        # Для изображений и текста можно вернуть прямо в браузер
        if cell_file.content_type.startswith('image/'):
            return HttpResponse(cell_file.file, content_type=cell_file.content_type)
        elif cell_file.content_type.startswith('text/'):
            content = cell_file.file.decode('utf-8', errors='ignore')
            return Response({'content': content, 'filename': cell_file.filename})
        else:
            return Response(
                {'message': 'Предпросмотр недоступен для этого типа файла'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'], url_path='history')
    def file_history(self, request, pk=None):
        """История замен файла"""
        cell_file = self.get_object()
        history = cell_file.history.all()

        history_data = [{
            'version': h.version,
            'filename': h.filename,
            'replaced_at': h.replaced_at,
            'replaced_by': h.replaced_by
        } for h in history]

        return Response({
            'current_version': cell_file.version,
            'current_filename': cell_file.filename,
            'history': history_data
        })

    @action(detail=True, methods=['post'], url_path='replace')
    def replace_file(self, request, pk=None):
        """Специальный эндпоинт для замены файла"""
        cell_file = self.get_object()

        # Используем сериализатор для обновления
        serializer = self.get_serializer(cell_file, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-cell')
    def get_by_cell(self, request):
        """Получение файла по координатам ячейки"""
        cell_id = request.query_params.get('cell_id')

        if not cell_id:
            return Response(
                {'error': 'Необходимо id ячейки'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            cell = Cell.objects.get(id=cell_id)
            cell_file = CellFile.objects.get(cell=cell)
            serializer = self.get_serializer(cell_file)
            return Response(serializer.data)
        except Cell.DoesNotExist:
            return Response(
                {'error': 'Ячейка не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        except CellFile.DoesNotExist:
            return Response(
                {'error': 'Файл не найден для этой ячейки'},
                status=status.HTTP_404_NOT_FOUND
            )


class RowValuePermissionViewSet(viewsets.ModelViewSet):
    serializer_class = RowValuePermissionSerializer
    queryset = RowValuePermission.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        'table_id': ['exact'],
        'column_id': ['exact'],
        'cell_value': ['exact', 'icontains'],
    }
