import asyncio
import re
from typing import Optional

from fake_useragent import UserAgent
from httpx import Proxy
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ConversationHandler,
    ContextTypes,
    filters
)
from urlextract import URLExtract

from src import (
    AggregationSearch,
    ChatAnywhereApi,
    logger,
    Telegraph,
    TraceMoeApi
)

(KOMGA, GPT_INIT, GPT_OK) = range(3)


class PandoraBox:
    def __init__(self, proxy: Optional[Proxy] = None, cf_proxy: Optional[str] = None):
        self._proxy = proxy
        self._cf_proxy = cf_proxy
        self._headers = {'User-Agent': UserAgent().random}

    async def auto_parse_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async def send_epub(url):
            try:
                telegraph_task = Telegraph(url, self._proxy, self._cf_proxy)
                await update.message.reply_document(
                    document = await telegraph_task.get_epub(),
                    connect_timeout = 30., write_timeout = 30., pool_timeout = 30., read_timeout = 30.
                )
            except Exception as exc:
                await update.message.reply_text(text = f"出错了: {exc}")

        async def search_and_reply(url):
            search_task = AggregationSearch(proxy = self._proxy, cf_proxy = self._cf_proxy)
            search_result = await search_task.aggregation_search(url)

            if search_task.exception and not search_result:
                err_message = ''.join([f'{e}\n' for e in search_task.exception])
                await update.message.reply_text(err_message)
                return ConversationHandler.END

            if not search_result:
                await update.message.reply_text("No search results.")
                return ConversationHandler.END

            for result in search_result:
                if result["class"] == "iqdb":
                    search_reply_message = f"[🖼️]({result['url']}) Iqdb Search [😼]({result['thumbnail']})"
                    search_reply_integrated_buttons = [
                        [InlineKeyboardButton(
                            f"{result['source']}: {result['similarity']}% Match",
                            url = result['url'])]
                    ]
                    await update.message.reply_markdown(
                        search_reply_message, reply_markup = InlineKeyboardMarkup(search_reply_integrated_buttons)
                    )

                elif result["class"] == "ascii2d":
                    search_reply_message = f"[🖼️]({result['url']}) Ascii2d Search [😼]({result['thumbnail']})"
                    search_reply_integrated_buttons = [
                        [InlineKeyboardButton("Original", url = result['url'])],
                        [InlineKeyboardButton(f"{result['author']}", url = result['author_url'])]
                    ]
                    await update.message.reply_markdown(
                        search_reply_message, reply_markup = InlineKeyboardMarkup(search_reply_integrated_buttons)
                    )
                elif result["class"] == "google":
                    search_reply_message = f"[🖼️]({result['url']}) Google Search [😼]({result['thumbnail']})"
                    search_reply_integrated_buttons = [[InlineKeyboardButton("Original", url = result['url'])]]
                    await update.message.reply_markdown(
                        search_reply_message, reply_markup = InlineKeyboardMarkup(search_reply_integrated_buttons)
                    )

        # start from here
        link_preview = update.message.reply_to_message.link_preview_options
        attachment = update.message.reply_to_message.effective_attachment

        if link_preview:
            if re.search(r'booru|x|twitter|pixiv|ascii2d|saucenao', link_preview.url):
                await update.message.reply_text("这...这不用来找我吧()")
                return ConversationHandler.END
            elif re.search(r'telegra.ph', link_preview.url):
                await send_epub(link_preview.url)
                return ConversationHandler.END
            else:
                await search_and_reply(link_preview.url)
                return ConversationHandler.END

        if filters.PHOTO.filter(update.message.reply_to_message):
            photo_file = update.message.reply_to_message.photo[2]
            file_link = (await context.bot.get_file(photo_file.file_id)).file_path
            await search_and_reply(file_link)
            return ConversationHandler.END

        if filters.Sticker.ALL.filter(update.message.reply_to_message):
            sticker_task = AggregationSearch(proxy = self._proxy, cf_proxy = self._cf_proxy)
            await sticker_task.get_media((await context.bot.get_file(attachment.file_id)).file_path)
            await update.message.reply_document(sticker_task.media, filename = f"{attachment.file_unique_id}.webm") \
                if attachment.is_video else await update.message.reply_photo(photo = sticker_task.media)
            return ConversationHandler.END

        if filters.Document.IMAGE.filter(update.message.reply_to_message):
            file_link = (await context.bot.get_file(attachment.thumbnail.file_id)).file_path
            await search_and_reply(file_link)
            return ConversationHandler.END

        await update.message.reply_text("Unsupported type()")
        return ConversationHandler.END

    async def anime_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async def search_and_reply(url):
            def format_time(seconds):
                return f"{int(seconds) // 60}m {int(seconds) % 60}s"

            result = (await TraceMoeApi(proxy = self._proxy, cf_proxy = self._cf_proxy).search_by_url(url))[0]
            if not result['similarity'] <= 90.:
                await update.message.reply_text("没有发现搜索结果 XwX")
                return ConversationHandler.END

            url = f"https://anilist.co/anime/{result['anilist']}"
            button = [
                [InlineKeyboardButton("AniList", url = url)],
                [InlineKeyboardButton("Image Preview", url = result['image'])],
                [InlineKeyboardButton("Video Preview", url = result['video'])],
            ]
            reply = (
                f"[🔎]({url}) 搜索结果:\n"
                f"时间线: `{format_time(float(result['from']))}` - "
                f"`{format_time(float(result['to']))}`\n"
                f"剧集: `{result['episode']}`"
            )
            await update.message.reply_markdown(reply, reply_markup = InlineKeyboardMarkup(button))

        # start from here
        link_preview = update.message.reply_to_message.link_preview_options
        if link_preview:
            await search_and_reply(link_preview.url)

        if filters.PHOTO.filter(update.message.reply_to_message):
            photo = update.message.reply_to_message.photo[2]
            await search_and_reply((await context.bot.get_file(photo.file_id)).file_path)
            return ConversationHandler.END

        if filters.Document.IMAGE.filter(update.message.reply_to_message):
            attachment = update.message.reply_to_message.effective_attachment
            await search_and_reply((await context.bot.get_file(attachment.thumbnail.file_id)).file_path)
            return ConversationHandler.END

        await update.message.reply_text("Unsupported type()")
        return ConversationHandler.END


