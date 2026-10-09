from rest_framework.filters import BaseFilterBackend
from django.db.models import Q
from tables.models import Cell, Column


class ColumnFilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if not request.query_params.get('is_column_search'):
            return queryset

        table_id = request.query_params.get('table')
        if not table_id:
            return queryset

        mode = request.query_params.get('column_search_mode', 'and')
        filters = self._collect_filters(request)

        if not filters:
            return queryset

        if mode == 'or':
            return self._apply_or_filters(queryset, filters, table_id)
        else:
            return self._apply_and_filters(queryset, filters, table_id)

    def _collect_filters(self, request):
        filters = []

        columns = request.query_params.getlist('column')
        datas = request.query_params.getlist('data')
        operators = request.query_params.getlist('operator')

        if columns:
            for i, column_id in enumerate(columns):
                if not column_id:
                    continue
                filters.append({
                    'column_id': column_id,
                    'value': datas[i] if i < len(datas) else None,
                    'operator': operators[i] if i < len(operators) else 'contains'
                })

        for key, value in request.query_params.items():
            if key.endswith('_operator'):
                continue
            if key in ['table', 'page', 'limit', 'is_column_search', 'column_search_mode',
                       'sort_field', 'sort_direction', 'column', 'data', 'operator']:
                continue

            operator_key = f'{key}_operator'
            operator = request.query_params.get(operator_key, 'contains')

            filters.append({
                'column_id': key,
                'value': value,
                'operator': operator
            })

        #пустые значения убираю
        return [f for f in filters if f['value'] and f['value'].strip()]

    def _apply_or_filters(self, queryset, filters, table_id):
        conditions = Q()
        row_ids = list(queryset.values_list('id', flat=True))

        for filter_data in filters:
            column_id = filter_data['column_id']
            search_value = filter_data['value']
            operator = filter_data['operator']

            #тип колонки
            try:
                column = Column.objects.get(id=column_id, table_id=table_id)
                column_type = column.data_type
            except Column.DoesNotExist:
                continue

            #фильтр
            if column_type in ['integer', 'float']:
                matching = self._filter_numeric_cells(column_id, search_value, row_ids, column_type)
                if matching:
                    conditions |= Q(id__in=matching)
            elif column_type in ['date', 'datetime']:
                cell_rows = Cell.objects.filter(
                    column=column_id,
                    row__in=row_ids,
                    value__icontains=search_value
                ).values_list('row', flat=True)
                if cell_rows:
                    conditions |= Q(id__in=cell_rows)
            else:
                lookup = 'icontains' if operator == 'contains' else 'exact'
                cell_rows = Cell.objects.filter(
                    column=column_id,
                    row__in=row_ids,
                    **{f'value__{lookup}': search_value}
                ).values_list('row', flat=True)
                if cell_rows:
                    conditions |= Q(id__in=cell_rows)

        return queryset.filter(conditions).distinct() if conditions else queryset

    def _apply_and_filters(self, queryset, filters, table_id):
        """AND режим - все условия должны совпасть"""
        row_ids = list(queryset.values_list('id', flat=True))
        valid_row_ids = set(row_ids)

        for filter_data in filters:
            if not valid_row_ids:
                break

            column_id = filter_data['column_id']
            search_value = filter_data['value']
            operator = filter_data['operator']

            # тип колонки получение
            try:
                column = Column.objects.get(id=column_id, table_id=table_id)
                column_type = column.data_type
            except Column.DoesNotExist:
                continue

            #фильтр
            if column_type in ['integer', 'float']:
                matching = self._filter_numeric_cells(column_id, search_value, list(valid_row_ids), column_type)
            elif column_type in ['date', 'datetime']:
                matching = list(Cell.objects.filter(
                    column=column_id,
                    row__in=valid_row_ids,
                    value__icontains=search_value
                ).values_list('row', flat=True))
            else:
                lookup = 'icontains' if operator == 'contains' else 'exact'
                matching = list(Cell.objects.filter(
                    column=column_id,
                    row__in=valid_row_ids,
                    **{f'value__{lookup}': search_value}
                ).values_list('row', flat=True))

            valid_row_ids = valid_row_ids.intersection(set(matching))

        if valid_row_ids:
            return queryset.filter(id__in=valid_row_ids)
        return queryset.none()

    def _filter_numeric_cells(self, column_id, search_value, row_ids, column_type):
        matching = []
        for cell in Cell.objects.filter(column=column_id, row__in=row_ids).only('row', 'value'):
            try:
                cell_val = int(float(cell.value)) if column_type == 'integer' else float(cell.value)

                if '-' in search_value:
                    min_v, max_v = map(float, search_value.split('-'))
                    if min_v <= cell_val <= max_v:
                        matching.append(cell.row_id)
                else:
                    search_val = int(search_value) if column_type == 'integer' else float(search_value)
                    if cell_val == search_val:
                        matching.append(cell.row_id)
            except (ValueError, TypeError, AttributeError):
                if search_value in str(cell.value):
                    matching.append(cell.row_id)
        return matching