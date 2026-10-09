"""Математические функции формул"""


def average_function(args, table_id, get_cell_value):
    """Функция СРЗНАЧ"""
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


def max_function(args, table_id, get_cell_value):
    """Функция МАКС"""
    values = []
    for arg in args:
        if isinstance(arg, (int, float)):
            values.append(arg)
        else:
            value = get_cell_value(arg, table_id)
            if isinstance(value, (int, float)):
                values.append(value)

    return max(values) if values else 0


def min_function(args, table_id, get_cell_value):
    """Функция МИН"""
    values = []
    for arg in args:
        if isinstance(arg, (int, float)):
            values.append(arg)
        else:
            value = get_cell_value(arg, table_id)
            if isinstance(value, (int, float)):
                values.append(value)

    return min(values) if values else 0


def get_math_functions():
    """Возвращает словарь математических функций"""
    return {
        'СРЗНАЧ': average_function,
        'МАКС': max_function,
        'МИН': min_function,
    }