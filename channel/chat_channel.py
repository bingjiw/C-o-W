# #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
# #《《《《《 引入另一个 专门判断回答是否是“很抱歉，我无法”之类的 函数 .py 文件
# #《《《《《 判断 AI回复的文本 决定要不要实时搜索
# from channel.ANSWER_APOLOGY import analyze_text_features__need_search
#《《《《《 引入 PLUGIN_MANager_instance 以便本文件中可用它
from plugins import instance as PLUGIN_MANager_instance
#《《《《《 引入 bridge单例，以便下面要 重设bot时用
from bridge import bridge
from bridge.bridge import Bridge
from common import const
#《《《《《 引入 随机数
import random
#》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》

import os
import re
import threading
import time
from asyncio import CancelledError
from concurrent.futures import Future, ThreadPoolExecutor

from bridge.context import *
from bridge.reply import *
from channel.channel import Channel
from common.dequeue import Dequeue
from common import memory
from plugins import *
from channel.MemorableTalker import *


try:
    from voice.audio_convert import any_to_wav
except Exception as e:
    pass

handler_pool = ThreadPoolExecutor(max_workers=8)  # 处理消息的线程池


#此函数不属于类
def _send_info(e_context: EventContext, content: str):
    reply = Reply(ReplyType.TEXT, content)
    channel = e_context["channel"]
    channel.send(reply, e_context["context"])


