import datetime
import re

from tables.models import Cell, Row, Column, Table
# Импортируем функции из модулей
from .formula_functions.base import get_basic_functions
from .formula_functions.date_time import get_datetime_functions
from .formula_functions.logical import get_logical_functions
from .formula_functions.math import get_math_functions


def column_letters_to_number(letters):
    """Преобразует буквы столбца в число"""
    result = 0
    for char in letters.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result


def get_cell_value(cell_ref, table_id, return_raw=False):
    """Получает значение ячейки по ссылке"""
    try:
        cell_ref = cell_ref.upper()
        col_letters = re.match(r'([A-Z]+)(\d+)', cell_ref).group(1)
        row_num = int(re.match(r'([A-Z]+)(\d+)', cell_ref).group(2)) - 1

        col_num = column_letters_to_number(col_letters)
        table = Table.objects.get(id=table_id)

        cell_row = Row.objects.get(table=table, order=row_num)
        cell_column = Column.objects.get(table=table, order=col_num)
        cell = Cell.objects.filter(
            table_id=table_id,
            row=cell_row.id,
            column=cell_column.id
        ).first()

        if cell and cell.value:
            if return_raw:
                return str(cell.value)

            try:
                return float(cell.value)
            except (ValueError, TypeError):
                try:
                    return float(datetime.datetime.strptime(cell.value, "%d.%m.%Y").timestamp())
                except (ValueError, TypeError):
                    try:
                        return float(datetime.datetime.strptime(cell.value, "%d.%m.%Y %H:%M").timestamp())
                    except (ValueError, TypeError):
                        if str(cell.value).startswith('='):
                            return cell.formula_value
                        return str(cell.value)
        return 0 if not return_raw else ""
    except Exception as e:
        print(f"Ошибка получения ячейки {cell_ref}: {e}")
        return 0 if not return_raw else ""


def parse_string_literal(token):
    """Парсит строковый литерал"""
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    return token


def evaluate_comparison(left, operator, right):
    """Вычисляет результат сравнения"""
    if isinstance(left, str) or isinstance(right, str):
        left_str = str(left).lower() if isinstance(left, (int, float)) else str(left)
        right_str = str(right).lower() if isinstance(right, (int, float)) else str(right)

        if operator == '=':
            return left_str == right_str
        elif operator == '<>':
            return left_str != right_str
        elif operator == '>':
            return left_str > right_str
        elif operator == '<':
            return left_str < right_str
        elif operator == '>=':
            return left_str >= right_str
        elif operator == '<=':
            return left_str <= right_str
    else:
        if operator == '>':
            return left > right
        elif operator == '<':
            return left < right
        elif operator == '>=':
            return left >= right
        elif operator == '<=':
            return left <= right
        elif operator == '=':
            return abs(left - right) < 1e-10
        elif operator == '<>':
            return abs(left - right) > 1e-10

    raise ValueError(f"Неизвестный оператор сравнения: {operator}")


# Регистрация всех функций
FUNCTIONS = {}
FUNCTIONS.update(get_basic_functions())
FUNCTIONS.update(get_logical_functions())
FUNCTIONS.update(get_datetime_functions())
FUNCTIONS.update(get_math_functions())
FUNCTIONS.update(get_datetime_functions())


def evaluate_function(func_name, arguments, table_id):
    """Вычисляет значение функции"""
    func_name = func_name.upper()

    if func_name in FUNCTIONS:
        return FUNCTIONS[func_name](arguments, table_id, get_cell_value)
    else:
        raise ValueError(f"Неизвестная функция: {func_name}")


