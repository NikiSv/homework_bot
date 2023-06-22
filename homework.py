import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv
from unittest import TestCase, mock, main as uni_main

import telegram
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
        message = 'Что что-то пошло не так при выполнении запроса :('
        log_and_send_message(message)
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
    if not isinstance(response.get('homeworks'), list):
        message = 'Список homeworks отсутствует в ответе'
        log_and_send_message(message)
        raise TypeError()
    if not response.get('homeworks'):
        logging.warning('Список homeworks пуст')
    return response.get("homeworks")


def parse_status(homework):
    """Извлекает из информации о домашней работе статус работы."""
    if 'homework_name' not in homework:
        message = 'В ответе API домашки нет ключа "homework_name"'
        log_and_send_message(message)
        raise KeyError()

    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
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
    ReqEx = requests.RequestException
    resp = mock.Mock()

    main()

    class TestReq(TestCase):
        """Тестирование работы сервера."""

        @mock.patch('requests.get')
        def test_network_error(self, rq_get):
            """Проверка сбоя сети."""
            rq_get.side_effect = resp(side_effect=ReqEx('testing'))
            main()

        @mock.patch('requests.get')
        def test_server_error(self, rq_get):
            """Проверка отказа сервера."""
            JSON = {'error': 'testing'}
            resp.json = resp(return_value=JSON)
            rq_get.return_value = resp
            main()

        @mock.patch('requests.get')
        def test_unexpected_status_code(self, rq_get):
            """Проверка неожиданного статуса ответа."""
            resp.status_code = 333
            rq_get.return_value = resp.status_code
            main()

        @mock.patch('requests.get')
        def test_unexpected_homework_status(self, rq_get):
            """Проверка неожиданного статуса домашки."""
            JSON = {'homeworks': [{'homework_name': 'test', 'status': 'test'}]}
            resp.json = resp(return_value=JSON)
            rq_get.return_value = resp
            main()

        @mock.patch('requests.get')
        def test_invalid_json(self, rq_get):
            """Проверка некорректного json."""
            JSON = {'homeworks': 1}
            resp.json = resp(return_value=JSON)
            rq_get.return_value = resp
            main()
    uni_main()
