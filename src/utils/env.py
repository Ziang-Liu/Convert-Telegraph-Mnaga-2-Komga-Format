import os

from .logger import logger


class EnvironmentReader:
    def __init__(self):
        # see https://core.telegram.org/bots/api#authorizing-your-bot
        self.BOT_TOKEN = os.getenv('BOT_TOKEN', None)
        # you can get from this bot https://t.me/userinfobot
        self.MY_USER_ID = int(os.getenv('MY_USER_ID', -1))
        # see https://buyca.tech/ or https://api.chatanywhere.org/v1/oauth/free/render
        self.CHAT_ANYWHERE_KEY = os.getenv('CHAT_ANYWHERE_KEY', None)
        # support format like 'http://[host]:[port]', 'socks5://[host]:[port]'
        self.PROXY = os.getenv('PROXY', None)
        # see https://github.com/ymyuuu/Cloudflare-Workers-Proxy
        self.CF_WORKER_PROXY = os.getenv('CF_WORKER_PROXY', None)
        # you can not set this number too high, or you will be banned by image host services
        self.TELEGRAPH_THREADS = int(os.getenv('TELEGRAPH_THREADS', 2))

    def print_env(self):
        logger.debug(f"[Env]: Bot Token: {self.BOT_TOKEN}")
        logger.debug(f"[Env]: Telegram user ID: {self.MY_USER_ID}")
        logger.debug(f"[Env]: Telegraph download threads: {self.TELEGRAPH_THREADS}")

        for key, value in [
            ("Chat Anywhere key", self.CHAT_ANYWHERE_KEY),
            ("Proxy", self.PROXY),
            ("CloudFlare Worker Proxy", self.CF_WORKER_PROXY),
        ]:
            if value:
                logger.debug(f"[Env] (str): {key}: '{value}'")

    def print_attribute(self, attribute_name):
        if hasattr(self, attribute_name):
            attribute_value = getattr(self, attribute_name)
            logger.info(f"[Env]: {attribute_name}: {attribute_value}")
        else:
            attribute_value = getattr(self, attribute_name)
            logger.info(f"[Env]: {attribute_name}: {attribute_value}")

    def get_variable(self, variable_name):
        value = getattr(self, variable_name, None)
        if isinstance(value, str):
            return value.strip() if value is not None else None

        return value
