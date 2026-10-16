from django.urls.conf import path

from . import column_views, row_views, cell_views, table_user_permission_views, table_filial_permission_views
from . import views

urlpatterns = [
    path('remove_table_permission/', table_user_permission_views.remove_table_permission,
         name='remove_table_permission'),
    path('delete_table/', views.delete_table, name='delete_table'),
    path('delete_row/', row_views.delete_row, name='delete_row'),
    path('update_cell/', cell_views.update_cell_request, name='update_cell'),
    path('create_from_file/', views.create_from_file, name='create_from_file'),
    path('get_table_data/', views.get_table_data, name='get_table_data'),
    path('get_table_info/', views.get_table_info, name='get_table_info'),
    path('get_table_list/', views.get_table_list, name='get_table_list'),
    path('get_cell_formula/', cell_views.get_cell_formula, name='get_cell_formula'),
    path('get_table_columns/', column_views.get_columns_by_table, name='get_table_columns'),
    path('update_column/', column_views.update_column, name='update_column'),
    path('get_column/', column_views.get_column, name='get_column'),
    path('get_column_select_list/', column_views.get_column_select_list, name='get_column_select_list'),
    path('create_column_select_list/', column_views.create_column_select_list, name='create_column_select_list'),
    path('update_column_select_list/', column_views.update_column_select_list, name='update_column_select_list'),
    path('delete_column_select_list/', column_views.delete_column_select_list, name='delete_column_select_list'),
    path('insert_row/', row_views.insert_row, name='insert_row'),
    path('insert_column/', column_views.insert_column, name='insert_column'),
    path('update_table_info/', views.update_table_info, name='update_table_info'),
    path('get_user_table_permissions/', table_user_permission_views.get_user_table_permissions,
         name='get_user_table_permissions'),
    path('get_user_table_permission/', table_user_permission_views.get_user_table_permission,
         name='get_user_table_permission'),
    path('search_user/', views.search_user, name='search_user'),
    path('update_table_permission/', table_user_permission_views.update_table_permission,
         name='update_table_permission'),

    path('remove_table_filial_permission/', table_filial_permission_views.remove_table_filial_permission,
         name='remove_table_filial_permission'),
    path('update_table_filial_permission/', table_filial_permission_views.update_table_filial_permission,
         name='update_table_filial_permission'),
    path('get_table_filial_permission/', table_filial_permission_views.get_table_filial_permission,
         name='get_table_filial_permission'),
    path('get_table_filial_permissions/', table_filial_permission_views.get_table_filial_permissions,
         name='get_table_filial_permissions'),

]
