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
        # see https://github.com/chatanywhere/GPT_API_free?tab=readme-ov-file#%E7%89%B9%E7%82%B9
        self.CHAT_ANYWHERE_MODEL = os.getenv('CHAT_ANYWHERE_MODEL', "gpt-4o-mini")
        self.CHAT_ANYWHERE_PROMPT = os.getenv(
            'CHAT_ANYWHERE_PROMPT',
            "请你扮演一个名为 Neko 的小动物角色，具有日本萌系风格，给人宅宅的感觉。"
            "在聊天中，适时使用日本常见的颜文字。"
            "请用简单自然的口语表达，灵活调整结束语，确保回答与上下文相关，模拟真实对话，增加互动性。"
        )
        # support format like 'http://[host]:[port]', 'socks5://[host]:[port]'
        self.PROXY = os.getenv('PROXY', None)
        # see https://github.com/ymyuuu/Cloudflare-Workers-Proxy
        self.CF_WORKER_PROXY = os.getenv('CF_WORKER_PROXY', None)
        # you can not set this number too high, or you will be banned by image host services
        self.TELEGRAPH_THREADS = int(os.getenv('TELEGRAPH_THREADS', 2))
        # no need to change
        self.BASE_URL = "https://api.telegram.org/bot"
        self.BASE_FILE_URL = "https://api.telegram.org/file/bot"
        self.WORKING_DIRS = ['/neko/komga', '/neko/dmzj', '/neko/epub', '/neko/.temp']
        self.BOT_COMMAND = {
            '📺': "anime",
            '👋': "bye",
            '💬': "chat",
            '❤️': ["cuddle", "hug", "kiss", "pet", "snog"],
            '❔': "help",
            '📖': "komga",
            '🐉': "long",
            '👀': "start",
        }

    def print_env(self):
        logger.debug(f"[Env]: Bot Token: {self.BOT_TOKEN}")
        logger.debug(f"[Env]: Telegram user ID: {self.MY_USER_ID}")
        logger.debug(f"[Env]: Telegraph download threads: {self.TELEGRAPH_THREADS}")

        for key, value in [
            ("Chat Anywhere key", self.CHAT_ANYWHERE_KEY),
            ("Chat Anywhere model", self.CHAT_ANYWHERE_MODEL),
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
