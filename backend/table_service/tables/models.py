import datetime

from django.contrib.auth.models import User
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import IntegerField, FloatField, BooleanField, DateField, F, TextField, Value
from django.db.models.functions import Concat
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.contrib.postgres.fields import ArrayField


class Filial(models.Model):
    """Модель филиала организации"""
    # id = models.IntegerField(primary_key=True)
    name = models.CharField(null=True, blank=True, verbose_name="Название")
    code = models.IntegerField(null=True, blank=True, verbose_name="Код")
    long_name = models.CharField(null=True, blank=True, verbose_name="Полное название")
    short_name = models.CharField(null=True, blank=True, verbose_name="Короткое название")
    set_date = models.DateField(null=True, blank=True, verbose_name="Дата создания")
    end_date = models.DateField(null=True, blank=True, verbose_name="Дата закрытия")
    boss = models.CharField(null=True, blank=True, verbose_name="Руководитель")

    class Meta:
        verbose_name = 'Филиал'
        verbose_name_plural = 'Филиалы'

    def __str__(self):
        return self.name or self.short_name or "Филиал"


class Employee(models.Model):
    """Модель сотрудника"""
    id_filial = models.IntegerField(null=True, blank=True, verbose_name="ID филиала")
    id_department = models.IntegerField(null=True, blank=True, verbose_name="ID отдела")
    post_name = models.CharField(null=True, blank=True, verbose_name="Должность")
    tabnumber = models.IntegerField(unique=True, verbose_name="Табельный номер")  # Табельный номер
    firstname = models.CharField(max_length=50, verbose_name="Имя")
    secondname = models.CharField(max_length=50, verbose_name="Фамилия")
    lastname = models.CharField(max_length=50, verbose_name="Отчество")
    email = models.CharField(max_length=50, verbose_name="email")
    set_date = models.DateField(null=True, blank=True, verbose_name="Дата приема")
    end_date = models.DateField(null=True, blank=True, verbose_name="Дата увольнения")

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'

    def __str__(self):
        return f"{self.secondname} {self.firstname} {self.lastname}"


class Department(models.Model):
    """Модель отдела/департамента"""
    id_parent = models.IntegerField(null=True, blank=True, verbose_name="ID родительского отдела")
    id_filial = models.IntegerField(null=True, blank=True, verbose_name="ID филиала")
    name = models.CharField(null=True, blank=True, verbose_name="Название")
    long_name = models.CharField(null=True, blank=True, verbose_name="Полное название")
    short_name = models.CharField(null=True, blank=True, verbose_name="Короткое название")
    set_date = models.DateField(null=True, blank=True, verbose_name="Дата создания")
    end_date = models.DateField(null=True, blank=True, verbose_name="Дата закрытия")

    class Meta:
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'

    def __str__(self):
        return self.name or self.short_name or "Отдел"