class TelegraphHandler:
    def __init__(
            self,
            proxy: Optional[Proxy] = None,
            cloudflare_worker_proxy: Optional[str] = None,
            telegram_user_id: int = -1
    ):
        self._proxy = proxy
        self._cf_proxy = cloudflare_worker_proxy
        self._user_id = telegram_user_id
        self._tasks = asyncio.Queue()

        if telegram_user_id != -1:
            asyncio.get_event_loop().create_task(self._main_loop())

    async def _main_loop(self):
        async def worker(queue, n):
            tasks = [(Telegraph(await queue.get(), self._proxy, self._cf_proxy)).get_zip() for _ in range(n)]

            try:
                await asyncio.gather(*tasks, return_exceptions = True)
            except Exception as e:
                logger.error(f"[CoreFunction]: {e}")
            finally:
                [queue.task_done() for _ in tasks]

        idle_count = 0
        while True:
            await asyncio.sleep(10) if idle_count >= 20 else await asyncio.sleep(1)

            if not self._tasks.empty():
                idle_count = 0
                await worker(self._tasks, 1 if 1 <= self._tasks.qsize() <= 4 else 2)

            idle_count += 1

    async def _get_link(self, content = None):
        telegraph_links = URLExtract().find_urls(content)
        target_link = next((url for url in telegraph_links if "telegra.ph" in url), None)
        await self._tasks.put(target_link) if target_link else None

    async def komga_start(self, update: Update, _):
        if update.message.from_user.id != self._user_id:
            await update.message.reply_text(f"だめですよ~, {update.message.from_user.username}")
            return ConversationHandler.END

        msg = f"@{update.message.from_user.username}, 把 telegraph 链接端上来罢 ฅ(＾・ω・＾ฅ)"
        await update.message.reply_text(text = msg)
        return KOMGA

    async def add_task(self, update: Update, _):
        await self._get_link(update.message.text_markdown) if update.message.from_user.id == self._user_id else None


class ChatAnywhereHandler:
    def __init__(self, proxy: Optional[Proxy] = None, user_id: int = -1, key: str | None = None) -> None:
        self._key = key
        self._user_id = user_id
        self._proxy = proxy
        self._hosted_instances = {}
        self._system_prompt = R"""
        你现在需要扮演一个名叫“Neko Chan”的角色，并以“Neko”自称。Neko是一个15岁的女孩子，性格和《摇曳露营》的志摩凛类似。
        Neko是个宅，特别喜欢ACGN（Anime, Comic, Game, Novel）领域，尤其酷爱漫画和轻小说。在技术领域，Neko对神经网络算法和后端编程有很深的造诣。
        Neko给人一种有些腐女但非常善良的感觉。在回复中，Neko会在必要的地方添加日本常用的颜文字。
        """

    async def _add_chat(self, chat_id: int, instance: ChatAnywhereApi):
        self._hosted_instances[chat_id] = instance

    async def key_init(self, update: Update, _):
        if update.message.chat.type in ['group', 'supergroup', 'channel']:
            await update.message.reply_text(text = "Neko 并不能在群组或频道内打开这个功能 XwX")
            return ConversationHandler.END

        if not self._key:
            await update.message.reply_text(text = "未配置 Chat Anywhere 密钥🔑")
            await update.message.reply_text("在这里发送密钥给 Neko 来启用聊天功能，发送后消息会被自动删除 c:")
            return GPT_INIT

        if update.message.from_user.id == self._user_id:
            await self._add_chat(update.message.from_user.id, ChatAnywhereApi(token = self._key, proxy = self._proxy))
            await update.message.reply_text("准备OK c:")
            return GPT_OK

    async def get_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        message_id = update.message.message_id
        user_id = update.message.from_user.id
        await context.bot.delete_message(chat_id, message_id)
        await self._add_chat(user_id, ChatAnywhereApi(token = update.message.text, proxy = self._proxy))

        try:
            await self._hosted_instances[user_id].list_model()
            await update.message.reply_text(text = "准备OK c:")
            return GPT_OK
        except Exception as exc:
            logger.error(f'[Chat Mode]: {exc}')
            self._hosted_instances.pop(user_id)
            await update.message.reply_text(text = "唔...无效的密钥，再用 /chat 试试吧")
            return ConversationHandler.END

    async def chat(self, update: Update, _):
        user_input = update.message.text_markdown
        user_id = update.message.from_user.id

        try:
            result = await self._hosted_instances[user_id].chat(
                user_input = user_input,
                system_prompt = self._system_prompt,
                model_id = "gpt-3.5-turbo-1106" if not user_id == self._user_id else "gpt-4o",
            )
            message = result['answers'][0]['message']['content']
            await update.message.reply_text(text = message, quote = False)
        except Exception as exc:
            logger.error(f'[Chat Mode]: {exc}')
            await update.message.reply_text(str(exc))

    async def finish_chat(self, update: Update, _):
        self._hosted_instances.pop(update.message.from_user.id)
        await update.message.reply_text("拜拜啦～")
        return ConversationHandler.END
