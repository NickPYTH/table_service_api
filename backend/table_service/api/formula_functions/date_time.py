"""Функции даты и времени"""
import datetime
import re


def parse_date_from_cell(cell_value):
    """Парсит дату из значения ячейки в объект datetime"""
    if not cell_value:
        return None

    try:
        return datetime.datetime.strptime(str(cell_value), "%d.%m.%Y")
    except ValueError:
        try:
            return datetime.datetime.strptime(str(cell_value), "%d.%m.%Y %H:%M")
        except ValueError:
            try:
                # Пытаемся преобразовать из timestamp
                return datetime.datetime.fromtimestamp(float(cell_value))
            except (ValueError, TypeError):
                return None


def today_function(args, table_id, get_cell_value):
    """Функция СЕГОДНЯ - возвращает текущую дату в формате DD.MM.YYYY"""
    if len(args) > 0:
        raise ValueError("Функция СЕГОДНЯ не требует аргументов")
    today = datetime.datetime.now()
    return today.strftime("%d.%m.%Y")


def year_function(args, table_id, get_cell_value):
    """Функция ГОД"""
    if len(args) == 0:
        return float(datetime.datetime.now().year)
    elif len(args) == 1:
        arg = args[0]

        if isinstance(arg, (int, float)):
            try:
                date_obj = datetime.datetime.fromtimestamp(arg)
                return float(date_obj.year)
            except (ValueError, OSError):
                return 0
        elif isinstance(arg, str):
            raw_value = get_cell_value(arg, table_id, return_raw=True)
            if raw_value:
                date_obj = parse_date_from_cell(raw_value)
                if date_obj:
                    return float(date_obj.year)
            return 0
        else:
            return 0
    else:
        raise ValueError("Функция ГОД принимает 0 или 1 аргумент")


def difference_function(args, table_id, get_cell_value):
    """
    Функция РАЗНИЦА - вычисляет разницу между датами
    Формат: РАЗНИЦА(дата1; дата2; [единица_измерения])
    Единицы измерения: "d" - дни, "m" - месяцы, "y" - годы
    По умолчанию: "d" (дни)
    """
    if len(args) < 2 or len(args) > 3:
        raise ValueError("Функция РАЗНИЦА требует 2 или 3 аргумента")

    # Получаем даты
    date1_arg = args[0]
    date2_arg = args[1]

    # Получаем единицу измерения (по умолчанию "d" - дни)
    unit = args[2].lower() if len(args) == 3 else "d"

    # Преобразуем аргументы в datetime объекты
    def parse_date_argument(date_arg):
        """Преобразует аргумент в datetime"""
        if isinstance(date_arg, (int, float)):
            # Это timestamp
            return datetime.datetime.fromtimestamp(date_arg)
        elif isinstance(date_arg, str):
            # Это может быть ссылка на ячейку или строка даты
            if re.match(r'^[A-Z]+\d+$', date_arg, re.IGNORECASE):
                # Ссылка на ячейку
                cell_value = get_cell_value(date_arg, table_id, return_raw=True)
                if not cell_value:
                    raise ValueError(f"Ячейка {date_arg} пустая")

                # Пытаемся распарсить дату из значения ячейки
                return parse_date_from_cell(cell_value)
            else:
                # Строка даты
                return parse_date_from_string(date_arg)
        else:
            raise ValueError(f"Неверный тип аргумента даты: {type(date_arg)}")

    def parse_date_from_string(date_str):
        """Парсит дату из строки"""
        try:
            return datetime.datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            try:
                return datetime.datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            except ValueError:
                try:
                    # Пытаемся распарсить как timestamp строку
                    return datetime.datetime.fromtimestamp(float(date_str))
                except (ValueError, TypeError):
                    raise ValueError(f"Неверный формат даты: {date_str}")

    try:
        date1 = parse_date_argument(date1_arg)
        date2 = parse_date_argument(date2_arg)

        # Вычисляем разницу в зависимости от единицы измерения
        if unit == "d":  # Дни
            delta = date2 - date1
            return abs(float(delta.days))

        elif unit == "m":  # Месяцы
            # Более точный расчет месяцев
            months = (date2.year - date1.year) * 12 + (date2.month - date1.month)

            # Корректировка на дни
            #if date2.day < date1.day:
            #    months -= 1

            return abs(float(months))

        elif unit == "y":  # Годы
            years = date2.year - date1.year

            # Корректировка на месяцы и дни
            if (date2.month, date2.day) < (date1.month, date1.day):
                years -= 1

            return abs(float(years))

        else:
            raise ValueError(f"Неизвестная единица измерения: {unit}. Используйте 'd', 'm' или 'y'")

    except Exception as e:
        raise ValueError(f"Ошибка вычисления разницы: {str(e)}")


def today_timestamp_function(args, table_id, get_cell_value):
    """
    Вспомогательная функция для получения timestamp текущей даты
    Используется внутри формул
    """
    if len(args) > 0:
        raise ValueError("Функция СЕГОДНЯ не требует аргументов")

    today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return float(today.timestamp())


def get_datetime_functions():
    """Возвращает словарь функций даты и времени"""
    return {
        'СЕГОДНЯ': today_function,
        'СЕГОДНЯ_TS': today_timestamp_function,  # Для внутреннего использования
        'ГОД': year_function,
        'РАЗНИЦА': difference_function,
    }
