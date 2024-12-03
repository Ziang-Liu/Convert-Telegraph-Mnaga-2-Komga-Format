import os

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import (
    introduce,
    instructions,
    ChatAnywhereHandler,
    GPT_OK,
    GPT_INIT,
    KOMGA,
    PandoraBox,
    LongSticker,
    TelegraphHandler
)
from src.utils import EnvironmentReader, logger, proxy_init

if __name__ == "__main__":
    async def error_handler(_, context: ContextTypes.DEFAULT_TYPE):
        logger.error(context.error)


    # this project's working dirs are all declared here
    working_dirs = ['/neko/komga', '/neko/dmzj', '/neko/epub', '/neko/.temp']
    [os.makedirs(name = working_dir, exist_ok = True, mode = 0o777) for working_dir in working_dirs]
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # get compose Environments
    _env = EnvironmentReader()
    # proxy for magic connection
    _cf_worker_proxy = _env.get_variable("CF_WORKER_PROXY")
    _proxy = _env.get_variable("PROXY")
    proxy = proxy_init(_proxy) if _proxy else None
    # Telegram basic params
    _bot_token = _env.get_variable("BOT_TOKEN")
    _my_user_id = _env.get_variable("MY_USER_ID")
    # ChatAnywhere network_api token
    _chat_anywhere_key = _env.get_variable("CHAT_ANYWHERE_KEY")
    # Telegram bot network_api url
    _base_url = 'https://api.telegram.org/bot'
    _base_file_url = 'https://api.telegram.org/file/bot'
    base_url = f'{_cf_worker_proxy}/{_base_url}' if _cf_worker_proxy else _base_url
    base_file_url = f'{_cf_worker_proxy}/{_base_file_url}' if _cf_worker_proxy else _base_file_url

    # exit if no bot token
    if not _bot_token:
        logger.error("[Main]: Bot token not set, please fill right params and try again.")
        exit(1)

    # create bot with envs
    neko_chan = (
        ApplicationBuilder().token(_bot_token).
        proxy(proxy).get_updates_proxy(proxy).
        pool_timeout(30.).connect_timeout(30.).
        base_url(base_url).base_file_url(base_file_url).build()
    )

    # static reply with basic command
    neko_chan.add_handler(CommandHandler("start", introduce))
    neko_chan.add_handler(CommandHandler("help", instructions))
    # core function: parse information of messages you replied
    long = LongSticker(proxy = proxy, cloudflare_worker_proxy = _cf_worker_proxy)
    play_something_fault = CommandHandler(
        command = "long",
        callback = long.play_from_photo
    )
    pandora = PandoraBox(proxy = proxy, cf_proxy = _cf_worker_proxy)
    parse = CommandHandler(
        command = ["hug", "cuddle", "kiss", "snog", "pet"],
        callback = pandora.auto_parse_reply,
        filters = filters.REPLY
    )
    anime_search = CommandHandler(
        command = "anime",
        callback = pandora.anime_search,
        filters = filters.REPLY
    )
    neko_chan.add_handler(play_something_fault)
    neko_chan.add_handler(parse)
    neko_chan.add_handler(anime_search)

    if _my_user_id == -1:
        logger.info("[Main]: Master's user id not set, telegraph syncing service will not work.")
    else:
        # core function: sync Telegraph manga to local storage
        telegraph = TelegraphHandler(
            proxy = proxy, telegram_user_id = _my_user_id, cloudflare_worker_proxy = _cf_worker_proxy)
        telegraph_monitor = ConversationHandler(
            entry_points = [CommandHandler(command = "komga", callback = telegraph.komga_start)],
            states = {KOMGA: [MessageHandler(filters = filters.TEXT, callback = telegraph.add_task)]},
            fallbacks = [],
            conversation_timeout = 300
        )
        neko_chan.add_handler(telegraph_monitor)

    # core function: use ChatAnywhere network_api to use chatgpt
    chat_anywhere = ChatAnywhereHandler(
        proxy = proxy,
        user_id = int(_my_user_id),
        key = _chat_anywhere_key if _chat_anywhere_key else None
    )
    chat_anywhere_init = ConversationHandler(
        entry_points = [CommandHandler(command = "chat", callback = chat_anywhere.key_init)],
        states = {
            GPT_INIT: [MessageHandler(filters = filters.TEXT & ~filters.COMMAND, callback = chat_anywhere.get_key)],
            GPT_OK: [MessageHandler(filters = filters.TEXT & ~filters.COMMAND, callback = chat_anywhere.chat)]
        },
        conversation_timeout = 300,
        fallbacks = [CommandHandler(command = "bye", callback = chat_anywhere.finish_chat)]
    )
    neko_chan.add_handler(chat_anywhere_init)

    # error handler (no use now)
    neko_chan.add_error_handler(error_handler)

    try:
        _env.print_env()
        logger.info("[Main]: Initialise Neko Chan......")
        neko_chan.run_polling(allowed_updates = Update.ALL_TYPES)
    except Exception as exc:
        logger.error(f"[Main]: Fatal error in initialization: {exc}")
        exit(1)
