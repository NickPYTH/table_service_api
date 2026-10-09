from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Q
from tables.models import (Table, Column, Cell, Row, TablePermission, TableFilialPermission,
                           RowFilialPermission, Filial, Department, Employee, Profile,
                           Admin, RowLock, CellLock, TableFilialLock, RowPermission,
                           SelectType, ColumnPermission, ColumnFilialPermission, CellEditLog, TableUserOnline)


class DateRangeFilter(admin.DateFieldListFilter):
    """Кастомный фильтр по диапазону дат"""
    pass


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'created_at', 'with_cell_confirm', 'with_cell_logging')
    list_filter = ('with_cell_confirm', 'with_cell_logging', 'created_at')
    search_fields = ('title', 'owner__username', 'share_token')
    readonly_fields = ('share_token', 'created_at')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('owner')


@admin.register(Column)
class ColumnAdmin(admin.ModelAdmin):
    list_display = ('name', 'table', 'data_type', 'order')
    list_filter = ('data_type', 'table')
    search_fields = ('name', 'table__title')
    list_editable = ('order',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('table')


@admin.register(Cell)
class CellAdmin(admin.ModelAdmin):
    list_display = ('id', 'table_id', 'row', 'column', 'value_preview')
    list_filter = ('table_id', 'column')
    search_fields = ('value', 'formula_value')

    def value_preview(self, obj):
        return obj.value[:50] + '...' if obj.value and len(obj.value) > 50 else obj.value

    value_preview.short_description = 'Значение (превью)'


@admin.register(Row)
class RowAdmin(admin.ModelAdmin):
    list_display = ('id', 'table', 'order', 'created_by')
    list_filter = ('table',)
    search_fields = ('table__title', 'created_by__username')
    list_editable = ('order',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('table', 'created_by')


@admin.register(Filial)
class FilialAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'boss', 'set_date', 'end_date')
    list_filter = ('set_date', 'end_date')
    search_fields = ('name', 'long_name', 'short_name', 'boss')
    date_hierarchy = 'set_date'


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'id_filial', 'set_date', 'end_date')
    list_filter = ('id_filial', 'set_date', 'end_date')
    search_fields = ('name', 'long_name', 'short_name')
    date_hierarchy = 'set_date'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('tabnumber', 'secondname', 'firstname', 'lastname', 'post_name', 'id_filial', 'set_date')
    list_filter = ('id_filial', 'id_department', 'set_date', 'end_date')
    search_fields = ('secondname', 'firstname', 'lastname', 'post_name', 'tabnumber')
    readonly_fields = ('tabnumber',)
    date_hierarchy = 'set_date'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'employee_info')
    list_filter = ('employee__id_filial',)
    search_fields = ('user__username', 'employee__secondname', 'employee__firstname', 'employee__lastname')

    def employee_info(self, obj):
        if obj.employee:
            return f"{obj.employee.secondname} {obj.employee.firstname}"
        return "Не назначен"

    employee_info.short_description = 'Сотрудник'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'employee')


@admin.register(Admin)
class AdminAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username',)
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(TablePermission)
class TablePermissionAdmin(admin.ModelAdmin):
    list_display = ('table', 'user', 'can_view', 'can_edit')
    list_filter = ('can_view', 'can_edit', 'table')
    search_fields = ('table__title', 'user__username')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('table', 'user')


