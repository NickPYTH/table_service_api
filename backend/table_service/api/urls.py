from django.urls import path, include
from rest_framework.routers import DefaultRouter


from . import views, simple_views
from .simple_views import create_table, proxy, recalculate_formulas, set_all_permission, remove_all_permission, \
    set_permissions_by_filial_code_column, normalize_numbers, update_general_formula_by_column, load_select_list, \
    get_email_by_tabnumber, get_union_permission_by_table_id, update_column_privelege_by_table_user, get_251_report, \
    get_crane_cover_report, get_work_cover_report

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='users')
router.register(r'filials', views.FilialViewSet, basename='filials')
router.register(r'departments', views.DepartmentViewSet, basename='departments')
router.register(r'employees', views.EmployeeViewSet, basename='employees')
router.register(r'profiles', views.ProfileViewSet, basename='profiles')
router.register(r'admins', views.AdminViewSet, basename='admins')
router.register(r'tables', views.TableListViewSet, basename='tables')
router.register(r'table', views.TableDetailViewSet, basename='table-detail')
router.register(r'columns', views.ColumnViewSet, basename='columns')

router.register(r'cells', views.CellViewSet, basename='cells')

# router.register(r'cells/update_cell_group', views.update_cell_group, basename='cells_update_cell_group')

router.register(r'row', views.RowDetailViewSet, basename='row')

router.register(r'rows', views.RowListViewSet, basename='rows')

router.register(r'tablepermissions', views.TablePermissionViewSet, basename='tablepermissions')

router.register(r'tbfilialpermissions', views.TableFilialPermissionViewSet, basename='tbfilialpermissions')

router.register(r'rowpermissions', views.RowPermissionViewSet, basename='row-permissions')

router.register(r'rowfilialpermissions', views.RowFilialPermissionViewSet, basename='rowfilialpermissions')

router.register(r'columnpermissions', views.ColumnPermissionViewSet, basename='column-permissions')

router.register(r'rowfile', views.RowUploadViewSet, basename='rowfile')

router.register(r'selecttype', views.SelectTypeViewSet, basename='selecttype')

router.register(r'celleditlog', views.CellEditLogViewSet, basename='celleditlog')

router.register(r'cellcomment', views.CellCommentViewSet, basename='cellcomment')

router.register(r'cellfiles', views.CellFileViewSet, basename='cellfiles')

router.register(r'columnfilialpermissions', views.ColumnFilialPermissionViewSet, basename='columnfilialpermissions')

router.register(r'rowvaluepermissions', views.RowValuePermissionViewSet, basename='rowvaluepermissions')

urlpatterns = [
    path('update_inn', simple_views.update_inn, name='update_inn'),
    path('get_current_user', views.CurrentUserView.as_view(), name='get_current_user'),
    path('users_search', simple_views.search_user, name='search_user'),
    path('cells_clear_range', simple_views.clear_range, name='clear_range'),  # Очистить диапазон ячеек
    path('cells_update_range', simple_views.update_range, name='update_range'),  # Растянуть диапазон ячеек,
    path('create_table', create_table, name='create_table'),
    path('recalculate_formulas', recalculate_formulas, name='recalculate_formulas'),
    path('normalize_numbers', normalize_numbers, name='normalize_numbers'),
    path('set_all_permission', set_all_permission, name='set_all_permission'),
    path('remove_all_permission', remove_all_permission, name='remove_all_permission'),
    path('set_permissions_by_filial_code_column', set_permissions_by_filial_code_column, name='set_permissions_by_filial_code_column'),
    path('proxy', proxy, name='proxy'),
    path('update_general_formula_by_column', update_general_formula_by_column, name='update_general_formula_by_column'),
    path('loadSelectList', load_select_list, name='load_select_list'),
    path('get_email_by_tabnumber', get_email_by_tabnumber, name='get_email_by_tabnumber'),
    path('get_union_permission_by_table_id', get_union_permission_by_table_id, name='get_union_permission_by_table_id'),
    path('update_column_privelege_by_table_user', update_column_privelege_by_table_user, name='update_column_privelege_by_table_user'),
    path('get_251_report', get_251_report, name='get_251_report'),
    path('get_crane_cover_report',get_crane_cover_report, name='get_crane_cover_report'),
    path('get_work_cover_report', get_work_cover_report, name='get_work_cover_report'),
    path('create_mass_permission', simple_views.create_mass_permissions, name='create_mass_permission'),
    path('', include(router.urls)),

]
