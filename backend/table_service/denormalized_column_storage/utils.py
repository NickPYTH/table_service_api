import re

from django.db import connection
from pycel.excelformula import ExcelFormula, OperatorNode, OperandNode, RangeNode

from denormalized_column_storage.models import FormulaDeps, CellFormula


def col_letter(n):
    """Конвертация имени колонки в формат А1"""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord('A') + rem) + result
    return result.lower()


def escape_tsv(value):
    """Убираем ломающие tsv формат символы"""
    s = str(value)
    s = s.replace("\\", "\\\\")  # сначала бэкслеш
    s = s.replace("\t", "\\t")  # табуляция
    s = s.replace("\n", "\\n")  # перенос строки
    s = s.replace("\r", "\\r")  # возврат каретки
    return s


def get_sql_compare_operator(compare_operator):
    """Получение оператора SQL из запроса клиента"""
    if compare_operator == "contains":
        return "ILIKE"
    elif compare_operator == "equals":
        return "="


def check_column_exist_in_table(column_name, table_name):
    with connection.cursor() as cursor:
        sql = f"""
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}' AND column_name = '{column_name}';
                """
        cursor.execute(sql)
        exist = cursor.fetchone()
    return exist is not None


def build_order_by_sql(sort_fields, table_name):
    """Формируем ORDER BY часть в формате SQL"""
    if len(sort_fields) == 0:
        return 'ORDER BY id'
    # должно получиться так - ORDER BY status DESC, name ASC
    result = "ORDER BY"
    for sort_field in sort_fields:
        if check_column_exist_in_table(sort_field['field'], table_name):
            result += f" {sort_field['field']} {sort_field['sort'].upper()},"
    if result == "ORDER BY":
        return 'ORDER BY id'
    return result[:-1]


def get_table_column_list_sql(table_name):
    """Возвращает список колонок для таблицы"""
    with connection.cursor() as cursor:
        cursor.execute(f"""
                       SELECT column_name
                       FROM information_schema.columns
                       WHERE table_schema = 'collector' AND table_name = '{table_name}'
                       """)
        return [row[0] for row in cursor.fetchall()]


def build_quick_filter_sql(table_name, search_value):
    """Формируем часть WHERE для быстрого поиска по всем колонкам"""
    EXCLUDED_COLUMNS = {'id', 'allowed_users', 'allowed_filials', 'order'}
    columns = get_table_column_list_sql(table_name)
    safe_columns = [
        f'"{col}"'
        for col in columns
        if col
           and col.strip()
           and col.strip().lower() not in EXCLUDED_COLUMNS
    ]
    concat_expression = f"CONCAT_WS(' ', {', '.join(safe_columns)})"
    quick_filter_sql = f"{concat_expression} ILIKE '%{search_value}%'"
    return quick_filter_sql


def build_filter_sql(table_name, filter_fields):
    """Формируем WHERE часть в формате SQL"""
    result = f"WHERE allowed_users @> ARRAY[{[1]}]"
    if 'items' not in filter_fields:
        return result
    if 'logicOperator' in filter_fields:
        logic_operator = filter_fields['logicOperator']
    else:
        logic_operator = 'and'
    quick_filter_sql = ""
    if 'quickFilterValues' in filter_fields:
        search_value = ''.join(filter_fields['quickFilterValues'])
        quick_filter_sql = build_quick_filter_sql(table_name, search_value)
    filters = ""
    for filter_field in filter_fields['items']:
        compare_operator = filter_field['operator']
        if 'value' in filter_field:
            compare_value = filter_field['value']
        else:
            compare_value = ''
        if compare_operator == "contains":
            compare_value = f"%{compare_value}%"
        filters += f"{filter_field['field']} {get_sql_compare_operator(compare_operator)} '{compare_value}' {logic_operator} "
    filters = filters[:-(len(logic_operator) + 1)]
    if len(filters) > 0:
        if len(quick_filter_sql) > 0:
            tmp = f"({filters} AND {quick_filter_sql})"
            result += f" AND ({tmp})"
        else:
            result += f" AND ({filters})"
    else:
        if len(quick_filter_sql) > 0:
            result += f" AND ({quick_filter_sql})"
    return result


def splice_node(value):
    """Разбиваем адрес ячейки(A1) на колонку и строку AA22 - AA 22"""
    reg = re.compile(r"^\$?([A-Z]+)\$?(\d+)$")
    m = reg.match(value.upper())
    letters, digits = m.group(1), m.group(2)
    return letters, int(digits)


