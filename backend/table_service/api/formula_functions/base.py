"""Базовые функции формул"""

def sum_function(args, table_id, get_cell_value):
    """Функция СУММ"""
    total = 0
    for arg in args:
        if isinstance(arg, (int, float)):
            total += arg
        else:
            value = get_cell_value(arg, table_id)
            if isinstance(value, (int, float)):
                total += value
    return total


def razn_function(args, table_id, get_cell_value):
    """Функция РАЗН - разница между первым и суммой остальных аргументов"""
    if not args:
        return 0

    # Первый аргумент
    if isinstance(args[0], (int, float)):
        total = args[0]
    else:
        total = get_cell_value(args[0], table_id)
        if not isinstance(total, (int, float)):
            total = float(total) if str(total).replace('.', '', 1).isdigit() else 0

    # Вычитаем остальные аргументы
    for arg in args[1:]:
        if isinstance(arg, (int, float)):
            total -= arg
        else:
            value = get_cell_value(arg, table_id)
            if isinstance(value, (int, float)):
                total -= value

    return total


def avg_function(args, table_id, get_cell_value):
    """Функция СРЗНАЧ - среднее значение"""
    if not args:
        return 0

    total = 0
    count = 0

    for arg in args:
        if isinstance(arg, (int, float)):
            total += arg
            count += 1
        else:
            value = get_cell_value(arg, table_id)
            if isinstance(value, (int, float)):
                total += value
                count += 1

    return total / count if count > 0 else 0


def min_function(args, table_id, get_cell_value):
    """Функция МИН - минимальное значение"""
    if not args:
        return 0

    min_val = None

    for arg in args:
        if isinstance(arg, (int, float)):
            val = arg
        else:
            val = get_cell_value(arg, table_id)
            if not isinstance(val, (int, float)):
                try:
                    val = float(val)
                except:
                    continue

        if min_val is None or val < min_val:
            min_val = val

    return min_val if min_val is not None else 0


def max_function(args, table_id, get_cell_value):
    """Функция МАКС - максимальное значение"""
    if not args:
        return 0

    max_val = None

    for arg in args:
        if isinstance(arg, (int, float)):
            val = arg
        else:
            val = get_cell_value(arg, table_id)
            if not isinstance(val, (int, float)):
                try:
                    val = float(val)
                except:
                    continue

        if max_val is None or val > max_val:
            max_val = val

    return max_val if max_val is not None else 0


def count_function(args, table_id, get_cell_value):
    """Функция СЧЁТ - количество числовых значений"""
    count = 0

    for arg in args:
        if isinstance(arg, (int, float)):
            count += 1
        else:
            value = get_cell_value(arg, table_id)
            if isinstance(value, (int, float)):
                count += 1

    return count


def if_empty(args, table_id, get_cell_value):
    """Функция ЕПУСТО - проверка ячейки на наличие значения"""
    return not not get_cell_value(args[0], table_id)


def get_basic_functions():
    """Возвращает словарь базовых функций"""
    return {
        'СУММ': sum_function,
        'РАЗН': razn_function,
        'СРЗНАЧ': avg_function,
        'МИН': min_function,
        'МАКС': max_function,
        'СЧЁТ': count_function,
        'ЕПУСТО': if_empty,
        # Английские названия для совместимости
        'SUM': sum_function,
        'AVG': avg_function,
        'AVERAGE': avg_function,
        'MIN': min_function,
        'MAX': max_function,
        'COUNT': count_function,
    }