def evaluate_expression(tokens, table_id):
    """Рекурсивно вычисляет выражение с поддержкой вложенных функций"""
    print(f"evaluate_expression: tokens={tokens}")

    if not tokens:
        return ""

    # Если выражение в скобках
    if len(tokens) >= 2 and tokens[0] == '(' and tokens[-1] == ')':
        # Проверяем, что это действительно парные скобки
        inner_tokens = tokens[1:-1]
        return evaluate_expression(inner_tokens, table_id)

    # Функция для проверки, находится ли оператор на верхнем уровне
    def find_top_level_operator(tokens, operators):
        """Находит позицию оператора на верхнем уровне (depth=0)"""
        depth = 0
        for i, token in enumerate(tokens):
            if token == '(':
                depth += 1
            elif token == ')':
                depth -= 1
            elif token.endswith('(') and re.match(r'^[A-ZА-Я]{2,}\($', token, re.IGNORECASE):
                depth += 1

            if depth == 0 and token in operators:
                return i, token
        return -1, None

    # Проверяем арифметические операторы с учетом приоритетов
    # Сначала * и /
    op_pos, op = find_top_level_operator(tokens, ['*', '/'])
    if op_pos != -1:
        left_tokens = tokens[:op_pos]
        right_tokens = tokens[op_pos + 1:]

        left_value = evaluate_expression(left_tokens, table_id)
        right_value = evaluate_expression(right_tokens, table_id)

        # Преобразуем в числа если нужно
        if not isinstance(left_value, (int, float)):
            try:
                left_value = float(left_value)
            except:
                left_value = 0

        if not isinstance(right_value, (int, float)):
            try:
                right_value = float(right_value)
            except:
                right_value = 0

        if op == '*':
            result = left_value * right_value
        else:  # '/'
            result = round(left_value / right_value, 1) if right_value != 0 else 0

        print(f"Арифметика {op}: {left_value} {op} {right_value} -> {result}")
        return result

    # Затем + и -
    op_pos, op = find_top_level_operator(tokens, ['+', '-'])
    if op_pos != -1:
        left_tokens = tokens[:op_pos]
        right_tokens = tokens[op_pos + 1:]

        left_value = evaluate_expression(left_tokens, table_id)
        right_value = evaluate_expression(right_tokens, table_id)

        # Для сложения проверяем типы
        if op == '+':
            try:
                left_value = float(left_value)
                right_value = float(right_value)
                result = left_value + right_value
            except:
                if isinstance(left_value, str) or isinstance(right_value, str):
                    result = str(left_value) + str(right_value)
                else:
                    # Преобразуем в числа если нужно
                    if not isinstance(left_value, (int, float)):
                        try:
                            left_value = float(left_value)
                        except:
                            left_value = 0

                    if not isinstance(right_value, (int, float)):
                        try:
                            right_value = float(right_value)
                        except:
                            right_value = 0

                    result = left_value + right_value
        else:  # '-'
            # Для вычитания всегда числа
            if not isinstance(left_value, (int, float)):
                try:
                    left_value = float(left_value)
                except:
                    left_value = 0

            if not isinstance(right_value, (int, float)):
                try:
                    right_value = float(right_value)
                except:
                    right_value = 0

            result = left_value - right_value

        print(f"Арифметика {op}: {left_value} {op} {right_value} -> {result}")
        return result

    # Проверяем логические операторы на верхнем уровне
    # Сначала && (высший приоритет)
    op_pos, op = find_top_level_operator(tokens, ['&&'])
    if op_pos != -1:
        left_tokens = tokens[:op_pos]
        right_tokens = tokens[op_pos + 1:]

        left_value = evaluate_expression(left_tokens, table_id)
        right_value = evaluate_expression(right_tokens, table_id)

        left_bool = convert_to_bool(left_value)
        right_bool = convert_to_bool(right_value)

        result = left_bool and right_bool
        print(f"Логическое И (&&): {left_value} && {right_value} -> {result}")
        return result

    # Затем || (низший приоритет)
    op_pos, op = find_top_level_operator(tokens, ['||'])
    if op_pos != -1:
        left_tokens = tokens[:op_pos]
        right_tokens = tokens[op_pos + 1:]

        left_value = evaluate_expression(left_tokens, table_id)
        right_value = evaluate_expression(right_tokens, table_id)

        left_bool = convert_to_bool(left_value)
        right_bool = convert_to_bool(right_value)

        result = left_bool or right_bool
        print(f"Логическое ИЛИ (||): {left_value} || {right_value} -> {result}")
        return result

    # Проверяем операторы сравнения на верхнем уровне
    op_pos, op = find_top_level_operator(tokens, ['>', '<', '>=', '<=', '=', '<>'])
    if op_pos != -1:
        left_tokens = tokens[:op_pos]
        right_tokens = tokens[op_pos + 1:]

        left_value = evaluate_expression(left_tokens, table_id)
        right_value = evaluate_expression(right_tokens, table_id)

        print(f"Сравнение: {left_value} {op} {right_value}")
        result = evaluate_comparison(left_value, op, right_value)
        print(f"Результат сравнения: {result}")
        return result

    # Если это один токен
    if len(tokens) == 1:
        token = tokens[0]
        return evaluate_single_token(token, table_id)

    # Если первый токен - функция
    if len(tokens) >= 1 and re.match(r'^[A-ZА-Я]{2,}\($', tokens[0], re.IGNORECASE):
        func_token = tokens[0]
        func_name = func_token[:-1]

        # Находим конец этой функции
        depth = 1
        i = 1

        while i < len(tokens) and depth > 0:
            token = tokens[i]

            if token.endswith('(') and re.match(r'^[A-ZА-Я]{2,}\($', token, re.IGNORECASE):
                depth += 1
            elif token == '(':
                depth += 1
            elif token == ')':
                depth -= 1

            i += 1

        # Если это вся выражение - обрабатываем как функцию
        if i >= len(tokens):
            func_parts = tokens
            full_func_str = ''.join(func_parts)
            print(f"Полная функция {func_name}: {full_func_str}")

            args_start = full_func_str.find('(') + 1
            args_end = full_func_str.rfind(')')
            args_str = full_func_str[args_start:args_end]

            args_tokens = tokenize_expression(args_str)
            print(f"Функция {func_name}, аргументы токены: {args_tokens}")

            if func_name.upper() == 'ЕСЛИМН':
                return evaluate_ifmn_function(args_tokens, table_id)

            # Разбираем аргументы для других функций
            arguments = []
            current_arg_tokens = []
            current_depth = 0

            for token in args_tokens:
                if token.endswith('(') and re.match(r'^[A-ZА-Я]{2,}\($', token, re.IGNORECASE):
                    current_depth += 1
                    current_arg_tokens.append(token)
                elif token == '(':
                    current_depth += 1
                    current_arg_tokens.append(token)
                elif token == ')':
                    current_depth -= 1
                    current_arg_tokens.append(token)
                    if current_depth == 0:
                        pass
                elif token == ';' and current_depth == 0:
                    if current_arg_tokens:
                        arg_value = evaluate_expression(current_arg_tokens, table_id)
                        arguments.append(arg_value)
                        current_arg_tokens = []
                else:
                    current_arg_tokens.append(token)

            if current_arg_tokens:
                arg_value = evaluate_expression(current_arg_tokens, table_id)
                arguments.append(arg_value)

            print(f"Функция {func_name}, вычисленные аргументы: {arguments}")

            if func_name.upper() in FUNCTIONS:
                result = FUNCTIONS[func_name.upper()](arguments, table_id, get_cell_value)
            else:
                result = evaluate_function(func_name, arguments, table_id)

            print(f"Результат функции {func_name}: {result}")
            return result

    # Если дошли сюда, значит это выражение, которое не было обработано выше
    if tokens:
        # Для простых случаев типа "a1" или "123"
        return evaluate_single_token(tokens[0], table_id)

    return ""


