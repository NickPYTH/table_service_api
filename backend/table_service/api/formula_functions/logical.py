"""Логические функции формул"""
import re
import datetime

def evaluate_condition(condition_arg, table_id, get_cell_value, evaluate_expression):
    """
    Универсальная функция оценки условия
    """
    # Если условие - строка с логическим выражением
    if isinstance(condition_arg, str):
        # Проверяем, содержит ли условие логические операторы
        if '&&' in condition_arg or '||' in condition_arg:
            if evaluate_expression is None:
                raise ValueError("Для сложных условий требуется evaluate_expression")

            # Токенизируем и вычисляем логическое выражение
            from ..formula_parser import tokenize_expression
            condition_tokens = tokenize_expression(condition_arg.replace(' ', ''))
            return evaluate_logical_condition(condition_tokens, table_id, evaluate_expression)
        else:
            # Простая строка
            return condition_arg.lower() not in ['false', '0', 'нет', 'no', '']

    # Если условие уже вычислено
    if isinstance(condition_arg, bool):
        return condition_arg
    elif isinstance(condition_arg, (int, float)):
        return condition_arg != 0
    else:
        return bool(condition_arg)


def evaluate_logical_condition(condition_tokens, table_id, evaluate_expression):
    """
    Вычисляет сложное логическое условие с операторами && и ||
    Правильная обработка с учетом приоритета && перед ||
    """

    # Преобразуем токены в список значений и операторов
    stack = []

    i = 0
    while i < len(condition_tokens):
        token = condition_tokens[i]

        if token in ['&&', '||']:
            stack.append(token)
            i += 1
            continue

        # Собираем подвыражение до следующего оператора
        j = i
        while j < len(condition_tokens) and condition_tokens[j] not in ['&&', '||']:
            j += 1

        sub_expr = condition_tokens[i:j]
        if sub_expr:
            # Вычисляем подвыражение
            result = evaluate_expression(sub_expr, table_id)

            # Преобразуем в булево значение
            if isinstance(result, bool):
                bool_result = result
            elif isinstance(result, (int, float)):
                bool_result = result != 0
            elif isinstance(result, str):
                bool_result = result.lower() not in ['false', '0', 'нет', 'no', '']
            else:
                bool_result = bool(result)

            stack.append(bool_result)

        i = j

    # Вычисляем выражение с учетом приоритета && перед ||
    # Сначала обрабатываем все &&
    i = 0
    while i < len(stack):
        if isinstance(stack[i], str) and stack[i] == '&&':
            if i > 0 and i + 1 < len(stack):
                left = stack[i - 1]
                right = stack[i + 1]

                # Проверяем, что left и right - булевы значения
                left_bool = left if isinstance(left, bool) else bool(left)
                right_bool = right if isinstance(right, bool) else bool(right)

                result = left_bool and right_bool

                # Заменяем три элемента на результат
                stack[i - 1] = result
                del stack[i:i + 2]  # Удаляем оператор и правый операнд
                i -= 1  # Возвращаемся назад, так как массив изменился
        i += 1

    # Затем обрабатываем все ||
    i = 0
    while i < len(stack):
        if isinstance(stack[i], str) and stack[i] == '||':
            if i > 0 and i + 1 < len(stack):
                left = stack[i - 1]
                right = stack[i + 1]

                left_bool = left if isinstance(left, bool) else bool(left)
                right_bool = right if isinstance(right, bool) else bool(right)

                result = left_bool or right_bool

                stack[i - 1] = result
                del stack[i:i + 2]
                i -= 1
        i += 1

    # В стеке должен остаться один булев результат
    if len(stack) == 1:
        result = stack[0]
        return result if isinstance(result, bool) else bool(result)

    return False


def if_function(args, table_id, get_cell_value, evaluate_expression=None):
    """Функция ЕСЛИ"""
    if len(args) != 3:
        raise ValueError(f"Функция ЕСЛИ требует 3 аргумента, получено {len(args)}")

    condition, true_value, false_value = args

    # Проверяем условие
    condition_result = evaluate_condition(condition, table_id, get_cell_value, evaluate_expression)

    return true_value if condition_result else false_value


def ifs_function(args, table_id, get_cell_value, evaluate_expression=None):
    """
    Функция ЕСЛИМН (множественное условие)
    Формат: ЕСЛИМН(условие1; результат1; условие2; результат2; ...; [значение_по_умолчанию])
    """
    print(f"ifs_function called with {len(args)} args: {args}")

    if len(args) < 2:
        raise ValueError("Функция ЕСЛИМН требует минимум 2 аргумента")

    # Проверяем четное или нечетное количество аргументов
    is_odd_count = len(args) % 2 == 1

    # Количество пар условие-результат
    pair_count = len(args) // 2

    # Обрабатываем пары условие-результат
    for i in range(0, pair_count * 2, 2):
        condition_arg = args[i]
        true_value = args[i + 1]

        print(f"Проверка пары {i//2}: условие={condition_arg}, результат={true_value}")

        # Проверяем условие
        condition_result = evaluate_condition(condition_arg, table_id, get_cell_value, evaluate_expression)

        print(f"Результат условия: {condition_result}")

        if condition_result:
            print(f"Условие истинно, возвращаем: {true_value}")
            return true_value

    # Если ни одно условие не сработало
    if is_odd_count:
        # Возвращаем последний аргумент как значение по умолчанию
        default_value = args[-1]
        print(f"Все условия ложны, возвращаем значение по умолчанию: {default_value}")
        return default_value
    else:
        print("Все условия ложны, нет значения по умолчанию, возвращаем пустую строку")
        return ""


def and_function(args, table_id, get_cell_value):
    """Функция И (логическое И)"""
    if not args:
        return False

    for arg in args:
        if isinstance(arg, bool):
            if not arg:
                return False
        elif isinstance(arg, (int, float)):
            if arg == 0:
                return False
        elif isinstance(arg, str):
            if arg.lower() in ['false', '0', 'нет', 'no', '']:
                return False
        elif not arg:
            return False

    return True


def or_function(args, table_id, get_cell_value):
    """Функция ИЛИ (логическое ИЛИ)"""
    if not args:
        return False

    for arg in args:
        if isinstance(arg, bool):
            if arg:
                return True
        elif isinstance(arg, (int, float)):
            if arg != 0:
                return True
        elif isinstance(arg, str):
            if arg.lower() not in ['false', '0', 'нет', 'no', '']:
                return True
        elif arg:
            return True

    return False


def get_logical_functions(evaluate_expression_func=None):
    """Возвращает словарь логических функций"""
    def wrapped_if_function(args, table_id, get_cell_value):
        return if_function(args, table_id, get_cell_value, evaluate_expression_func)

    def wrapped_ifs_function(args, table_id, get_cell_value):
        return ifs_function(args, table_id, get_cell_value, evaluate_expression_func)

    return {
        'ЕСЛИ': wrapped_if_function,
        'ЕСЛИМН': wrapped_ifs_function,
        'И': and_function,
        'ИЛИ': or_function,
    }