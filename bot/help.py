from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup


async def introduce(update: Update, _):
    await update.message.reply_markdown(
        f"Nyacome!, {update.message.from_user.full_name}\n\n"
        f"这里是 Neko Chan (=^‥^=)，一个自托管的拥有许多实用的功能的~~高性能~~机器人。"
        f"想了解详细信息可以使用 /help 来获取命令列表与功能介绍\n"
        f"如果你喜欢这个[项目](https://github.com/wiseCirno/neko-chan-telegram-bot), 可以给个🌟哦。"
    )


async def instructions(update: Update, _):
    await update.message.reply_markdown(
        "_命令列表_:\n\n"
        
        "/hug /pet /kiss /cuddle /snog\n"
        "对猫猫搂搂抱抱请随意 c:，Neko 开心了以后会根据你回复的内容来：搜图；把 Telegraph 本子打包成 epub；下载贴纸\n\n"
        
        "/anime\n"
        "支持通过回复上传的图片文件/压缩图片的番剧截图（）来进行番剧搜索（时间线也有哦）。\n\n"
        
        "/komga\n"
        "`自动关闭: 5min`\n"
        "仅限于所有者填写环境变量中的个人ID后启用，使用命令后将 Telegraph 漫画交给 Neko，她会帮你妥善整理在服务器里的 c:\n\n"
        
        "/chat\n"
        "`结束聊天` /bye\n"
        "`自动关闭: 5min`\n"
        "支持 ChatAnywhere API Token，和 Neko 愉快交流吧！\n"
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
