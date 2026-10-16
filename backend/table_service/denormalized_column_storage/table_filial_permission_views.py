from django.contrib.auth.models import User
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from tables.models import Filial
from .models import TableV2, TableFilialPermissionV2, RoleV2
from .request_validate import add_table_filial_permission_request_validate, \
    update_table_filial_permission_request_validate


@api_view(['GET'])
def get_table_filial_permissions(request):
    table_id = request.query_params.get('table_id')
    table = TableV2.objects.get(id=table_id)
    response = []
    for permission in TableFilialPermissionV2.objects.filter(table=table):
        filial = permission.filial
        role = permission.role
        response.append({
            "id": permission.id,
            "table_id": permission.table.id,
            "filial_id": permission.filial.id,
            "filial": filial.name,
            "role_id": role.id,
            "role_name": role.humanity_name,
        })
    return Response(response)


@api_view(['GET'])
def get_table_filial_permission(request):
    id = request.query_params.get('id')
    p = TableFilialPermissionV2.objects.get(id=id)
    return Response({
        "id": p.id,
        "filial": p.filial.name,
        "role": p.role.name
    })


@api_view(['POST'])
def remove_table_filial_permission(request):
    """Метод для удаления прав на таблицу(TablePermissionV2) + удаление filial_id в каждой строке"""
    permission_id = request.data['permission_id']
    tp = TableFilialPermissionV2.objects.get(id=permission_id)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
                UPDATE "{tp.table.system_name}"
                SET allowed_filials = array_remove(allowed_filials, {tp.filial.id})
                WHERE {tp.filial.id} = ANY(allowed_filials)
            """,
        )

    tp.delete()

    return Response({'result': 'success'})


@api_view(['POST'])
def update_table_filial_permission(request):
    table_id, filial_name, role, permission_id = update_table_filial_permission_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    filial = Filial.objects.get(name=filial_name)
    role = RoleV2.objects.get(name=role)
    if permission_id is None:
        TableFilialPermissionV2.objects.create(
            filial=filial,
            table=table,
            role=role
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                    UPDATE "{table.system_name}"
                    SET allowed_filials = array_append(allowed_filials, {filial.id})
                    WHERE NOT ({filial.id} = ANY(allowed_filials))
                """,
            )
    else:
        tp = TableFilialPermissionV2.objects.get(id=permission_id)
        tp.filial = filial
        tp.role = role
        tp.save()
    return Response({'result': 'success'})