class Profile(models.Model):
    """Профиль пользователя, связанный с сотрудником"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )
    employee = models.OneToOneField(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profile',
        verbose_name="Сотрудник"
    )

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'

    def __str__(self):
        return f"Профиль {self.user.username}"


class Table(models.Model):
    """Основная модель таблицы"""
    title = models.CharField(max_length=200, verbose_name="Название таблицы")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Владелец")
    created_at = models.DateTimeField(default=datetime.datetime.now(), verbose_name="Дата создания")
    share_token = models.CharField(max_length=32, unique=True, blank=True, verbose_name="Токен доступа")
    with_cell_confirm = models.BooleanField(default=False, verbose_name="Подтверждение ячеек")
    with_cell_logging = models.BooleanField(default=False, verbose_name="Логирование изменений")
    delete_row = models.BooleanField(default=False, blank=True, verbose_name="Признак удаления по расписанию строк")
    show_locked_row = models.BooleanField(default=True, blank=True, verbose_name="Показывать заблокированные ячейки")
    allow_user_insert_row = models.BooleanField(default=True, blank=True, verbose_name="Вставка строк через через контекстное меню")
    allow_user_insert_column = models.BooleanField(default=True, blank=True,verbose_name="Вставка стобцов через через контекстное меню")
    open_last_page_by_default = models.BooleanField(default=True, blank=True,verbose_name="Открывать последнюю страницу по умлочанию")

    class Meta:
        verbose_name = 'Таблица'
        verbose_name_plural = 'Таблицы'

    def save(self, *args, **kwargs):
        if not self.share_token:
            self.share_token = get_random_string(32)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('table_detail', kwargs={'pk': self.pk})

    def get_shared_url(self):
        return reverse('shared_table_view', kwargs={'share_token': self.share_token})

    def get_url_for_users(self):
        return f'/shared/{self.share_token}'

    def is_admin(self, user):
        """Проверяет, является ли пользователь админом таблицы"""
        return Admin.objects.filter(user=user).exists()

    def has_add_permission(self, user):
        """Проверяет, может ли пользователь добавлять строки в таблицу"""
        # Проверяем глобальную блокировку для филиала
        filial = Filial.objects.get(id=user.profile.employee.id_filial)
        if TableFilialLock.objects.filter(
                table=self,
                filial=filial,
                locked_by=user
        ).exists():
            return False

        return True

    def has_view_permission(self, user):
        """Проверяет, может ли пользователь видеть таблицу"""
        if self.owner == user:
            return True
        if self.is_admin(user):
            return True
        return self.permissions.filter(user=user, can_view=True).exists()

    @classmethod
    def get_shared_tables(cls, user):
        """Возвращает все таблицы, к которым у пользователя есть доступ"""
        # Таблицы, где пользователь явно указан в TablePermission
        shared_via_permissions = cls.objects.filter(
            permissions__user=user,
        ).distinct()
        return shared_via_permissions

    def __str__(self):
        return self.title


class Admin(models.Model):
    """Администраторы сервиса"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    created_at = models.DateTimeField(default=datetime.datetime.now(), verbose_name="Дата назначения")

    class Meta:
        verbose_name = 'Администратор сервиса'
        verbose_name_plural = 'Администраторы сервиса'

    def __str__(self):
        return f"Админ: {self.user.username}"


class SelectType(models.Model):
    """Типы значений для выпадающих списков"""
    column_id = models.IntegerField(null=True, blank=True, verbose_name="ID колонки")
    name = models.CharField(null=True, blank=True, verbose_name="Значение")
    filial_owner_code = models.CharField(null=True, blank=True, verbose_name="Код филиала владельца")

    class Meta:
        verbose_name = 'Значение выпадающего списка'
        verbose_name_plural = 'Значения выпадающих списков'

    def __str__(self):
        return self.name or "Значение списка"


class Column(models.Model):
    """Колонки таблицы"""
    class ColumnType(models.TextChoices):
        TEXT = 'text', 'Текст'
        INTEGER = 'integer', 'Целое число'
        FLOAT = 'float', 'Число с плавающей точкой'
        BOOLEAN = 'boolean', 'Логическое'
        DATE = 'date', 'Дата'
        DATETIME = 'datetime', 'Дата и время'
        SELECT = 'select', 'Выпадающий список'
        AUTO_INCREMENT = 'auto', 'Автоинкремент'
        FILE = 'file', 'Файл'
        PERMISSION = 'permission', "Права доступа"

    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='columns', verbose_name="Таблица")
    name = models.CharField(max_length=100, verbose_name="Название колонки")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    data_type = models.CharField(
        max_length=10,
        choices=ColumnType.choices,
        default=ColumnType.TEXT,
        verbose_name="Тип данных"
    )
    related_column_ids = models.JSONField(default=list, blank=True, verbose_name="Связанные колонки")
    related_number_column_id = models.IntegerField(blank=True, null=True, verbose_name="Связанная колонка с датой")
    default_value = models.CharField(blank=True, null=True, verbose_name="Значение по умолчанию")
    default_value_from_user_filial_code = models.BooleanField(default=False, verbose_name="Значение по умолчанию из кода филиала работника")
    default_value_from_prev_row = models.BooleanField(default=False, verbose_name="Значение по умолчанию из предыдущей строк")
    available_if_confirm_mode_enabled = models.BooleanField(default=False, verbose_name="Доступно для многократного редактирования в режиме с подтверждением")
    hidden = models.BooleanField(default=False, verbose_name="Скрытая колонка")
    disabled = models.BooleanField(default=False, verbose_name="Запрет на редактирование")
    required = models.BooleanField(default=False, verbose_name="Обязательная для заполнения")

    class Meta:
        ordering = ['order']
        verbose_name = 'Колонка'
        verbose_name_plural = 'Колонки'

    def __str__(self):
        return f"{self.table.title} - {self.name}"


