from django.contrib.auth.models import User
from django.db import models


class TableV2(models.Model):
    system_name = models.CharField(max_length=255)
    alternative_name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RoleV2(models.Model):
    name = models.CharField(max_length=255)
    humanity_name = models.CharField(max_length=255, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TableUserPermissionV2(models.Model):
    table = models.ForeignKey(TableV2, on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    role = models.ForeignKey(RoleV2, on_delete=models.DO_NOTHING, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ColumnV2(models.Model):
    table = models.ForeignKey(TableV2, on_delete=models.DO_NOTHING)
    system_name = models.CharField(max_length=255)
    position = models.IntegerField(default=0)
    alternative_name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    hidden = models.BooleanField(default=False)
    required = models.BooleanField(default=False)
    readonly = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ColumnV2SelectValues(models.Model):
    column = models.ForeignKey(ColumnV2, on_delete=models.DO_NOTHING)
    value = models.CharField(max_length=255)


class CellFormula(models.Model):
    table_name = models.CharField(max_length=255, default='', blank=True, null=True)
    formula = models.CharField(max_length=255, blank=True, null=True)
    value = models.CharField(max_length=255, blank=True, null=True)
    error = models.CharField(max_length=255, blank=True, null=True)
    row_id = models.BigIntegerField(blank=True, null=True)
    column = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FormulaDeps(models.Model):
    to_row_id = models.BigIntegerField(blank=True, null=True)
    to_column = models.CharField(max_length=255, blank=True, null=True)
    from_row_id = models.BigIntegerField(blank=True, null=True)
    from_column = models.CharField(max_length=255, blank=True, null=True)
    table_name = models.CharField(max_length=255, blank=True, null=True)
