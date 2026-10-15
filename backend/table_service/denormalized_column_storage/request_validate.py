def create_from_file_request_validate(request):
    try:
        file = request.FILES.get("file")
    except Exception as e:
        raise e
    try:
        table_name = request.data["table_name"]
    except Exception as e:
        raise e

    return file, table_name

def get_table_data_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e
    try:
        page = int(request.data['page'])
    except Exception as e:
        raise e
    try:
        page_size = int(request.data['pageSize'])
        if page_size == 0:
            raise Exception("Page size is 0")
    except Exception as e:
        raise e
    try:
        sort = request.data['sort']
    except Exception as e:
        raise e
    try:
        filter = request.data['filter']
    except Exception as e:
        raise e
    try:
        group_fields = request.data['group_fields']
    except Exception as e:
        raise e
    try:
        group_keys = request.data['group_keys']
    except Exception as e:
        raise e

    return table_id, page, page_size, sort, filter, group_fields, group_keys

def get_table_info_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e

    return table_id

def update_cell_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e
    try:
        column_name = request.data['column_name']
    except Exception as e:
        raise e
    try:
        row_id = request.data['row_id']
    except Exception as e:
        raise e
    try:
        value = request.data['value']
    except Exception as e:
        raise e

    return table_id, column_name, row_id, value

def delete_row_request_validate(request):
    try:
        table_name = request.data['table_name']
    except Exception as e:
        raise e
    try:
        row_id = request.data['row_id']
    except Exception as e:
        raise e
    return table_name, row_id

def delete_table_request_validate(request):
    try:
        table_name = request.data['table_name']
    except Exception as e:
        raise e
    return table_name

def add_table_permission_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e
    try:
        user_id = request.data['user_id']
    except Exception as e:
        raise e
    return table_id, user_id

def remove_table_permission_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e
    try:
        user_id = request.data['user_id']
    except Exception as e:
        raise e
    return table_id, user_id

def update_column_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e
    try:
        column_system_name = request.data['column_system_name']
    except Exception as e:
        raise e
    try:
        column_alternative_name = request.data['column_alternative_name']
    except Exception as e:
        raise e
    try:
        column_type = request.data['type']
    except Exception as e:
        raise e
    try:
        hidden = request.data['hidden']
    except Exception as e:
        raise e
    try:
        required = request.data['required']
    except Exception as e:
        raise e
    try:
        readonly = request.data['readonly']
    except Exception as e:
        raise e
    return table_id, column_system_name, column_alternative_name, column_type, hidden, required, readonly

def insert_column_request_validate(request):
    try:
        table_id = request.data['table_id']
    except Exception as e:
        raise e
    try:
        neighborhood_system_name = request.data['neighborhood_system_name']
    except Exception as e:
        raise e
    try:
        position_name = request.data['position_name']
    except Exception as e:
        raise e
    try:
        alternative_name = request.data['alternative_name']
    except Exception as e:
        raise e
    try:
        column_type = request.data['column_type']
    except Exception as e:
        raise e
    try:
        hidden = request.data['hidden']
    except Exception as e:
        raise e
    try:
        required = request.data['required']
    except Exception as e:
        raise e
    try:
        readonly = request.data['readonly']
    except Exception as e:
        raise e
    return table_id, neighborhood_system_name, position_name, alternative_name, column_type, hidden, required, readonly

def get_column_request_validate(request):
    try:
        table_id = request.GET.get('table_id')
    except Exception as e:
        raise e
    try:
        system_name = request.GET.get('system_name')
    except Exception as e:
        raise e
    return table_id, system_name