class Row(models.Model):
    """Строки таблицы"""
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='rows', verbose_name="Таблица")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_rows',
        verbose_name="Создатель"
    )
    created_date = models.DateField(auto_now_add=True, verbose_name="Дата создания")


    class Meta:
        ordering = ['order']
        verbose_name = 'Строка'
        verbose_name_plural = 'Строки'



    def has_edit_permission(self, user):
        """Проверяет, может ли пользователь редактировать строку"""
        if self.table.owner == user:
            return True
        if self.table.is_admin(user):
            return True
        return self.permissions.filter(user=user, can_edit=True).exists()

    def has_delete_permission(self, user):
        """Проверяет, может ли пользователь удалять строку"""
        if self.table.owner == user:
            return True
        if self.table.is_admin(user):
            return True
        return self.permissions.filter(user=user, can_delete=True).exists()

    def has_manage_permission(self, user):
        """Проверяет, может ли пользователь управлять правами на строку"""
        if self.table.owner == user:
            return True
        if self.table.is_admin(user):
            return True
        return False

    @classmethod
    def get_visible_rows(cls, user, table):
        """Возвращает строки, которые пользователь может видеть"""
        if table.owner == user:
            return table.rows.all()
        if table.is_admin(user):
            return table.rows.all()
        result = models.Q(permissions__user=user) | models.Q(created_by=user)

        user_filial = None
        if hasattr(user, 'profile') and user.profile.employee:
            user_filial = user.profile.employee.id_filial

        # Если у пользователя есть филиал, добавляем условие для коллег из того же филиала
        if user_filial:
            colleagues = User.objects.filter(
                profile__employee__id_filial=user_filial
            ).values_list('id', flat=True)
            result |= models.Q(created_by__in=colleagues)

        return table.rows.filter(result).distinct()

    @property
    def user_values(self):
        if not hasattr(self, '_user_values_cache'):
            # Получаем пользователя через создателя строки (если он есть)
            user = None
            if self.created_by and hasattr(self.created_by, 'profile') and self.created_by.profile.employee:
                user = self.created_by.profile.employee

            self._user_values_cache = {
                'id': user.id if user else None,
                'firstname': user.firstname if user else '',
                'secondname': user.secondname if user else '',
                'lastname': user.lastname if user else '',
                'full_name': f'{user.secondname} {user.firstname} {user.lastname}' if user else ''
            }
        return self._user_values_cache

    @property
    def filial_values(self):
        if not hasattr(self, '_filial_values_cache'):
            # Получаем филиал через создателя строки (если он есть)
            filial = None
            if self.created_by and hasattr(self.created_by, 'profile') and self.created_by.profile.employee:
                filial_id = self.created_by.profile.employee.id_filial
                filial = Filial.objects.get(id=filial_id)

            self._filial_values_cache = {
                'id': filial.id if filial else None,
                'name': filial.name if filial else '',
            }
        return self._filial_values_cache

    @property
    def cell_values(self):
        if not hasattr(self, '_cell_values_cache'):
            cells = self.cells.select_related('column').all()
            self._cell_values_cache = {
                cell.column: cell.value
                for cell in cells
            }
        return self._cell_values_cache

    @classmethod
    def annotate_for_sorting(cls, queryset, column_id, data_type):
        """Добавляет аннотации для сортировки по типу данных"""
        # Создаем подзапрос для каждого типа данных
        if data_type == Column.ColumnType.INTEGER:
            subquery = Cell.objects.filter(
                row=models.OuterRef('pk'),
                column_id=column_id
            ).values('integer_value')[:1]
            return queryset.annotate(
                **{f'sort_value_{column_id}': models.Subquery(subquery, output_field=IntegerField())}
            )
        elif data_type == Column.ColumnType.FLOAT:
            subquery = Cell.objects.filter(
                row=models.OuterRef('pk'),
                column_id=column_id
            ).values('float_value')[:1]
            return queryset.annotate(
                **{f'sort_value_{column_id}': models.Subquery(subquery, output_field=FloatField())}
            )
        elif data_type == Column.ColumnType.BOOLEAN:
            subquery = Cell.objects.filter(
                row=models.OuterRef('pk'),
                column_id=column_id
            ).values('boolean_value')[:1]
            return queryset.annotate(
                **{f'sort_value_{column_id}': models.Subquery(subquery, output_field=BooleanField())}
            )
        elif data_type == Column.ColumnType.DATE:
            subquery = Cell.objects.filter(
                row=models.OuterRef('pk'),
                column_id=column_id
            ).values('date_value')[:1]
            return queryset.annotate(
                **{f'sort_value_{column_id}': models.Subquery(subquery, output_field=DateField())}
            )
        else:  # TEXT
            queryset = queryset.annotate(
                user_full_name=Concat(
                    F('created_by__profile__employee__secondname'),
                    Value(' '),
                    F('created_by__profile__employee__firstname'),
                    Value(' '),
                    F('created_by__profile__employee__lastname'),
                    output_field=TextField()
                )
            )

            subquery = Cell.objects.filter(
                row=models.OuterRef('pk'),
                column_id=column_id
            ).values('text_value')[:1]
            return queryset.annotate(
                **{f'sort_value_{column_id}': models.Subquery(subquery, output_field=TextField())}
            )


