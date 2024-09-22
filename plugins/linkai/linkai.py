import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from plugins import *
from .midjourney import MJBot
from .summary import LinkSummary
from bridge import bridge
from common.expired_dict import ExpiredDict
from common import const
import os
from .utils import Util
from config import plugin_config

@plugins.register(
    name="linkai",
    desc="A plugin that supports knowledge base and midjourney drawing.",
    version="0.1.0",
    author="https://link-ai.tech",
    desire_priority=99
)
class LinkAI(Plugin):
    
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        self.config = super().load_config()
        if not self.config:
            # 未加载到配置，使用模板中的配置
            self.config = self._load_config_template()
        if self.config:
            self.mj_bot = MJBot(self.config.get("midjourney"))
        self.sum_config = {}
        if self.config:
            self.sum_config = self.config.get("summary")
        logger.info(f"[LinkAI] inited, config={self.config}")


    def on_handle_context(self, e_context: EventContext):
        """
        消息处理逻辑
        :param e_context: 消息上下文
        """
        if not self.config:
            return

        context = e_context['context']
        if context.type not in [ContextType.TEXT, ContextType.IMAGE, ContextType.IMAGE_CREATE, ContextType.FILE,
                                ContextType.SHARING]:
            # filter content no need solve
            return


        #文件 或 图片 
        #文件 或 图片 (其实主要是 文件，只不过原代码 是 文件或图片，没改它罢了。)
        if context.type in [ContextType.FILE, ContextType.IMAGE] and self._is_summary_open(context):
            # 文件处理
            context.get("msg").prepare()
            file_path = context.content

            #遇到 不支持的文件，提前退出
            if not LinkSummary().check_file(file_path, self.sum_config):
                #统一不在插件内给用户回话。_send_info(e_context, "只能解读小于 5 MB 的 txt, csv, docx, pdf, md, jpg, jpeg, png 文件")
                #
                #设置返回结果内容。炳用 reply的ReplyType.ERROR表示: 内部遇到不支持的内容类型（如视频号或其他文件后缀），中途退出，无需后续处理。
                ReplyErrorMsg_and_BREAK_PASS("只能解读小于 5 MB 的 txt, csv, docx, pdf, md, jpg, jpeg, png 文件", e_context)
                return
            
            #收到文件
            if context.type != ContextType.IMAGE:
                _send_info(e_context, "收到文件，正在生成摘要，请稍后...\n\n（支持的文件类型：txt, csv, docx, pdf, md, jpg, jpeg, png）")

            res = LinkSummary().summary_file(file_path)
            if not res:
                if context.type != ContextType.IMAGE:
                    #设置返回结果内容。炳用 reply的ReplyType.ERROR表示: 内部遇到不支持的内容类型（如视频号或其他文件后缀），中途退出，无需后续处理。
                    ReplyErrorMsg_and_BREAK_PASS("试图总结文件时出错，因为神秘力量无法获取内容，请稍后再试吧", e_context)
                    
                return
            
            summary_text = res.get("summary")
            
            if context.type != ContextType.IMAGE:
                USER_FILE_MAP[_find_user_id(context) + "-sum_id"] = res.get("summary_id")
                #炳暂不支持这个功能：summary_text += "\n\n💬 发送 \"开启对话\" 可以开启与文件内容的对话"
            
            _set_reply_text(summary_text, e_context, level=ReplyType.TEXT)
            
            os.remove(file_path)
            
            return


        #公众号分享 或 总结文件
        #公众号分享 或 总结文件
        if (context.type == ContextType.SHARING and self._is_summary_open(context)) or \
                (context.type == ContextType.TEXT and self._is_summary_open(context) and LinkSummary().check_url(context.content)):
            
            #如是一个 邀请我进群 的分享SHARING
            #context.content中的 邀请我进群 的 链接：
            #Context(type=SHARING, content=https://support.weixin.qq.com/cgi-bin/mmsupport-bin/addchatroombyinvite?ticket=AUYmZw%2BLQ0QRjwtZsy%2BdEg%3D%3D
                    #域名: support.weixin.qq.com
                    #路径: /cgi-bin/mmsupport-bin/addchatroombyinvite
                    #参数: ticket=Afbzq5r%2FzwOtWXMJ0uWOlA%3D%3D
            if (context.type == ContextType.SHARING) and (context.content.startswith("https://support.weixin.qq.com/cgi-bin/mmsupport-bin/addchatroombyinvite?ticket=")):
                ReplyErrorMsg_and_BREAK_PASS("收到，谢谢你邀请我进群。", e_context)
                return

            if not LinkSummary().check_url(context.content):
                ReplyErrorMsg_and_BREAK_PASS("收到我看不懂的：\n❎小程序分享\n❎视频号分享\n\n请发我能看懂的：\n✅微信公众号分享", e_context)
                return
            
            _send_info(e_context, "收到：\n✅公众号分享\n正在阅读...")
            
            res = LinkSummary().summary_url(context.content)
            
            if not res:
                ReplyErrorMsg_and_BREAK_PASS("（公众号文章）因为神秘力量无法获取文章内容，请稍后再试吧~", e_context)
                return
            
            #炳注：下面这句 里面会 设 BREAK_PASS
            #                                     V 原下行此处的文字被去掉：  \n\n💬 发送 \"开启对话\" 可以开启与文章内容的对话
            _set_reply_text(res.get("summary") + " ", e_context, level=ReplyType.TEXT)
            
            USER_FILE_MAP[_find_user_id(context) + "-sum_id"] = res.get("summary_id")
            return

        mj_type = self.mj_bot.judge_mj_task_type(e_context)
        if mj_type:
            # MJ作图任务处理
            self.mj_bot.process_mj_task(mj_type, e_context)
            return

        if context.content.startswith(f"{_get_trigger_prefix()}linkai"):
            # 应用管理功能
            self._process_admin_cmd(e_context)
            return

        if context.type == ContextType.TEXT and context.content == "开启对话" and _find_sum_id(context):
            # 文本对话
            _send_info(e_context, "正在为你开启对话，请稍后")
            res = LinkSummary().summary_chat(_find_sum_id(context))
            if not res:
                _set_reply_text("开启对话失败，请稍后再试吧", e_context)
                return
            USER_FILE_MAP[_find_user_id(context) + "-file_id"] = res.get("file_id")
            _set_reply_text("💡你可以问我关于这篇文章的任何问题，例如：\n\n" + res.get(
                "questions") + "\n\n发送 \"退出对话\" 可以关闭与文章的对话", e_context, level=ReplyType.TEXT)
            return

        if context.type == ContextType.TEXT and context.content == "退出对话" and _find_file_id(context):
            del USER_FILE_MAP[_find_user_id(context) + "-file_id"]
            bot = bridge.Bridge().find_chat_bot(const.LINKAI)
            bot.sessions.clear_session(context["session_id"])
            _set_reply_text("对话已退出", e_context, level=ReplyType.TEXT)
            return

        if context.type == ContextType.TEXT and _find_file_id(context):
            bot = bridge.Bridge().find_chat_bot(const.LINKAI)
            context.kwargs["file_id"] = _find_file_id(context)
            reply = bot.reply(context.content, context)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        #判断 是不是 group_app_map群聊与LINKAI的应用 映射的 聊天 ？
        if self._is_chat_task(e_context):
            # 文本对话任务处理
            self._process_chat_task(e_context)

    # 插件管理功能
    def _process_admin_cmd(self, e_context: EventContext):
        context = e_context['context']
        cmd = context.content.split()
        if len(cmd) == 1 or (len(cmd) == 2 and cmd[1] == "help"):
            _set_reply_text(self.get_help_text(verbose=True), e_context, level=ReplyType.INFO)
            return

        if len(cmd) == 2 and (cmd[1] == "open" or cmd[1] == "close"):
            # 知识库开关指令
            if not Util.is_admin(e_context):
                _set_reply_text("需要管理员权限执行", e_context, level=ReplyType.ERROR)
                return
            is_open = True
            tips_text = "开启"
            if cmd[1] == "close":
                tips_text = "关闭"
                is_open = False
            conf()["use_linkai"] = is_open
            bridge.Bridge().reset_bot()
            _set_reply_text(f"LinkAI对话功能{tips_text}", e_context, level=ReplyType.INFO)
            return

        if len(cmd) == 3 and cmd[1] == "app":
            # 知识库应用切换指令
            if not context.kwargs.get("isgroup"):
                _set_reply_text("该指令需在群聊中使用", e_context, level=ReplyType.ERROR)
                return
            if not Util.is_admin(e_context):
                _set_reply_text("需要管理员权限执行", e_context, level=ReplyType.ERROR)
                return
            app_code = cmd[2]
            group_name = context.kwargs.get("msg").from_user_nickname
            group_mapping = self.config.get("group_app_map")
            if group_mapping:
                group_mapping[group_name] = app_code
            else:
                self.config["group_app_map"] = {group_name: app_code}
            # 保存插件配置
            super().save_config(self.config)
            _set_reply_text(f"应用设置成功: {app_code}", e_context, level=ReplyType.INFO)
            return

        if len(cmd) == 3 and cmd[1] == "sum" and (cmd[2] == "open" or cmd[2] == "close"):
            # 知识库开关指令
            if not Util.is_admin(e_context):
                _set_reply_text("需要管理员权限执行", e_context, level=ReplyType.ERROR)
                return
            is_open = True
            tips_text = "开启"
            if cmd[2] == "close":
                tips_text = "关闭"
                is_open = False
            if not self.sum_config:
                _set_reply_text(
                    f"插件未启用summary功能，请参考以下链添加插件配置\n\nhttps://github.com/zhayujie/chatgpt-on-wechat/blob/master/plugins/linkai/README.md",
                    e_context, level=ReplyType.INFO)
            else:
                self.sum_config["enabled"] = is_open
                _set_reply_text(f"文章总结功能{tips_text}", e_context, level=ReplyType.INFO)
            return

        _set_reply_text(f"指令错误，请输入{_get_trigger_prefix()}linkai help 获取帮助", e_context,
                        level=ReplyType.INFO)
        return

    def _is_summary_open(self, context) -> bool:
        if not self.sum_config or not self.sum_config.get("enabled"):
            return False
        if context.kwargs.get("isgroup") and not self.sum_config.get("group_enabled"):
            return False
        support_type = self.sum_config.get("type") or ["FILE", "SHARING"]
        if context.type.name not in support_type and context.type.name != "TEXT":
            return False
        return True

    # LinkAI 对话任务处理
    def _is_chat_task(self, e_context: EventContext):
        context = e_context['context']
        # 群聊应用管理
        return self.config.get("group_app_map") and context.kwargs.get("isgroup")

    def _process_chat_task(self, e_context: EventContext):
        """
        处理LinkAI对话任务
        :param e_context: 对话上下文
        """
        context = e_context['context']
        # 群聊应用管理
        group_name = context.get("msg").from_user_nickname
        app_code = self._fetch_group_app_code(group_name)
        if app_code:
            context.kwargs['app_code'] = app_code

    def _fetch_group_app_code(self, group_name: str) -> str:
        """
        根据群聊名称获取对应的应用code
        :param group_name: 群聊名称
        :return: 应用code
        """
        group_mapping = self.config.get("group_app_map")
        if group_mapping:
            app_code = group_mapping.get(group_name) or group_mapping.get("ALL_GROUP")
            return app_code

    def get_help_text(self, verbose=False, **kwargs):
        trigger_prefix = _get_trigger_prefix()
        help_text = "用于集成 LinkAI 提供的知识库、Midjourney绘画、文档总结、联网搜索等能力。\n\n"
        if not verbose:
            return help_text
        help_text += f'📖 知识库\n - 群聊中指定应用: {trigger_prefix}linkai app 应用编码\n'
        help_text += f' - {trigger_prefix}linkai open: 开启对话\n'
        help_text += f' - {trigger_prefix}linkai close: 关闭对话\n'
        help_text += f'\n例如: \n"{trigger_prefix}linkai app Kv2fXJcH"\n\n'
        help_text += f"🎨 绘画\n - 生成: {trigger_prefix}mj 描述词1, 描述词2.. \n - 放大: {trigger_prefix}mju 图片ID 图片序号\n - 变换: {trigger_prefix}mjv 图片ID 图片序号\n - 重置: {trigger_prefix}mjr 图片ID"
        help_text += f"\n\n例如：\n\"{trigger_prefix}mj a little cat, white --ar 9:16\"\n\"{trigger_prefix}mju 11055927171882 2\""
        help_text += f"\n\"{trigger_prefix}mjv 11055927171882 2\"\n\"{trigger_prefix}mjr 11055927171882\""
        help_text += f"\n\n💡 文档总结和对话\n - 开启: {trigger_prefix}linkai sum open\n - 使用: 发送文件、公众号文章等可生成摘要，并与内容对话"
        return help_text

    def _load_config_template(self):
        logger.debug("No LinkAI plugin config.json, use plugins/linkai/config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    plugin_conf["midjourney"]["enabled"] = False
                    plugin_conf["summary"]["enabled"] = False
                    plugin_config["linkai"] = plugin_conf
                    return plugin_conf
        except Exception as e:
            logger.exception(e)

    def reload(self):
        self.config = super().load_config()


def _send_info(e_context: EventContext, content: str):
    reply = Reply(ReplyType.TEXT, content)
    channel = e_context["channel"]
    channel.send(reply, e_context["context"])


def _find_user_id(context):
    if context["isgroup"]:
        return context.kwargs.get("msg").actual_user_id
    else:
        return context["receiver"]


def _set_reply_text(content: str, e_context: EventContext, level: ReplyType = ReplyType.ERROR):
    reply = Reply(level, content)
    e_context["reply"] = reply
    e_context.action = EventAction.BREAK_PASS


#炳 常用函数：回复错误消息，并设BREAK_PASS
def ReplyErrorMsg_and_BREAK_PASS(contentMsg: str, e_context: EventContext):
    _set_reply_text(contentMsg, e_context, ReplyType.ERROR)


def _get_trigger_prefix():
    return conf().get("plugin_trigger_prefix", "$")


def _find_sum_id(context):
    return USER_FILE_MAP.get(_find_user_id(context) + "-sum_id")


def _find_file_id(context):
    user_id = _find_user_id(context)
    if user_id:
        return USER_FILE_MAP.get(user_id + "-file_id")


USER_FILE_MAP = ExpiredDict(conf().get("expires_in_seconds") or 60 * 30)
