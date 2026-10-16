from django.contrib.auth.models import User
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from tables.models import Profile
from .models import TableV2, TableUserPermissionV2, RoleV2
from .request_validate import add_table_permission_request_validate, update_table_permission_request_validate


@api_view(['GET'])
def get_user_table_permissions(request):
    table_id = request.query_params.get('table_id')
    table = TableV2.objects.get(id=table_id)
    response = []
    for permission in TableUserPermissionV2.objects.filter(table=table):
        user = permission.user
        profile = Profile.objects.get(user=user)
        role = permission.role
        response.append({
            "id": permission.id,
            "table_id": permission.table.id,
            "user_id": permission.user.id,
            "fio": f"{profile.employee.lastname} {profile.employee.firstname[0]}. {profile.employee.lastname[0]}.",
            "role_id": role.id,
            "role_name": role.humanity_name,
        })
    return Response(response)


@api_view(['GET'])
def get_user_table_permission(request):
    id = request.query_params.get('id')
    p = TableUserPermissionV2.objects.get(id=id)
    return Response({
        "id": p.id,
        "username": p.user.username,
        "role": p.role.name
    })


@api_view(['POST'])
def remove_table_permission(request):
    """Метод для удаления прав на таблицу(TablePermissionV2) + удаление user_id в каждой строке"""
    table_id, permission_id = add_table_permission_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    user = User.objects.get(username=username)
    table_permission = TableUserPermissionV2.objects.filter(
        user=user,
        table=table,
    )
    table_permission.delete()

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
                UPDATE "{table.system_name}"
                SET allowed_users = array_remove(allowed_users, {user.id})
                WHERE {user.id} = ANY(allowed_users)
            """,
        )

    return Response({'result': 'success'})


@api_view(['POST'])
def update_table_permission(request):
    table_id, username, role, permission_id = update_table_permission_request_validate(request)
    table = TableV2.objects.get(id=table_id)
    user = User.objects.get(username=username)
    role = RoleV2.objects.get(name=role)
    if permission_id is None:
        TableUserPermissionV2.objects.create(
            user=user,
            table=table,
            role=role
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                    UPDATE "{table.system_name}"
                    SET allowed_users = array_append(allowed_users, {user.id})
                    WHERE NOT ({user.id} = ANY(allowed_users))
                """,
            )
    else:
        tp = TableUserPermissionV2.objects.get(id=permission_id)
        tp.role = role
        tp.user = user
        tp.save()
    return Response({'result': 'success'})