class Cell(models.Model):
    """Ячейки таблицы"""
    table_id = models.IntegerField(blank=True, null=True, verbose_name="ID таблицы")
    row = models.IntegerField(blank=True, null=True, verbose_name="ID строки")
    column = models.IntegerField(blank=True, null=True, verbose_name="ID колонки")
    value = models.TextField(blank=True, null=True, verbose_name="Значение")
    formula_value = models.TextField(blank=True, null=True, verbose_name="Значение формулы")
    color = models.TextField(blank=True, null=True, verbose_name="Цвет ячейки")

    class Meta:
        unique_together = ('row', 'column')
        verbose_name = 'Ячейка'
        verbose_name_plural = 'Ячейки'

    def __str__(self):
        return f"{self.row} - {self.column}: {self.value}"


class CellFile(models.Model):
    """Файл, привязанный к ячейке таблицы"""

    # Связь с ячейкой (один файл может быть связан с одной ячейкой)
    cell = models.ForeignKey(
        Cell,
        on_delete=models.DO_NOTHING,
        related_name='cellfile_set',
        verbose_name="Ячейка"
    )

    # Сам файл, хранящийся в БД
    file = models.BinaryField(
        verbose_name="Файл",
        editable=True
    )

    # Мета-информация о файле
    filename = models.CharField(
        max_length=255,
        verbose_name="Имя файла"
    )

    file_extension = models.CharField(
        max_length=10,
        verbose_name="Расширение файла",
        blank=True
    )

    file_size = models.BigIntegerField(
        verbose_name="Размер файла (байт)",
        blank=True,
        null=True
    )

    content_type = models.CharField(
        max_length=100,
        verbose_name="MIME-тип",
        blank=True
    )

    # Информация о загрузке
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата загрузки"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    # Информация о версиях/заменах
    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Версия файла"
    )

    previous_file_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name="Хеш предыдущей версии"
    )

    # Дополнительная информация
    uploaded_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Кем загружен"
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Описание файла"
    )

    class Meta:
        verbose_name = 'Файл ячейки'
        verbose_name_plural = 'Файлы ячеек'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['cell']),
            models.Index(fields=['uploaded_at']),
            models.Index(fields=['filename']),
        ]

    def __str__(self):
        return f"{self.filename} (Cell {self.cell.row}:{self.cell.column})"

    def save(self, *args, **kwargs):
        # Автоматическое определение расширения и размера при сохранении
        if self.file and not self.file_extension:
            if '.' in self.filename:
                self.file_extension = self.filename.split('.')[-1].lower()

        if self.file and not self.file_size:
            self.file_size = len(self.file)

        super().save(*args, **kwargs)


class CellFileHistory(models.Model):
    """История замен файлов"""

    cell_file = models.ForeignKey(
        CellFile,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name="Файл"
    )

    file = models.BinaryField(verbose_name="Файл (предыдущая версия)")
    filename = models.CharField(max_length=255, verbose_name="Имя файла")
    version = models.PositiveIntegerField(verbose_name="Версия")
    replaced_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата замены")
    replaced_by = models.CharField(max_length=150, blank=True, null=True, verbose_name="Кем заменен")

    class Meta:
        verbose_name = 'История файла'
        verbose_name_plural = 'История файлов'
        ordering = ['-replaced_at']