@admin.register(TableFilialPermission)
class TableFilialPermissionAdmin(admin.ModelAdmin):
    list_display = ('table', 'filial', 'can_view')
    list_filter = ('can_view', 'table', 'filial')
    search_fields = ('table__title', 'filial__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('table', 'filial')


@admin.register(RowFilialPermission)
class RowFilialPermissionAdmin(admin.ModelAdmin):
    list_display = ('row', 'filial', 'can_edit', 'can_delete')
    list_filter = ('can_edit', 'can_delete', 'filial')
    search_fields = ('row', 'filial')


@admin.register(RowPermission)
class RowPermissionAdmin(admin.ModelAdmin):
    list_display = ('table', 'row', 'user', 'can_edit', 'can_delete')
    list_filter = ('can_edit', 'can_delete', 'table')
    search_fields = ('row', 'user', 'table')


@admin.register(RowLock)
class RowLockAdmin(admin.ModelAdmin):
    list_display = ('row', 'user', 'locked_at')
    list_filter = ('locked_at',)
    search_fields = ('row__id', 'user__username')
    readonly_fields = ('locked_at',)
    date_hierarchy = 'locked_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('row', 'user')


@admin.register(CellLock)
class CellLockAdmin(admin.ModelAdmin):
    list_display = ('cell', 'user', 'locked_at')
    list_filter = ('locked_at',)
    search_fields = ('cell__id', 'user__username')
    readonly_fields = ('locked_at',)
    date_hierarchy = 'locked_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('cell', 'user')


@admin.register(TableFilialLock)
class TableFilialLockAdmin(admin.ModelAdmin):
    list_display = ('table', 'filial', 'locked_by', 'locked_at')
    list_filter = ('locked_at', 'table', 'filial')
    search_fields = ('table__title', 'filial__name', 'locked_by__username')
    readonly_fields = ('locked_at',)
    date_hierarchy = 'locked_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('table', 'filial', 'locked_by')


# Дополнительные модели, которые не были в вашем исходном файле

@admin.register(SelectType)
class SelectTypeAdmin(admin.ModelAdmin):
    list_display = ('column_id', 'name')
    list_filter = ('column_id',)
    search_fields = ('name', 'column_id')


@admin.register(ColumnPermission)
class ColumnPermissionAdmin(admin.ModelAdmin):
    list_display = ('column', 'user', 'table', 'can_view', 'can_edit')
    list_filter = ('can_view', 'can_edit', 'table')
    search_fields = ('column', 'user', 'table')


@admin.register(ColumnFilialPermission)
class ColumnFilialPermissionAdmin(admin.ModelAdmin):
    list_display = ('column', 'filial', 'can_edit', 'can_delete')
    list_filter = ('can_edit', 'can_delete', 'filial')
    search_fields = ('column__name', 'filial__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('column', 'filial')


@admin.register(CellEditLog)
class CellEditLogAdmin(admin.ModelAdmin):
    list_display = ('cell_id', 'user_id', 'old_value_preview', 'new_value_preview', 'row_id')
    list_filter = ('user_id',)
    search_fields = ('old_value', 'new_value', 'cell_id', 'row_id')

    def old_value_preview(self, obj):
        return obj.old_value[:30] + '...' if obj.old_value and len(obj.old_value) > 30 else obj.old_value

    old_value_preview.short_description = 'Старое значение'

    def new_value_preview(self, obj):
        return obj.new_value[:30] + '...' if obj.new_value and len(obj.new_value) > 30 else obj.new_value

    new_value_preview.short_description = 'Новое значение'


@admin.register(TableUserOnline)
class TableUserOnlineAdmin(admin.ModelAdmin):
    list_display = ('user', 'table')
    list_filter = ('table',)
    search_fields = ('user__username', 'table__title')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'table')


# Оптимизация отображения связанных полей в сырых id полях
class HasFilialFilter(admin.SimpleListFilter):
    """Фильтр для проверки наличия филиала"""
    title = 'Наличие филиала'
    parameter_name = 'has_filial'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Есть филиал'),
            ('no', 'Нет филиала'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(id_filial__isnull=False)
        if self.value() == 'no':
            return queryset.filter(id_filial__isnull=True)
        return queryset


# Добавляем фильтры к моделям с id полями
class EmployeeAdminWithFilters(EmployeeAdmin):
    list_filter = (HasFilialFilter, 'id_department', 'set_date', 'end_date')


class DepartmentAdminWithFilters(DepartmentAdmin):
    list_filter = (HasFilialFilter, 'set_date', 'end_date')


# Перерегистрируем с улучшенными фильтрами
admin.site.unregister(Employee)
admin.site.unregister(Department)


@admin.register(Employee)
class EmployeeAdminImproved(EmployeeAdminWithFilters):
    pass


@admin.register(Department)
class DepartmentAdminImproved(DepartmentAdminWithFilters):
    pass