def fill_formula_dependencies(table_name, from_column, from_row_id, formula_str):
    """Создаем граф зависимостей формул друг от друга по входной формуле"""
    formula = ExcelFormula(formula_str)
    for node in formula.rpn:
        if type(node) == RangeNode:
            column_name, row_id = splice_node(node.value)
            # Пропускаем саму ячейку из зависимых
            if column_name == from_column and row_id == from_row_id:
                continue
            FormulaDeps.objects.create(from_row_id=from_row_id,
                                       from_column=from_column.lower(),
                                       to_column=column_name.lower(),
                                       to_row_id=row_id,
                                       table_name=table_name
                                       )


def get_cell_value(table_name, cell):
    """SQL запрос получения данных ячейки"""
    column_name, row_id = splice_node(cell)
    with connection.cursor() as cursor:
        # Получаем кол-во записей
        cursor.execute(
            f"SELECT {column_name} FROM {table_name} WHERE id = {row_id}"
        )
        value = cursor.fetchone()[0]
        return value


def stack_calculator(table_name, formula_str):
    """Расчет результата формулы"""
    stack = []
    formula = ExcelFormula(formula_str)
    for node in formula.rpn:
        if type(node) == OperandNode:
            stack.append(int(node.value))
        if type(node) == RangeNode:
            stack.append(get_cell_value(table_name, node.value))
        if type(node) == OperatorNode:
            if node.value == '+':
                item_1 = int(stack.pop())
                item_2 = int(stack.pop())
                stack.append(item_1 + item_2)
            if node.value == '-':
                item_1 = int(stack.pop())
                item_2 = int(stack.pop())
                stack.append(item_2 - item_1)
    if len(stack) == 1:
        return stack[0]
    else:
        return 0


def calculate_formula(table_name, column_name, row_id, formula_str):
    """Обертка расчета формул"""
    # Проверяем наличие записи о формуле
    try:
        cell_formula = CellFormula.objects.get(table_name=table_name, column=column_name, row_id=row_id)
    except Exception as e:
        cell_formula = CellFormula.objects.create(table_name=table_name, column=column_name, row_id=row_id)
    # Проверяем изменилась ли формула, если да, то чистим граф зависимостей
    if cell_formula.formula != formula_str:
        cell_formula.formula = formula_str
        FormulaDeps.objects.filter(table_name=table_name, from_column=column_name, from_row_id=row_id).delete()
        fill_formula_dependencies(table_name, column_name, row_id, formula_str)
    cell_formula.value = stack_calculator(table_name, formula_str)
    cell_formula.save()
    return cell_formula.value


def update_cell(table_name, column_name, row_id, value):
    """SQL запрос обновления данных ячейки"""
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table_name} SET {column_name} = '{value}' WHERE id = {row_id}",
        )


def recursive_update(table_name, table_id, column_name, row_id, updated_cell):
    """SQL запрос рекурсивного обхода и зависимых ячеек и пересчета значений формул"""
    # print(f"Ячейка {column_name}{row_id}")
    with connection.cursor() as cursor:
        cursor.execute(f"""
                            with recursive affected as (
                            select from_column, from_row_id
                            from collector.denormalized_column_storage_formuladeps
                            where table_name='{table_name}' AND to_row_id = {row_id} AND to_column = '{column_name}'
                            UNION
                            SELECT fd.from_column, fd.from_row_id
                            FROM collector.denormalized_column_storage_formuladeps fd
                            JOIN affected a
                              ON fd.to_row_id = a.from_row_id AND fd.to_column = a.from_column
                            WHERE fd.table_name = '{table_name}'
                        )
                        SELECT DISTINCT from_column, from_row_id FROM affected;
                        """)
        rows = cursor.fetchall()  # [('b', 2)]
    # print(f"От нее зависят эти {rows}")
    for column, row_id_l in rows:
        cell_formula = CellFormula.objects.get(table_name=table_name, column=column, row_id=row_id_l)
        value = calculate_formula(table_name, column, row_id_l, cell_formula.formula)
        update_cell(table_name, column, row_id_l, value)
        updated_cell.append({
            "table_name": table_name,
            "table_id": table_id,
            "column_name": column,
            "row_id": row_id_l,
            "value": value
        })
        recursive_update(table_name, table_id, column, row_id_l, updated_cell)
    return updated_cell