class TablePermission(models.Model):
    """Права доступа к таблице для пользователей"""
    class UserRoles(models.TextChoices):
        OWNER = 'owner','Создатель'
        USER = 'user','Рядовой'
        ADMIN = 'admin','Админ'
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='permissions', verbose_name="Таблица")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    can_view = models.BooleanField(default=True, verbose_name="Может просматривать")
    can_edit = models.BooleanField(default=True, verbose_name="Может редактировать")
    role = models.CharField(
                            verbose_name='Роль пользователя',
                            max_length=20,
                            choices=UserRoles.choices,
                            default=UserRoles.USER)

    class Meta:
        unique_together = ('table', 'user')
        verbose_name = 'Право доступа к таблице'
        verbose_name_plural = 'Права доступа к таблицам'

    def __str__(self):
        return f"{self.user.username} - {self.table.title}"


class TableFilialPermission(models.Model):
    """Права доступа к таблице для филиалов"""
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='filial_permissions', verbose_name="Таблица")
    filial = models.ForeignKey(Filial, on_delete=models.CASCADE, verbose_name="Филиал")
    can_view = models.BooleanField(default=True, verbose_name="Может просматривать")

    class Meta:
        unique_together = ('table', 'filial')
        verbose_name = 'Право доступа филиала'
        verbose_name_plural = 'Права доступа филиалов'

    def __str__(self):
        return f"{self.filial.name} - {self.table.title}"


class RowPermission(models.Model):
    """Права доступа к строкам для пользователей"""
    table = models.IntegerField(blank=False, verbose_name="ID таблицы")
    row = models.IntegerField(blank=False, verbose_name="ID строки")
    user = models.IntegerField(blank=False, verbose_name="ID пользователя")
    can_edit = models.BooleanField(default=True, verbose_name="Может редактировать")
    can_delete = models.BooleanField(default=False, verbose_name="Может удалять")

    class Meta:
        unique_together = ('row', 'user')
        verbose_name = 'Право доступа к строке'
        verbose_name_plural = 'Права доступа к строкам'

    def __str__(self):
        return f"Строка {self.row} - Пользователь {self.user}"


class RowFilialPermission(models.Model):
    """Права доступа к строкам для филиалов"""
    row = models.IntegerField(blank=False, verbose_name="ID строки")
    filial = models.IntegerField(blank=False, verbose_name="ID филиала")
    can_edit = models.BooleanField(default=True, verbose_name="Может редактировать")
    can_delete = models.BooleanField(default=False, verbose_name="Может удалять")

    class Meta:
        unique_together = ('row', 'filial')
        verbose_name = 'Право филиала на строку'
        verbose_name_plural = 'Права филиалов на строки'

    def __str__(self):
        return f"Строка {self.row} - Филиал {self.filial}"


class RowLock(models.Model):
    """Блокировки строк"""
    row = models.OneToOneField(
        Row,
        on_delete=models.CASCADE,
        related_name='lock',
        verbose_name="Строка"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='row_locks',
        verbose_name="Пользователь"
    )
    locked_at = models.DateTimeField(verbose_name="Время блокировки")

    class Meta:
        verbose_name = 'Блокировка строки'
        verbose_name_plural = 'Блокировки строк'

    def __str__(self):
        return f"Строка {self.row.id} заблокирована {self.user.username}"


class TableFilialLock(models.Model):
    """Блокировки добавления строк для филиалов"""
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='filial_add_permissions', verbose_name="Таблица")
    filial = models.ForeignKey(Filial, on_delete=models.CASCADE, verbose_name="Филиал")
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Заблокировал")
    locked_at = models.DateTimeField(verbose_name="Время блокировки")

    class Meta:
        unique_together = ('table', 'filial')
        verbose_name = 'Блокировка филиала'
        verbose_name_plural = 'Блокировки филиалов'

    def __str__(self):
        return f"{self.filial.name} - {self.table.title}"


class ColumnPermission(models.Model):
    """Права доступа к колонкам для пользователей"""
    column = models.IntegerField(blank=False, verbose_name="ID колонки")
    user = models.IntegerField(blank=False, verbose_name="ID пользователя")
    table = models.IntegerField(blank=False, verbose_name="ID таблицы")
    can_view = models.BooleanField(default=True, verbose_name="Может просматривать")
    can_edit = models.BooleanField(default=True, verbose_name="Может редактировать")

    class Meta:
        unique_together = ('column', 'user')
        verbose_name = 'Право доступа к колонке'
        verbose_name_plural = 'Права доступа к колонкам'

    def __str__(self):
        return f"Колонка {self.column} - Пользователь {self.user}"


