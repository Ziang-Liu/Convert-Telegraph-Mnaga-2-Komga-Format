import os

HOST = os.getenv('SOCKS_HOST')
PORT = os.getenv('SOCKS_PORT', int)
TGBOT_TOKEN = os.getenv('TG_BOT_TOKEN')
DOWNLOAD_THREADS = os.getenv('DOWNLOAD_THREADS', int)
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', '/download')
GET_HEADER_TEST_URL = 'https://www.apple.com'