def convert_to_bool(value):
    """Преобразует значение в булево"""
    if isinstance(value, bool):
        return value
    elif isinstance(value, (int, float)):
        return value != 0
    elif isinstance(value, str):
        return value.lower() not in ['false', '0', 'нет', 'no', '', 'ложь']
    else:
        return bool(value)


def evaluate_single_token(token, table_id):
    """Вычисляет значение одиночного токена"""
    if token.startswith('"') and token.endswith('"'):
        return parse_string_literal(token)
    elif token.isdigit() or (token.replace('.', '', 1).isdigit() and token.count('.') <= 1):
        return float(token)
    elif re.match(r'^[A-Z]+\d+$', token, re.IGNORECASE):
        return get_cell_value(token, table_id)
    else:
        return token


def evaluate_ifmn_function(args_tokens, table_id):
    """Специальная обработка для функции ЕСЛИМН"""
    print(f"evaluate_ifmn_function: args_tokens={args_tokens}")

    arguments = []
    current_arg_tokens = []
    current_depth = 0

    for token in args_tokens:
        if token.endswith('(') and re.match(r'^[A-ZА-Я]{2,}\($', token, re.IGNORECASE):
            current_depth += 1
            current_arg_tokens.append(token)
        elif token == '(':
            current_depth += 1
            current_arg_tokens.append(token)
        elif token == ')':
            current_depth -= 1
            current_arg_tokens.append(token)
            if current_depth == 0:
                # Закрыли вложенную функцию
                pass
        elif token == ';' and current_depth == 0:
            if current_arg_tokens:
                # Используем evaluate_expression для вычисления сложных выражений
                arg_value = evaluate_expression(current_arg_tokens, table_id)
                arguments.append(arg_value)
                current_arg_tokens = []
        else:
            current_arg_tokens.append(token)

    # Последний аргумент
    if current_arg_tokens:
        arg_value = evaluate_expression(current_arg_tokens, table_id)
        arguments.append(arg_value)

    print(f"evaluate_ifmn_function: вычисленные аргументы={arguments}")

    # Вычисляем функцию ЕСЛИМН
    if 'ЕСЛИМН' in FUNCTIONS:
        result = FUNCTIONS['ЕСЛИМН'](arguments, table_id, get_cell_value)
        print(f"evaluate_ifmn_function: результат={result}")
        return result
    else:
        raise ValueError("Функция ЕСЛИМН не найдена")


