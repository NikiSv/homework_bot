import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ApiRequestError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('P_TOKEN')
TELEGRAM_TOKEN = os.getenv('T_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('T_CHAT_ID')

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(name)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    if (
        PRACTICUM_TOKEN is None
        or TELEGRAM_TOKEN is None
        or TELEGRAM_CHAT_ID is None
    ):
        logger.critical("Отсутствие обязательных переменных окружения!")
        return False
    return True


def log_and_send_message(message):
    """Запись сообщения в лог и отправка через Telegram."""
    logging.error(message)
    send_message(telegram.Bot(token=TELEGRAM_TOKEN), message)


def send_message(bot, message):
    """Отправка сообщение в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f'Удачная отправка сообщения в Telegram: {message}')
    except Exception as e:
        logging.error(f'Ошибка при отправке сообщения в Telegram: {e}')


def get_api_answer(current_timestamp):
    """Запрос к единственному эндпоинту API-сервиса."""
    params = {'from_date': current_timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException():
        raise ApiRequestError()
    if response.status_code != 200:
        message = f'Ошибка при запросе к API: {response.status_code}'
        logging.error(message)
        raise ApiRequestError(message)
    if not response:
        logging.warning('Пустой ответ API')
    return response.json()


def check_response(response):
    """Проверка ответа API на соответствие документации из урока."""
    if not isinstance(response, dict):
        message = 'Получен список вместо ожидаемого словаря'
        log_and_send_message(message)
        raise TypeError()
    homeworks = response.get('homeworks')
    if not isinstance(response.get('homeworks'), list):
        message = 'Список homeworks отсутствует в ответе'
        log_and_send_message(message)
        raise TypeError()
    if not homeworks:
        logging.warning('Список homeworks пуст')
    return response.get("homeworks")


def parse_status(homework):
    """Извлекает из информации о домашней работе статус работы."""
    if 'homework_name' not in homework:
        message = 'В ответе API домашки нет ключа "homework_name"'
        log_and_send_message(message)
        raise KeyError()

    homework_name = homework['homework_name']
    try:
        homework_status = homework['status']
    except KeyError:
        message = f'Для работы "{homework_name}" не указан статус проверки.'
        log_and_send_message(message)
        raise ValueError()

    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if verdict is None:
        message = f'Статус проверки для работы "{homework_name}" неизвестен:'
        f'{homework_status}.'
        log_and_send_message(message)
        raise ValueError()
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if check_tokens():
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        current_timestamp = int(time.time())
        while True:
            try:
                response = get_api_answer(current_timestamp)
                check_response(response)
                homeworks = response['homeworks']
                for hw in homeworks:
                    message = parse_status(hw)
                    send_message(bot, message)
            except Exception as error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                logging.error(message)
            time.sleep(RETRY_PERIOD)
    else:
        SystemExit()


if __name__ == '__main__':
    main()