class ColumnFilialPermission(models.Model):
    """Права доступа к колонкам для филиалов"""
    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name='filial_add_permissions', verbose_name="Колонка")
    filial = models.ForeignKey(Filial, on_delete=models.CASCADE, verbose_name="Филиал")
    table = models.IntegerField(blank=False, verbose_name="ID таблицы")
    can_delete = models.BooleanField(default=True, verbose_name="Может удалять")
    can_edit = models.BooleanField(default=True, verbose_name="Может редактировать")

    class Meta:
        unique_together = ('column', 'filial')
        verbose_name = 'Право филиала на колонку'
        verbose_name_plural = 'Права филиалов на колонки'

    def __str__(self):
        return f"{self.column.name} - {self.filial.name}"


class CellLock(models.Model):
    """Блокировки ячеек"""
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name='cells_lock_cell', unique=True, verbose_name="Ячейка")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cells_lock_user', verbose_name="Пользователь")
    locked_at = models.DateTimeField(default=datetime.datetime.now(), verbose_name="Время блокировки")

    class Meta:
        verbose_name = 'Блокировка ячейки'
        verbose_name_plural = 'Блокировки ячеек'

    def __str__(self):
        return f"Ячейка {self.cell.id} заблокирована {self.user.username}"


class CellEditLog(models.Model):
    """Лог изменений ячеек"""
    user_id = models.IntegerField(verbose_name="ID пользователя")
    old_value = models.CharField(null=True, verbose_name="Старое значение")
    new_value = models.CharField(null=True, verbose_name="Новое значение")
    cell_id = models.IntegerField(verbose_name="ID ячейки")
    row_id = models.IntegerField(null=True, verbose_name="ID строки")
    date_time = models.DateTimeField(null=True, auto_now=True)

    class Meta:
        verbose_name = 'Лог изменения ячейки'
        verbose_name_plural = 'Лог изменений ячеек'

    def __str__(self):
        return f"Ячейка {self.cell_id} изменена пользователем {self.user_id}"


class TableUserOnline(models.Model):
    """Пользователи онлайн в таблицах"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    table = models.ForeignKey(Table, on_delete=models.CASCADE, verbose_name="Таблица")

    class Meta:
        verbose_name = 'Пользователь онлайн'
        verbose_name_plural = 'Пользователи онлайн'

    def __str__(self):
        return f"{self.user.username} в {self.table.title}"


class CellComment(models.Model):
    cell_id = models.IntegerField(verbose_name="ID ячейки")
    user_id = models.IntegerField(verbose_name="ID пользователя")
    table = models.ForeignKey(Table, on_delete=models.CASCADE, verbose_name="Таблица", blank=True, null=True)
    text = models.TextField(verbose_name="Комментарий")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата комментария")


class UserOnlineHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    date = models.DateField(null=True, blank=True, verbose_name="Дата")


class Company(models.Model):
    inn = models.CharField(blank=True, null=True, verbose_name='ИНН')
    ogrn = models.CharField(blank=True, null=True, verbose_name='ОГРН')
    kpp = models.CharField(blank=True, null=True, verbose_name='КПП')
    okpo = models.CharField(blank=True, null=True, verbose_name='ОКПО')
    okved = models.CharField(blank=True, null=True, verbose_name='ОКВЭД')
    address = models.TextField(blank=True, null=True, verbose_name='Адрес')
    short_name = models.CharField(blank=True, null=True, verbose_name='Краткое наименование')

    class Meta:
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'


class RowValuePermission(models.Model):
    user_ids = ArrayField(
        models.IntegerField(),
        default=list,
        blank=True,
    )
    table_id = models.ForeignKey(Table, related_name="row_value_permissions", db_index=True, on_delete=models.CASCADE)
    column_id = models.IntegerField(db_index=True)
    cell_value = models.CharField(max_length=255, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['table_id', 'column_id', 'cell_value'],
                name='unique_permission',
            )
        ]
        indexes = [
            GinIndex(fields=['user_ids'], name='row_value_permission'),
            models.Index(fields=['table_id', 'column_id']),
            models.Index(fields=['cell_value']),
        ]
