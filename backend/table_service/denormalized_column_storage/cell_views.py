from rest_framework.decorators import api_view
from rest_framework.response import Response

from denormalized_column_storage.models import FormulaDeps, CellFormula, TableV2
from denormalized_column_storage.request_validate import update_cell_request_validate
from denormalized_column_storage.utils import recursive_update, update_cell, calculate_formula
from denormalized_column_storage.ws_sender import send_cell_update


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