# 抽象类, 它包含了与消息通道无关的通用处理逻辑
class ChatChannel(Channel):
    name = None  # 登录的用户名
    user_id = None  # 登录的用户id
    futures = {}  # 记录每个session_id提交到线程池的future对象, 用于重置会话时把没执行的future取消掉，正在执行的不会被取消
    sessions = {}  # 用于控制并发，每个session_id同时只能有一个context在处理
    lock = threading.Lock()  # 用于控制对sessions的访问

    def __init__(self):
        _thread = threading.Thread(target=self.consume)
        _thread.setDaemon(True)
        _thread.start()

    # 根据消息构造context，消息内容相关的触发项写在这里
    def _compose_context(self, ctype: ContextType, content, **kwargs):

        #炳：对 微信的引用 提取文本与整理格式
        def WeiXin_Reference_extract_and_format(text):
            # 1. 删除第一次遇到的「和：之间的内容，并删除：
            text = re.sub(r'「[^」]*：', '「', text, count=1)
            
            # 2. 将最后一次出现的 - - - - - - - - - - - - - - - 替换为换行
            text = text.rsplit('- - - - - - - - - - - - - - -', 1)
            text = '\n'.join(text)
            
            return text


        context = TextizedContextMsg(ctype, content)
        context.kwargs = kwargs
        # context首次传入时，origin_ctype是None,
        # 引入的起因是：当输入语音时，会嵌套生成两个context，第一步语音转文本，第二步通过文本生成文字回复。
        # origin_ctype用于第二步文本回复时，判断是否需要匹配前缀，如果是私聊的语音，就不需要匹配前缀
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype
        # context首次传入时，receiver是None，根据类型设置receiver
        first_in = "receiver" not in context
        # 群名匹配过程，设置session_id和receiver
        if first_in:  # context首次传入时，receiver是None，根据类型设置receiver
            config = conf()
            cmsg = context["msg"]
            user_data = conf().get_user_data(cmsg.from_user_id)

            ###############
            #炳：给每个用户一个以他的自己的ID作为令牌，取其ID的前11个字符
            #from_user_id=@e7a3951a75b5320ccc9ecb34a3bea3627b178951868257504ff4c27e6e1c6d80,
            # 取字符串的前11个字符，包括@共11个。否则太长了. 即使字符串 s 只有5个字符，使用 s[:11] 也不会出错，而是返回整个字符串。
            # 原本user_data中的api_key是只在Godcmd插件中设置的
            first_11_chars = cmsg.from_user_id[:11]
            user_data["openai_api_key"] = first_11_chars
            ###############

            context["openai_api_key"] = user_data.get("openai_api_key")
            
            context["gpt_model"] = user_data.get("gpt_model")
            
            if context.IsGroupChat :
                group_name = context.GroupName
                group_id = context.GroupID

                ##########################
                #### 第1级过滤：群名过滤 ####
                #群名过滤，检查 对来源于此群的消息 要不要 响应，还是忽略 
                group_name_white_list = config.get("group_name_white_list", [])
                group_name_keyword_white_list = config.get("group_name_keyword_white_list", [])
                if any(
                    [
                        group_name in group_name_white_list,
                        "ALL_GROUP" in group_name_white_list,
                        check_contain(group_name, group_name_keyword_white_list),
                    ]
                ):
                    group_chat_in_one_session = conf().get("group_chat_in_one_session", [])
                    session_id = cmsg.actual_user_id
                    if any(
                        [
                            group_name in group_chat_in_one_session,
                            "ALL_GROUP" in group_chat_in_one_session,
                        ]
                    ):
                        session_id = group_id
                else:
                    #群名过滤，对不在白名单的群名，不组装context
                    #且直接return后，不会再往下走
                    logger.debug(f"No need reply, groupName not in whitelist, group_name={group_name}")
                    return None
                
                context["session_id"] = session_id
                context["receiver"] = group_id
            else:
                context["session_id"] = cmsg.other_user_id
                context["receiver"] = cmsg.other_user_id

            #至此 context  组装完成

            e_context = PluginManager().emit_event(EventContext(Event.ON_RECEIVE_MESSAGE, {"channel": self, "context": context}))
            
            context = e_context["context"]
            if e_context.is_pass() or context is None:
                return context
            if cmsg.from_user_id == self.user_id and not config.get("trigger_by_self", True):
                logger.debug("[chat_channel]self message skipped")
                return None

        # 消息内容匹配过程，并处理content
        # 若是 文件
        if (ctype == ContextType.FILE) :
            # 群聊中有人发文件，不用理它。不支持群聊内发的文件解读，且不一定是发给我机器人看的。
            if context.IsGroupChat:  # 群聊
                #对群聊中的文件，啥也不用干，直接退出函数，不要返回context对象
                return

                # #对群聊中的文件，让函数最后会自动返回 context
                # # 因 group-talker 需要群聊中的文件 
                # pass

            else:  # 单聊
                #对单聊中的文件，啥也不用干。函数最后会自动返回 context 的
                pass

        # 若是 文本 或 分享
        elif (ctype == ContextType.TEXT) or (ctype == ContextType.SHARING) :

            #微信中的引用  , 也是属于文字TEXT 
            if first_in and "」\n- - - - - - -" in content:  # 初次匹配 过滤引用消息

                #炳改，使支持 微信中的引用
                #整理一下文本与格式，以便LLM处理与理解
                content = WeiXin_Reference_extract_and_format(content)
                logger.debug(f"微信引用修整格式后:\n{content}")
                #logger.debug("[chat_channel]reference query skipped")
                #炳：取消了原来对引用的跳过 return None


            ###########################################
            #### 第2级过滤：检查 群聊消息 有没有 @机器人的前缀 或 某些触发机器人回答的关键字 ####
            nick_name_black_list = conf().get("nick_name_black_list", [])

            # 群聊 ################
            if context.IsGroupChat :  # 群聊
                # 检查 群聊消息 有没有 @机器人的前缀 或 某些触发机器人回答的关键字
                
                # 前缀：有没有匹配到
                match_prefix = check_prefix(content, conf().get("group_chat_prefix"))
                
                # 包含关键字：有没有匹配到
                match_contain = check_contain(content, conf().get("group_chat_keyword"))
                
                flag = False
                if context["msg"].to_user_id != context["msg"].actual_user_id:

                    # 消息发送者的 昵称
                    nick_name = context.SpeakerNickName

                    context.Is_at_Me_in_Group = match_prefix is not None or match_contain is not None
                    if context.Is_at_Me_in_Group:
                        flag = True
                        if match_prefix:
                            content = content.replace(match_prefix, "", 1).strip()
                    
                    #是否 群聊 被@了
                    if context["msg"].is_at:

                        if nick_name and nick_name in nick_name_black_list:
                            # 第3级过滤：黑名单过滤
                            # 第3级过滤：消息发送者的 昵称黑名单 过滤 
                            logger.warning(f"[chat_channel]群聊时，昵称【{nick_name}】在昵称黑名单nick_name_black_list中, 忽略")
                            return None

                        logger.info("[chat_channel]receive group at")
                        if not conf().get("group_at_off", False):
                            flag = True
                        self.name = self.name if self.name is not None else ""  # 部分渠道self.name可能没有赋值
                        pattern = f"@{re.escape(self.name)}(\u2005|\u0020)"
                        subtract_res = re.sub(pattern, r"", content)
                        if isinstance(context["msg"].at_list, list):
                            for at in context["msg"].at_list:
                                pattern = f"@{re.escape(at)}(\u2005|\u0020)"
                                subtract_res = re.sub(pattern, r"", subtract_res)
                        if subtract_res == content and context["msg"].self_display_name:
                            # 前缀移除后没有变化，使用群昵称再次移除
                            pattern = f"@{re.escape(context['msg'].self_display_name)}(\u2005|\u0020)"
                            subtract_res = re.sub(pattern, r"", content)
                        content = subtract_res
                        logger.info(f"群聊中收到一条消息，删除所有 @ 之后的内容是：{content}")

                #很重要的标志信息：在群聊中，是否被@了。
                #因若被@，则必须要回答。
                #否则group-talker可答 可不答
                context.Being_at_Me_in_Group = flag

                if not flag:
                    if context["origin_ctype"] == ContextType.VOICE:
                        logger.info("[chat_channel]receive group voice, but checkprefix didn't match")
                    
                    #炳改前  原本是：return None
                    #因 group-talker（主动聊天者功能） 不论对方是不是 @我机器人，都要处理，都有可能会回复。


            # 单聊 ################
            else:  # 单聊
                nick_name = context.SpeakerNickName

                if nick_name and nick_name in nick_name_black_list:
                    # 黑名单过滤
                    # 这里是第2次黑名单过滤，滤文字类。      第1次过滤 滤：语音与图片
                    logger.warning(f"[chat_channel]单聊时，昵称【{nick_name}】在昵称黑名单nick_name_black_list中, 忽略")
                    #logger.warning(f"[chat_channel] Nickname '{nick_name}' in In BlackList, ignore")
                    return None

                match_prefix = check_prefix(content, conf().get("single_chat_prefix", [""]))
                if match_prefix is not None:  # 判断如果匹配到自定义前缀，则返回过滤掉前缀+空格后的内容
                    content = content.replace(match_prefix, "", 1).strip()
                elif context["origin_ctype"] == ContextType.VOICE:  # 如果源消息是私聊的语音消息，允许不匹配前缀，放宽条件
                    pass
                else:
                    return None
            content = content.strip()
            img_match_prefix = check_prefix(content, conf().get("image_create_prefix",[""]))
            
            if img_match_prefix:
                content = content.replace(img_match_prefix, "", 1)
                context.type = ContextType.IMAGE_CREATE
            else:
                context.type = ctype  #需保持可能的SHARING类型，原句会把SHARING强变成TEXT，有误，故改之。  ContextType.TEXT

            context.content = content.strip()
            if "desire_rtype" not in context and conf().get("always_reply_voice") and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                context["desire_rtype"] = ReplyType.VOICE
        
        elif context.type == ContextType.VOICE:
            if "desire_rtype" not in context and conf().get("voice_reply_voice") and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                context["desire_rtype"] = ReplyType.VOICE
        
        return context



    def _handle(self, context: Context):
        if context is None or not context.content:
            return

        logger.debug("现执行到了 chat_channel.py - _handle 函数中 ready to handle context值=【{}】 补充输出context[“msg”]=【{}】".format(context, context["msg"]))
      

        #VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        # 这里是第1次黑名单过滤，第2次过滤只滤文字
        # 炳 解决问题：黑名单中的人单聊发来语音时，竟也去做语音识别，纯粹浪费。
        #       方法：预判，如果是 黑名单中的人单聊 ，则不要做 _generate_reply 
        #                （自然也不会在_generate_reply中去进一步做语音识别了）
        # 消息内容匹配过程，并处理content
        nick_name_black_list = conf().get("nick_name_black_list", [])
        from_user_nick_name = context["msg"].from_user_nickname
        if (                                            # 如发来的是  语音、图片、文件、公众号分享，且是黑名单中的人，则忽略跳过
            (context.type == ContextType.VOICE or context.type == ContextType.IMAGE or context.type == ContextType.FILE or context.type == ContextType.SHARING) and       
            context.IsSingleChat and       # 且是单聊
            from_user_nick_name and                     # 且发送者有呢称
            from_user_nick_name in nick_name_black_list # 且发送者呢称在黑名单中
        ):
            # 黑名单过滤
            logger.warning(f"chat_channel.py - _handle()中：黑名单中的人单聊发来【语音、图片、文件、公众号分享】，来者呢称'{from_user_nick_name}'在config.json配置的黑名单nick_name_black_list中，忽略（跳过，不处理），避免原代码的浪费去做语音识别等")
            return
        #AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

        #先由group-talker看一眼
        #先由MemorableTalker看一眼，如果MemorableTalker有回答，就不用再调用传统的_generate_reply了
        reply = Take_a_Look_Maybe_generate_reply(context)

        # 如果MemorableTalker没回答，但 又是必须回答的情况，则再调用传统的_generate_reply
        # 必须回答的情况：私聊  或  群聊被@了
        if (reply is None) and (context.IsSingleChat or (context.IsGroupChat and context.Being_at_Me_in_Group)) :
            # reply的构建步骤        
            reply = self._generate_reply(context)
        
        # 若 reply 为空，说明_generate_reply内部出错了，直接退出，不发任何错误消息给用户
        if reply is None: 
            return
        #否则如果reply是ERROR
        # 仅在单聊 且 是文件或分享 且 ReplyType.ERROR 时，才回复用户 出错的情况
        # 如有些文件类型无法处理或超过大小，或视频号分享 等 暂不支持的类型消息，就会返回 ReplyType.ERROR
        elif (context.IsSingleChat) and (context.type==ContextType.FILE or context.type==ContextType.SHARING) and (reply.type == ReplyType.ERROR) :
            self._send_reply(context, reply)

        else :
            logger.debug("[chat_channel] ready to decorate reply: {}".format(reply))

            # reply的包装步骤
            if reply and reply.content:
                reply = self._decorate_reply(context, reply)

                # reply的发送步骤
                self._send_reply(context, reply)



    #炳重构：试图转语音为文本，可能会失败（如语音识别失败）
    def _Try_to_Convert_Voice_to_Text(self, context):
        """
        处理语音消息，输入 Context 对象实例，输出 Reply 对象实例。
        
        :param context: Context 对象实例
        :return: Reply 对象实例
        """
        
        cmsg = context["msg"]
        cmsg.prepare()
        file_path = context.content
        wav_path = os.path.splitext(file_path)[0] + ".wav"
        
        try:
            any_to_wav(file_path, wav_path)
        except Exception as e:  # 转换失败，直接使用mp3，对于某些api，mp3也可以识别
            logger.warning("[chat_channel] any to wav error, use raw path. " + str(e))
            wav_path = file_path
        
        # 语音识别
        reply = super().build_voice_to_text(wav_path)
        
        # 删除临时文件
        try:
            os.remove(file_path)
            if wav_path != file_path:
                os.remove(wav_path)
        except Exception as e:
            pass
            # logger.warning("[chat_channel] delete temp file error: " + str(e))
        
        return reply



    def _generate_reply(self, context: Context, reply: Reply = Reply()) -> Reply:

        #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
        #《《《《 把 EventContext 的构建从原 紧凑 代码中 提取到外面，放到前面来，
        #《《《《 以便后面的reply = e_context["reply"]要用到
        e_context = EventContext(
            Event.ON_HANDLE_CONTEXT,
            {"channel": self, "context": context, "reply": reply},
        )

        # 有 2个地方可产生（EMIT）此事件：此处 与 bridge 中
        # 此处产生事件 不受炳的流程控制，执行流程会被插件抢走（抢走后不再走炳的流程），此处适合如：Godcmd
        # bridge中产生事件 受炳的流程控制，适合让LINKAI插件处理事件后得到所要的【识别、总结】结果
        #
        #所以，此处只要激发Godcmd插件的事件处理即可，不用激发其他的插件
        #产生（EMIT）事件 只给 【GODCMD插件】与【群聊总结插件】 处理
        e_context = PluginManager().emit_event_ONLY_FOR_PLUGIN_( ["GODCMD"], e_context )
        #
        # 炳注：每次都产生事件的原因：为了要利用Godcmd的 #stop #resume 功能，
        #       Godcmd 用 #stop #resume 暂停整个 C-o-W 的原理： 
        #       若 Godcmd 中的 isRunning 是 False（即 服务已暂停），则所有事件都“忽略跳过” BREAK_PASS
        #       所以 若要用 Godcmd 的暂停服务的功能，就必须每条接收到的消息都经Godcmd的事件处理走一遍
        # 需要每次都产生事件，才能由Godcmd插件来决定根据当前 isRunning 的状态要不要后面的流程继续走下去
        #  
        # #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
        

        reply = e_context["reply"]
        if not e_context.is_pass():
            logger.debug("[chat_channel] ready to handle context: type={}, content={}".format(context.type, context.content))
            
            ###########################################
            # 如果是 语音消息, 则偿试转为文本，若成功转为文本，则接下来按文本处理
            if context.type == ContextType.VOICE:  

                convertResultReply = self._Try_to_Convert_Voice_to_Text(context)
        
                # 如果语音识别失败
                if convertResultReply.type == ReplyType.ERROR or convertResultReply.content == "":
                    _send_info(context, f"语音识别失败，无法识别你说的话\n\n请发文字消息提问\n\n{convertResultReply.content}")
                    return convertResultReply
                
                #如果转成功（不是上面的ERROR类型），且回复类型是文本
                elif convertResultReply.type == ReplyType.TEXT: 
                    #语音识别后，给用户一个回馈，以免用户等得不耐烦（3次调用很费时：语音+1答+2答）
                    _send_info(e_context, f"你说：\n\n“{reply.content}”\n\n思考如何答你...")

                    # 炳：语音识别成功后，不要像从前那样：重新 组装一个新的文本类型的context
                    # 炳：直接给原context的TextizedText设为转换成功后的值。
                    context.TextizedText = convertResultReply.content
                    
            # 若经上面 语音转文本成功 后，可继续执行下面的代码处理转换后的文本        
            ###########################################
            # 如果是  文字 或 画图
            # 炳加：             或 TextizedText有值（非None）
            if context.type == ContextType.TEXT or context.type == ContextType.IMAGE_CREATE or (context.TextizedText is not None):  
                context["channel"] = e_context["channel"]

                #炳加：
                #如果是对 图片、语音、其他怪的引用 全都 回复 “我看不到你引用的内容”
                prefixes = ("「[图片]」", "「[该消息类型暂不能展示]」", "「[视频]」", "「[文件]")
                strReceivedMsg = context.content
                logger.debug(f"如果是对 图片、语音、其他怪的引用 全都 回复 “我看不到你引用的内容”，收到消息【{strReceivedMsg}】")
                if strReceivedMsg.startswith(prefixes):
                    _send_info(e_context, "看不了消息中的：\n❎视频号引用\n❎视频引用\n❎图片引用\n❎语音引用\n\n我能看见：\n✅文字消息引用\n\n如引用的是图片，请重发图片本身，我看见后，再问我与图片相关的问题。\n\n正在（看不了引用的情况下）尝试回答你...")
                    #发给LLM前 ，删除 [该消息类型暂不能展示] 这样的话，以免误导LLM
                    for prefix in prefixes:
                        context.content = context.content.removeprefix(prefix)

                #即使看不见引用，也试图回答用户
                reply = super().build_reply_content(context.TextizedText, context)
                #炳注：其实以上这句才是真正让bot去调用LLM回答的命令，


            # 如果是 图片消息，仅保存到本地（待用户下个问题时 可能会问有关图的问题）
            elif context.type == ContextType.IMAGE:  # 图片消息，当前仅做下载保存到本地的逻辑
                
                #VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
                #炳：应在这里跟用户说“收到图片，可在3分钟内问询与图片相关的问题”
                #   如果是  单聊  才说 “收到一张图片。。。。   群聊就静悄悄地存好图片（不发声）
                if context.IsSingleChat :
                    context["channel"] = e_context["channel"]
                    #如果上一张图还没有问答处理掉，又来一张图（一次发了多张图）
                    if memory.USER_IMAGE_CACHE.get(context["session_id"]) is not None:
                        reply = Reply(ReplyType.TEXT, "🖼️虽然收到多张图片，但只能针对最后一张图片提问（不要连续发多张图片。请发一张问一张）")
                    else :
                        reply = Reply(ReplyType.TEXT, "🖼️收到一张图片，在90秒可问与此图相关的问题（可一次问多个问题）")
                #AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

                # 无论是单聊 还是 群聊 都把图片存好记下
                memory.USER_IMAGE_CACHE[context["session_id"]] = {
                    "path": context.content,
                    "msg": context.get("msg")
                }


            # 如是 公众号分享 或 文件
            elif context.type == ContextType.SHARING or context.type == ContextType.FILE :  

                # VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
                # 炳改，使支持微信的“图文分享”
                # 由以下代码片断可知：微信的“图文分享”在content中就是一个URL链接。
                # elif itchat_msg["Type"] == SHARING:
                # self.ctype = ContextType.SHARING
                # self.content = itchat_msg.get("Url")
                logger.warning(f"[chat_channel.py]将处理微信的“公众号分享”或“上传的文件”: {context.content}")
                #
                #保持context.type为SHARING，在bridge.py中再调LINKAI处理。因发现deepseek读到的微信分享页面内容错误，估计微信页面用了些奇怪技术防止机器人读取。所以还是交给LINKAI处理吧，LINKAI已经弄通了微信页面的怪诡计
                #context.type = ContextType.TEXT #把类型改为文字文本类型，以便后面的处理不会遇到刁难
                #
                #以下2句是从最前面的TEXT的处理方法处抄来的
                context["channel"] = e_context["channel"] #不知何意，照抄之
                #下一句会在bridge中激发 LINKAI插件事件来处理
                reply = super().build_reply_content(f"{context.content}", context)
                # AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
                
            # 函数调用等，当前无默认逻辑
            elif context.type == ContextType.FUNCTION :  
                pass

            elif context.type == ContextType.JOIN_GROUP :
                return
            
            else:
                logger.warning("[chat_channel] unknown context type: {}".format(context.type))
                return

        return reply


    def _decorate_reply(self, context: Context, reply: Reply) -> Reply:

        #炳 增加子函数《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
        #  AI重构前的原代码     #《《《 在回答后附加：随机显示10种（或20种或更多，数量不限）小提示中的1种
        #                     # 生成一个0到9之间（包含0与9）的随机整数
        #                     x = random.randint(0, 9)
        #                     # 从JSON对象中拿 提示数组，共 10 个提示
        #                     hintArray = conf().get("random_hintStr_array",[""])
        #                     # 从10个提示中，随机取一个
        #                     hint = hintArray[x]
        #                     # 提示前加上分隔线字符串，组成：回复文本
        #                     reply_text = reply_text + """
        # ━━━━━━━━
        # """ 
        #                     + hint    
        def get_safe_random_hint(conf):
            # 从配置中获取提示数组
            hint_array = conf().get("random_hintStr_array", [])
            
            # 检查hint_array是否为空或不是列表
            if not isinstance(hint_array, list) or len(hint_array) == 0:
                return ""  # 如果hint_array无效，返回空字符串
            
            # 安全地生成随机索引
            random_index = random.randint(0, len(hint_array) - 1)
            
            # 安全地获取提示
            hint = hint_array[random_index] if 0 <= random_index < len(hint_array) else ""
            
            # 确保hint是字符串类型
            return str(hint)
        # 》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》


        if reply and reply.type:
            e_context = PluginManager().emit_event(
                EventContext(
                    Event.ON_DECORATE_REPLY,
                    {"channel": self, "context": context, "reply": reply},
                )
            )
            reply = e_context["reply"]
            desire_rtype = context.get("desire_rtype")
            if not e_context.is_pass() and reply and reply.type:
                if reply.type in self.NOT_SUPPORT_REPLYTYPE:
                    logger.error("[chat_channel]reply type not support: " + str(reply.type))
                    reply.type = ReplyType.ERROR
                    reply.content = "不支持发送的消息类型: " + str(reply.type)

                if reply.type == ReplyType.TEXT:
                    reply_text = reply.content
                    if desire_rtype == ReplyType.VOICE and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                        reply = super().build_text_to_voice(reply.content)
                        return self._decorate_reply(context, reply)
                    if context.IsGroupChat:
                        if not context.get("no_need_at", False):
                            reply_text = "@" + context["msg"].actual_user_nickname + "\n" + reply_text.strip()
                        reply_text = conf().get("group_chat_reply_prefix", "") + reply_text + conf().get("group_chat_reply_suffix", "")
                    else:
                        reply_text = conf().get("single_chat_reply_prefix", "") + reply_text + conf().get("single_chat_reply_suffix", "")
                    
                    #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
                    # 只在回答内容大于270字时，才附加随机提示。
                    # 若本就很短的有用回复，超50%都是添加的广告提示，会显得很啰嗦烦人
                    if len(reply_text) > 270 :
                        # 使用函数 安全地获取 随机提示
                        hint = get_safe_random_hint(conf)
                        reply_text = f"{reply_text}\n━━━━━━━\n\n👨🏻‍🔧{hint}"
                    # 》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》

                    reply.content = reply_text
                elif reply.type == ReplyType.ERROR or reply.type == ReplyType.INFO:
                    reply.content = "[" + str(reply.type) + "]\n" + reply.content
                elif reply.type == ReplyType.IMAGE_URL or reply.type == ReplyType.VOICE or reply.type == ReplyType.IMAGE or reply.type == ReplyType.FILE or reply.type == ReplyType.VIDEO or reply.type == ReplyType.VIDEO_URL:
                    pass
                else:
                    logger.error("[chat_channel] unknown reply type: {}".format(reply.type))
                    return
            if desire_rtype and desire_rtype != reply.type and reply.type not in [ReplyType.ERROR, ReplyType.INFO]:
                logger.warning("[chat_channel] desire_rtype: {}, but reply type: {}".format(context.get("desire_rtype"), reply.type))
            return reply

    def _send_reply(self, context: Context, reply: Reply):
        if reply and reply.type:
            e_context = PluginManager().emit_event(
                EventContext(
                    Event.ON_SEND_REPLY,
                    {"channel": self, "context": context, "reply": reply},
                )
            )
            reply = e_context["reply"]
            if not e_context.is_pass() and reply and reply.type:
                logger.debug("[chat_channel] ready to send reply: {}, context: {}".format(reply, context))
                self._send(reply, context)

    def _send(self, reply: Reply, context: Context, retry_cnt=0):
        try:
            self.send(reply, context)
        except Exception as e:
            logger.error("[chat_channel] sendMsg error: {}".format(str(e)))
            if isinstance(e, NotImplementedError):
                return
            logger.exception(e)
            if retry_cnt < 2:
                time.sleep(3 + 3 * retry_cnt)
                self._send(reply, context, retry_cnt + 1)

    def _success_callback(self, session_id, **kwargs):  # 线程正常结束时的回调函数
        logger.debug("\n⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎⬆︎此条问答所有流程结束Worker return success, session_id = {}\n\n\n".format(session_id))

    def _fail_callback(self, session_id, exception, **kwargs):  # 线程异常结束时的回调函数
        logger.exception("Worker return exception: {}".format(exception))

    def _thread_pool_callback(self, session_id, **kwargs):
        def func(worker: Future):
            try:
                worker_exception = worker.exception()
                if worker_exception:
                    self._fail_callback(session_id, exception=worker_exception, **kwargs)
                else:
                    self._success_callback(session_id, **kwargs)
            except CancelledError as e:
                logger.info("Worker cancelled, session_id = {}".format(session_id))
            except Exception as e:
                logger.exception("Worker raise exception: {}".format(e))
            with self.lock:
                self.sessions[session_id][1].release()

        return func

    def produce(self, context: Context):
        session_id = context["session_id"]
        with self.lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = [
                    Dequeue(),
                    threading.BoundedSemaphore(conf().get("concurrency_in_session", 4)),
                ]
            if context.type == ContextType.TEXT and context.content.startswith("#"):
                self.sessions[session_id][0].putleft(context)  # 优先处理管理命令
            else:
                self.sessions[session_id][0].put(context)

    # 消费者函数，单独线程，用于从消息队列中取出消息并处理
    def consume(self):
        while True:
            with self.lock:
                session_ids = list(self.sessions.keys())
                for session_id in session_ids:
                    context_queue, semaphore = self.sessions[session_id]
                    if semaphore.acquire(blocking=False):  # 等线程处理完毕才能删除
                        if not context_queue.empty():
                            context = context_queue.get()
                            logger.debug("[chat_channel] consume context: {}".format(context))
                            future: Future = handler_pool.submit(self._handle, context)
                            future.add_done_callback(self._thread_pool_callback(session_id, context=context))
                            if session_id not in self.futures:
                                self.futures[session_id] = []
                            self.futures[session_id].append(future)
                        elif semaphore._initial_value == semaphore._value + 1:  # 除了当前，没有任务再申请到信号量，说明所有任务都处理完毕
                            self.futures[session_id] = [t for t in self.futures[session_id] if not t.done()]
                            assert len(self.futures[session_id]) == 0, "thread pool error"
                            del self.sessions[session_id]
                        else:
                            semaphore.release()
            time.sleep(0.1)

    # 取消session_id对应的所有任务，只能取消排队的消息和已提交线程池但未执行的任务
    def cancel_session(self, session_id):
        with self.lock:
            if session_id in self.sessions:
                for future in self.futures[session_id]:
                    future.cancel()
                cnt = self.sessions[session_id][0].qsize()
                if cnt > 0:
                    logger.info("Cancel {} messages in session {}".format(cnt, session_id))
                self.sessions[session_id][0] = Dequeue()

    def cancel_all_session(self):
        with self.lock:
            for session_id in self.sessions:
                for future in self.futures[session_id]:
                    future.cancel()
                cnt = self.sessions[session_id][0].qsize()
                if cnt > 0:
                    logger.info("Cancel {} messages in session {}".format(cnt, session_id))
                self.sessions[session_id][0] = Dequeue()


def check_prefix(content, prefix_list):
    if not prefix_list:
        return None
    for prefix in prefix_list:
        if content.startswith(prefix):
            return prefix
    return None


def check_contain(content, keyword_list):
    if content is None:
        return None
    
    if not keyword_list:
        return None
    
    for ky in keyword_list:
        if content.find(ky) != -1:
            return True
    
    return None