def tokenize_expression(expression):
    """Разбирает выражение на токены"""
    tokens = []
    i = 0
    n = len(expression)

    while i < n:
        if expression[i].isspace():
            i += 1
            continue

        # Строки в кавычках
        if expression[i] == '"':
            j = i + 1
            while j < n and expression[j] != '"':
                j += 1
            if j < n:
                tokens.append(expression[i:j + 1])
                i = j + 1
                continue

        # Логические операторы && и ||
        if i + 1 < n:
            two_char_op = expression[i:i + 2]
            if two_char_op in ['&&', '||']:
                tokens.append(two_char_op)
                i += 2
                continue

        # Операторы сравнения
        if i + 1 < n:
            two_char_op = expression[i:i + 2]
            if two_char_op in ['>=', '<=', '<>']:
                tokens.append(two_char_op)
                i += 2
                continue

        # Функции
        if expression[i].isalpha() or expression[
            i] in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя':
            j = i
            while j < n and (expression[j].isalpha() or expression[
                j] in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'):
                j += 1
            if j < n and expression[j] == '(':
                tokens.append(expression[i:j + 1])
                i = j + 1
                continue

        # Одиночные операторы и символы
        if expression[i] in '><=+-*/();':
            tokens.append(expression[i])
            i += 1
            continue

        # Ячейки
        if expression[i].isalpha():
            j = i
            while j < n and expression[j].isalpha():
                j += 1
            while j < n and expression[j].isdigit():
                j += 1
            if j > i:
                tokens.append(expression[i:j])
                i = j
                continue

        # Числа
        if expression[i].isdigit():
            j = i
            while j < n and expression[j].isdigit():
                j += 1
            if j < n and expression[j] == '.':
                j += 1
                while j < n and expression[j].isdigit():
                    j += 1
            tokens.append(expression[i:j])
            i = j
            continue

        i += 1

    return tokens


def calculate_formula(cell, enable_save=True):
    """Основная функция вычисления формулы"""
    FUNCTIONS.update(get_logical_functions(evaluate_expression))
    try:
        formula = cell.value.strip()

        if not formula.upper().startswith('='):
            cell.formula_value = "Ошибка: формула должна начинаться с ="
            cell.save()
            return

        formula_content = formula[1:]

        # Убираем пробелы вне кавычек
        formula_content_no_spaces = ''
        in_quotes = False
        for char in formula_content:
            if char == '"':
                in_quotes = not in_quotes
                formula_content_no_spaces += char
            elif char.isspace() and not in_quotes:
                continue
            else:
                formula_content_no_spaces += char

        tokens = tokenize_expression(formula_content_no_spaces)

        if not tokens:
            cell.formula_value = "Ошибка: неверный формат формулы"
            cell.save()
            return

        try:
            result = evaluate_expression(tokens, cell.table_id)

            # Форматируем результат
            if isinstance(result, bool):
                cell.formula_value = "ИСТИНА" if result else "ЛОЖЬ"
            elif isinstance(result, (int, float)):
                if isinstance(result, float) and result.is_integer():
                    cell.formula_value = str(int(result))
                else:
                    cell.formula_value = str(round(result, 4))
            elif isinstance(result, str):
                cell.formula_value = result
            else:
                cell.formula_value = str(result)

        except ValueError as e:
            cell.formula_value = f"Ошибка: {str(e)}"
        except Exception as e:
            cell.formula_value = f"Ошибка вычисления: {str(e)}"

        if enable_save:
            cell.save()

    except Exception as e:
        print(f"Ошибка при вычислении формулы: {e}")
        cell.formula_value = "Ошибка вычисления"
        cell.save()