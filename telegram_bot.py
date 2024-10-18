import logging
import re
import sqlite3
from datetime import datetime

import pytz
import swisseph as swe
from geopy.geocoders import Nominatim
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)
from timezonefinder import TimezoneFinder

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = '7797416253:AAE17Y-ckKcEkvZCru-JGgl9J1eNkns0xac'
user_data = {}


def get_coordinates(city_name: str) -> tuple[float, float]:
    """
        Get the latitude and longitude of a city using the Nominatim geolocation API.

        Args:
            city_name (str): The name of the city to retrieve coordinates for.

        Returns:
            tuple[float, float]: The latitude and longitude of the city.

        Raises:
            ValueError: If the city cannot be found by the geolocation service.
        """
    geolocator = Nominatim(user_agent="telegram-astro-bot")
    location = geolocator.geocode(city_name)
    if location:
        return location.latitude, location.longitude
    else:
        raise ValueError("Внучка, к сожалению, бабуля не нашла такого города на карте. Введи, пожалуйста, существующий город")


def get_timezone(latitude: float, longitude: float) -> str:
    """
    Determine the timezone based on latitude and longitude using TimezoneFinder.

    Args:
        latitude (float): The latitude of the location.
        longitude (float): The longitude of the location.

    Returns:
        str: The timezone identifier (e.g., 'Europe/Moscow') for the location.

    Raises:
        ValueError: If the timezone cannot be determined for the given coordinates.
    """
    tf = TimezoneFinder()
    return tf.timezone_at(lat=latitude, lng=longitude)


def get_zodiac_sign(degree: float) -> str:
    """
    Determine the zodiac sign based on the degree within the ecliptic.

    Args:
        degree (float): The degree of the planet's position along the ecliptic (0-360 degrees).

    Returns:
        str: The name of the zodiac sign corresponding to the degree.
    """
    signs = [
        "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
        "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"
    ]
    return signs[int(degree // 30)]


def get_planet_description(planet: str, zodiac_sign: str) -> str:
    """
    Retrieve the description of a planet in a given zodiac sign from the database.

    Args:
        planet (str): The name of the planet (e.g., 'Солнце', 'Луна').
        zodiac_sign (str): The name of the zodiac sign (e.g., 'Овен', 'Телец').

    Returns:
        str: A description of the planet in that zodiac sign.

    Raises:
        sqlite3.Error: If there is an issue querying the database.
    """

    conn = sqlite3.connect('zodiac.db')
    cursor = conn.cursor()

    cursor.execute(f"SELECT description FROM {planet} WHERE zodiac_sign = ?", (zodiac_sign,))
    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]
    else:
        return "Описание не найдено"


def validate_date(date_str: str) -> datetime:
    """
    Validate the date string provided by the user. Ensures the date is in the correct format and not in the future.

    Args:
        date_str (str): The birthdate as a string in the format 'DD.MM.YYYY'.

    Returns:
        datetime: The validated date as a datetime object.

    Raises:
        ValueError: If the date is incorrectly formatted or if the year is beyond 2024.
    """
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
        if date.year > 2024:
            raise ValueError("Внучка, дата некорректна. Такой год еще не наступил")
        return date
    except ValueError:
        raise ValueError("Внучка, дата некорректна. Пожалуйста, введи ее в формате ДД.ММ.ГГГГ")


def validate_time(time_str: str) -> tuple[int, int]:
    """
    Validate the time string provided by the user. Ensures the time is in the correct format and is a valid time.

    Args:
        time_str (str): The birth time as a string in the format 'HH:MM'.

    Returns:
        tuple[int, int]: A tuple containing the hours and minutes as integers.

    Raises:
        ValueError: If the time is incorrectly formatted or contains invalid hours or minutes.
    """
    if re.match(r"^[0-2][0-9]:[0-5][0-9]$", time_str):
        hours, minutes = map(int, time_str.split(":"))
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return hours, minutes
    raise ValueError("Внучка, время некорректно. Пожалуйста, введи его в формате ЧЧ:ММ (например, 14:30)")


def calculate_planet_positions(year: int, month: int, day: int, hour: int, minute: int, latitude: float, longitude: float
) -> dict:
    """
    Calculate the positions of the planets in the zodiac for a given date and location.

    Args:
        year (int): The birth year.
        month (int): The birth month.
        day (int): The birt date.
        hour (int): The birth hour.
        minute (int): The birth minute.
        latitude (float): The latitude of the birthplace.
        longitude (float): The longitude of the birthplace.

    Returns:
        dict: A dictionary containing the degree, zodiac sign, and description of each planet's position.
    """
    date_str = f"{year}-{month}-{day} {hour}:{minute}:00"
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

    julian_day = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60)
    swe.set_topo(longitude, latitude, 0)

    planets = ["Солнце", "Луна", "Меркурий", "Венера", "Марс", "Юпитер", "Сатурн", "Уран", "Нептун", "Плутон"]
    planet_positions = {}

    for planet_index, planet_name in enumerate(planets):
        planet_position, ret_flag = swe.calc_ut(julian_day, planet_index)
        degree = planet_position[0]
        zodiac_sign = get_zodiac_sign(degree)

        description = get_planet_description(planet_name, zodiac_sign)
        planet_positions[planet_name] = {
            "degree": degree,
            "zodiac_sign": zodiac_sign,
            "description": description
        }

    return planet_positions


