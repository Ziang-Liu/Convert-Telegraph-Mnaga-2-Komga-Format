from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup


async def introduce(update: Update, _):
    await update.message.reply_markdown(
        f"Nyacome!, {update.message.from_user.full_name}\n\n"
        f"这里是 Neko Chan (=^‥^=)，一个自托管的拥有许多实用的功能的~~高性能~~机器人。"
        f"想了解详细信息可以使用 /help 来获取命令列表与功能介绍\n"
        f"如果你喜欢这个[项目](https://github.com/Ziang-Liu/Neko-Chan), 不妨给它点个 star ฅ(＾・ω・＾ฅ)。"
    )


async def instructions(update: Update, _):
    await update.message.reply_markdown(
        f"_Command List_:\n\n"
        f"/hug | /pet | /kiss | /cuddle | /snog \n"
        f"对待猫猫的不同手段（搂搂抱抱随意选择），Neko 会根据你回复的内容自动自动选择功能:\n"
        f"`功能列表: (PHOTO | Document.IMAGE | Preview.URL: 搜图, "
        f"Sticker: 贴纸下载，text 包含 Telegraph 漫画: 上传 epub)`\n\n"
        f"/anime \n"
        f"支持通过回复文件上传或者聊天图片（番剧截图）来进行番剧的时间线搜索\n\n"
        f"/komga \n`Auto close: 5min` \n"
        f"仅限于所有者填写环境变量中的个人ID后启用，使用命令后将 Telegraph 漫画交给 Neko 就好，她会帮你妥善整理在服务器里的 c:\n\n"
        f"/chat \n`Fallback:` /bye  `Auto close: 5min` \n"
        f"支持 ChatAnywhere API Token，和 Neko 愉快交流吧！(免费令牌会时不时出现请求错误，后面考虑换一个接口)\n"
    )


async def handle_inline_button(update: Update, _):
    choices = [
        [InlineKeyboardButton("猫娘交流模式", callback_data = "gpt")],
        [InlineKeyboardButton("Telegraph 队列", callback_data = "komga")],
        [InlineKeyboardButton("帮助", callback_data = "help")],
        [InlineKeyboardButton("关于", callback_data = "start")],
    ]
    reply_markup = InlineKeyboardMarkup(choices)
    await update.message.reply_text("需要什么帮助瞄", reply_markup = reply_markup)
