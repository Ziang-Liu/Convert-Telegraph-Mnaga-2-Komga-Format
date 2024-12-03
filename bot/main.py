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


    _env = EnvironmentReader()
    _proxy = proxy_init(_env.get_variable("PROXY"))
    _cf_proxy = _env.get_variable("CF_WORKER_PROXY")
    _bot_token = _env.get_variable("BOT_TOKEN")
    _user_id = _env.get_variable("MY_USER_ID")
    _chat_key = _env.get_variable("CHAT_ANYWHERE_KEY")
    _chat_model = _env.get_variable("CHAT_ANYWHERE_MODEL")
    _chat_prompt = _env.get_variable("CHAT_ANYWHERE_PROMPT")
    _telegraph_thread = _env.get_variable("TELEGRAPH_THREADS")
    _cmd = _env.BOT_COMMAND
    _base_url = f'{_cf_proxy}/{_env.BASE_URL}' if _cf_proxy else _env.BASE_URL
    _base_file_url = f'{_cf_proxy}/{_env.BASE_FILE_URL}' if _cf_proxy else _env.BASE_FILE_URL
    [os.makedirs(name = d, exist_ok = True, mode = 0o777) for d in _env.WORKING_DIRS]
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # exit if no bot token
    if not _bot_token:
        logger.error("[Main]: Bot token not set, please fill right params and try again.")
        exit(1)

    # create bot with envs
    neko_chan = (
        ApplicationBuilder().token(_bot_token).
        proxy(_proxy).get_updates_proxy(_proxy).
        pool_timeout(30.).connect_timeout(30.).
        base_url(_base_url).base_file_url(_base_file_url).build()
    )

    # core function: Send Long Sticker
    long = LongSticker(_proxy, _cf_proxy)
    # core function: Parse contents based on reply
    pandora = PandoraBox(_proxy, _cf_proxy)

    neko_chan.add_handler(CommandHandler(_cmd['👀'], introduce))
    neko_chan.add_handler(CommandHandler(_cmd['❔'], instructions))
    neko_chan.add_handler(CommandHandler(_cmd['🐉'], long.wan_xx_wan_de, filters.PHOTO | filters.REPLY))
    neko_chan.add_handler(CommandHandler(_cmd['❤️'], pandora.parse, filters.REPLY))
    neko_chan.add_handler(CommandHandler(_cmd['📺'], pandora.anime_search, filters.REPLY))

    if _user_id == -1:
        logger.info("[Main]: User ID not set, telegraph syncing service will not work.")
    else:
        # core function: Sync Telegraph manga
        telegraph = TelegraphHandler(_user_id, _telegraph_thread, _proxy, _cf_proxy)
        telegraph_monitor = ConversationHandler(
            entry_points = [CommandHandler(_cmd['📖'], telegraph.komga_start)],
            states = {KOMGA: [MessageHandler(filters.TEXT, telegraph.add_task)]},
            fallbacks = [],
            conversation_timeout = 300
        )
        neko_chan.add_handler(telegraph_monitor)

    # core function: ChatAnywhere GPT conversation
    chat_anywhere = ChatAnywhereHandler(_user_id, _chat_key, _chat_model, _chat_prompt, _proxy, _cf_proxy)
    lets_chat = ConversationHandler(
        entry_points = [CommandHandler(_cmd['💬'], chat_anywhere.new)],
        states = {
            GPT_INIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_anywhere.get_key)],
            GPT_OK: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_anywhere.chat)]
        },
        fallbacks = [CommandHandler(_cmd['👋'], chat_anywhere.bye)],
        conversation_timeout = 300
    )
    neko_chan.add_handler(lets_chat)

    # error handler (no use now)
    neko_chan.add_error_handler(error_handler)

    try:
        _env.print_env()
        logger.info("[Main]: Initialise Neko Chan......")
        neko_chan.run_polling(allowed_updates = Update.ALL_TYPES)
    except Exception as exc:
        logger.error(f"[Main]: Fatal error in initialization: {exc}")
        exit(1)