def calculate_ascendant(year: int, month: int, day: int, hour: int, minute: int, latitude: float, longitude: float
                        ) -> tuple[float, str]:
    """
    Calculate the degree and zodiac sign of the ascendant (rising sign) for a given date and location.

    Args:
        year (int): The birth year.
        month (int): The birth month.
        day (int): The birthdate.
        hour (int): The birth hour.
        minute (int): The birth minute.
        latitude (float): The latitude of the birthplace.
        longitude (float): The longitude of the birthplace.

    Returns:
        tuple[float, str]: The degree of the ascendant and its corresponding zodiac sign.
    """

    timezone_str = get_timezone(latitude, longitude)
    if timezone_str is None:
        raise ValueError("Невозможно определить часовой пояс для указанных координат.")

    local_tz = pytz.timezone(timezone_str)
    local_dt = local_tz.localize(datetime(year, month, day, hour, minute))

    utc_dt = local_dt.astimezone(pytz.utc)

    julian_day = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                            utc_dt.hour + utc_dt.minute / 60.0)

    houses, ascmc = swe.houses(julian_day, latitude, longitude, b'P')

    ascendant_degree = ascmc[0]
    ascendant_sign = get_zodiac_sign(ascendant_degree)

    return ascendant_degree, ascendant_sign


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handler for the /start command. Sends a greeting message to the user.

        Args:
            update (Update): The incoming update from Telegram.
            context (ContextTypes.DEFAULT_TYPE): The context of the current conversation.
    """

    await update.message.reply_text('Привет, внучка! \n'
                                    'Меня зовут АстроБабуля. Я — чат-бот, который поможет тебе рассчитать твою натальную карту.\n\n'
                                    'Чтобы начать, просто нажми на /next')


async def next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handler for the /next command. Asks the user to input their birthdate.

        Args:
            update (Update): The incoming update from Telegram.
            context (ContextTypes.DEFAULT_TYPE): The context of the current conversation.
        """

    await update.message.reply_text('Введи дату своего рождения в формате ДД.ММ.ГГГГ:')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handle user messages for collecting birthdate, time, and place, and calculate the natal chart.

        Args:
            update (Update): The incoming update from Telegram.
            context (ContextTypes.DEFAULT_TYPE): The context of the current conversation.

        Raises:
            ValueError: If the user provides invalid input for date, time, or location.
    """

    try:
        if 'birth_date' not in context.user_data:
            birth_date = update.message.text
            valid_date = validate_date(birth_date)
            context.user_data['birth_date'] = valid_date
            await update.message.reply_text('Введи время рождения в формате ЧЧ:ММ:')

        elif 'birth_time' not in context.user_data:
            birth_time = update.message.text
            hour, minute = validate_time(birth_time)
            context.user_data['birth_time'] = (hour, minute)
            await update.message.reply_text('Введи место рождения (город):')

        elif 'birth_place' not in context.user_data:
            birth_place = update.message.text
            latitude, longitude = get_coordinates(birth_place)
            context.user_data['birth_place'] = (latitude, longitude)

            birth_date = context.user_data['birth_date']
            hour, minute = context.user_data['birth_time']
            latitude, longitude = context.user_data['birth_place']
            planets = calculate_planet_positions(birth_date.year, birth_date.month, birth_date.day, hour, minute,
                                                 latitude, longitude)

            ascendant_degree, ascendant_sign = calculate_ascendant(birth_date.year, birth_date.month, birth_date.day,
                                                                   hour, minute, latitude, longitude)

            context.user_data['nat_chart'] = planets
            context.user_data['ascendant'] = {"degree": ascendant_degree, "zodiac_sign": ascendant_sign,
                                              "description": get_planet_description('Асцендент', ascendant_sign)}

            buttons = [
                [InlineKeyboardButton("Солнце", callback_data='Солнце'),
                 InlineKeyboardButton("Луна", callback_data='Луна')],
                [InlineKeyboardButton("Меркурий", callback_data='Меркурий'),
                 InlineKeyboardButton("Венера", callback_data='Венера')],
                [InlineKeyboardButton("Марс", callback_data='Марс'),
                 InlineKeyboardButton("Юпитер", callback_data='Юпитер')],
                [InlineKeyboardButton("Сатурн", callback_data='Сатурн'),
                 InlineKeyboardButton("Уран", callback_data='Уран')],
                [InlineKeyboardButton("Нептун", callback_data='Нептун'),
                 InlineKeyboardButton("Плутон", callback_data='Плутон')],
                [InlineKeyboardButton("Асцендент", callback_data='Асцендент')],
                [InlineKeyboardButton("Рассчитать новую натальную карту", callback_data='new_chart')]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            await update.message.reply_text("Молодец! Бабуля составила твою натальную карту. "
                                            "Теперь выбери, о каком из положений тебе хотелось бы узнать:",
                                            reply_markup=reply_markup)

    except ValueError as e:
        await update.message.reply_text(str(e))


async def send_planet_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Send an inline keyboard with buttons for each planet and the ascendant, allowing the user to view their descriptions.

        Args:
            update (Update): The incoming update from Telegram.
            context (ContextTypes.DEFAULT_TYPE): The context of the current conversation.
    """

    buttons = [
        [InlineKeyboardButton("Солнце", callback_data='Солнце'),
         InlineKeyboardButton("Луна", callback_data='Луна')],
        [InlineKeyboardButton("Меркурий", callback_data='Меркурий'),
         InlineKeyboardButton("Венера", callback_data='Венера')],
        [InlineKeyboardButton("Марс", callback_data='Марс'),
         InlineKeyboardButton("Юпитер", callback_data='Юпитер')],
        [InlineKeyboardButton("Сатурн", callback_data='Сатурн'),
         InlineKeyboardButton("Уран", callback_data='Уран')],
        [InlineKeyboardButton("Нептун", callback_data='Нептун'),
         InlineKeyboardButton("Плутон", callback_data='Плутон')],
        [InlineKeyboardButton("Асцендент", callback_data='Асцендент')],
        [InlineKeyboardButton("Рассчитать новую натальную карту", callback_data='new_chart')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.callback_query.message.edit_reply_markup(reply_markup=reply_markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handle the callback when a user presses one of the planet buttons. Respond with the description of the planet or ascendant.

        Args:
            update (Update): The incoming update from Telegram (callback query).
            context (ContextTypes.DEFAULT_TYPE): The context of the current conversation.
    """

    query = update.callback_query
    await query.answer()

    if query.data == 'new_chart':
        await query.message.reply_text('Введи дату своего рождения в формате ДД.ММ.ГГГГ:')
        context.user_data.clear()
    else:
        if query.data == 'Асцендент':
            ascendant = context.user_data['ascendant']
            response = f"Асцендент: {ascendant['degree']:.2f}° в знаке {ascendant['zodiac_sign']}\nОписание: {ascendant['description']}"
        else:
            planet = context.user_data['nat_chart'][query.data]
            response = f"{query.data}: {planet['degree']:.2f}° в знаке {planet['zodiac_sign']}\nОписание: {planet['description']}"

        await query.edit_message_text(response)
        await send_planet_buttons(update, context)


def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    application.add_handler(CommandHandler("next", next))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.run_polling()


if __name__ == '__main__':
    main()
