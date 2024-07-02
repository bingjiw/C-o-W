#《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
#《《《《《 引入另一个 专门判断回答是否是“很抱歉，我无法”之类的 函数 .py 文件
#《《《《《 判断 AI回复的文本 决定要不要实时搜索
from channel.ANSWER_APOLOGY import analyze_text_features__need_search
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

try:
    from voice.audio_convert import any_to_wav
except Exception as e:
    pass

handler_pool = ThreadPoolExecutor(max_workers=8)  # 处理消息的线程池


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
        context = Context(ctype, content)
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
            context["openai_api_key"] = user_data.get("openai_api_key")
            context["gpt_model"] = user_data.get("gpt_model")
            if context.get("isgroup", False):
                group_name = cmsg.other_user_nickname
                group_id = cmsg.other_user_id

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
                    logger.debug(f"No need reply, groupName not in whitelist, group_name={group_name}")
                    return None
                context["session_id"] = session_id
                context["receiver"] = group_id
            else:
                context["session_id"] = cmsg.other_user_id
                context["receiver"] = cmsg.other_user_id
            e_context = PluginManager().emit_event(EventContext(Event.ON_RECEIVE_MESSAGE, {"channel": self, "context": context}))
            context = e_context["context"]
            if e_context.is_pass() or context is None:
                return context
            if cmsg.from_user_id == self.user_id and not config.get("trigger_by_self", True):
                logger.debug("[chat_channel]self message skipped")
                return None

        # 消息内容匹配过程，并处理content
        if ctype == ContextType.TEXT:
            if first_in and "」\n- - - - - - -" in content:  # 初次匹配 过滤引用消息
                logger.debug(content)
                logger.debug("[chat_channel]reference query skipped")
                return None

            nick_name_black_list = conf().get("nick_name_black_list", [])
            if context.get("isgroup", False):  # 群聊
                # 校验关键字
                match_prefix = check_prefix(content, conf().get("group_chat_prefix"))
                match_contain = check_contain(content, conf().get("group_chat_keyword"))
                flag = False
                if context["msg"].to_user_id != context["msg"].actual_user_id:
                    if match_prefix is not None or match_contain is not None:
                        flag = True
                        if match_prefix:
                            content = content.replace(match_prefix, "", 1).strip()
                    if context["msg"].is_at:
                        nick_name = context["msg"].actual_user_nickname
                        if nick_name and nick_name in nick_name_black_list:
                            # 黑名单过滤
                            logger.warning(f"[chat_channel] Nickname {nick_name} in In BlackList, ignore")
                            return None

                        logger.info("[chat_channel]receive group at")
                        if not conf().get("group_at_off", False):
                            flag = True
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
                if not flag:
                    if context["origin_ctype"] == ContextType.VOICE:
                        logger.info("[chat_channel]receive group voice, but checkprefix didn't match")
                    return None
            else:  # 单聊
                nick_name = context["msg"].from_user_nickname
                if nick_name and nick_name in nick_name_black_list:
                    # 黑名单过滤
                    logger.warning(f"[chat_channel] Nickname '{nick_name}' in In BlackList, ignore")
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
                context.type = ContextType.TEXT
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

        #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《

        #《《《《《《 子函数：停用LINKAI插件
        def DISABLE_LINKAI():    
            logger.debug("《《《《 子函数内：将要 停用LINKAI插件 ")

            ###因已经在_generate_reply中做了控制：只在需要LINKAI时，才产生事件emit_event。  
            ###不用LINKAI时，就不会emit_event产生事件了
            ###所以我后来觉得没必要 disable/enable _pluging 了，这样可以避免相同事件被多个相同的 plugin 实例听到和处理的问题
            ###
            ### 停用插件
            ###success = PLUGIN_MANager_instance.disable_plugin("LINKAI")
            ###if success:
            ###    logger.debug(f"《《《《 子函数内：停用 LINKAI 插件 成功")
            ###else:
            ###    logger.debug(f"《《《《 子函数内：停用 LINKAI 插件 失败")

            logger.debug(f"《《《《 子函数内：将要 把环境配置use_linkai设为False，重设bot（重选答题的GPT，让LINKAI的bot下岗）")
            conf()["use_linkai"] = False
            #reset会导致bot的session丢失，失去记忆。故不要执行：bridge.Bridge().reset_bot()                
            
            # Change the model type
            Bridge().btype["chat"] = const.CHATGPT
            logger.debug(f"《《《《 子函数内：已把bridge.py中的model改为{const.GPT35}")

            return          


        #《《《《《《 子函数：启用LINKAI插件
        def ENABLE_LINKAI():  
            logger.debug("《《《《《 子函数内：启用 LINKAI 插件 ")

            ###因已经在_generate_reply中做了控制：只在需要LINKAI时，才产生事件emit_event。  
            ###不用LINKAI时，就不会emit_event产生事件了
            ###所以我后来觉得没必要 disable/enable _pluging 了，这样可以避免相同事件被多个相同的 plugin 实例听到和处理的问题
            ###            
            # 启用插件
            ###success, message = PLUGIN_MANager_instance.enable_plugin("LINKAI")
            ###if success:
            ###    logger.debug(f"《《《《 子函数内：启用 LINKAI 插件 成功: {message}")
            ###else:
            ###    logger.debug(f"《《《《 子函数内：启用 LINKAI 插件 失败: {message}")  
            

            logger.debug(f"《《《《 子函数内：将要 把环境配置use_linkai设为True，重设bot（重选答题的GPT，让LINKAI的bot上岗）")
            conf()["use_linkai"] = True
            #reset会导致bot的session丢失，失去记忆。故不要执行：bridge.Bridge().reset_bot()                
                           
            # Change the model type
            Bridge().btype["chat"] = const.LINKAI
            logger.debug(f"《《《《 子函数内：已把bridge.py中的model改为{const.LINKAI}")

            return          


        logger.debug("《《《《【先禁外援，首考(问)不及格(答不出)，再请外援代答】 首考前先：停用LINKAI插件（禁外援） ")
        DISABLE_LINKAI()

        logger.debug("》》》》示首考前的 context 以作对比检查 [WX] ready to handle context值={}".format(context))
        #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
        
        # reply的构建步骤        
        reply = self._generate_reply(context)

        #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《

        logger.debug("《《《《 判断【首考的回答及格否?】再决定要不要请外援实时搜索。根据第1次产生的回答，来判断是否需要第2次调用（引发外援LINKAI插件来处理）")
        text = None if reply is None else reply.content
        analyze_result_string, final_score = analyze_text_features__need_search(text)
        logger.debug("\n" + analyze_result_string)
        
        # analyze_text_features__need_search 如果 need_search 结果值较小，则不需要再 上网实时搜索
        # 3.5 这个“及格分数线” 是拿多十多个回复测试后，得到的一个较好的 分界值
        if final_score < 3.5 :
            logger.debug("《《《《【首考及格】（首考成功过关）不需要再请外援上网实时搜索。不需要 第2次调用 _generate_reply（来引发LINKAI插件来处理）")
        else :
            logger.debug("《《《《【首考不及格】（首考没过）第1次的回答是“很抱歉...”，需要进行 第2次调用 _generate_reply（来引发LINKAI插件来处理）")
        
            logger.debug("《《《《 【允许请外援】（需上网搜索）：启用 LINKAI 插件")
            ENABLE_LINKAI()

            logger.debug("》》》》 输出 第1次后 第2次前 的 context 以作对比检查 context值={}".format(context))
        
            logger.debug("《《《《【请外援来答】执行：第2次调用 _generate_reply 以让LINKAI产生回答 ")
            reply = self._generate_reply(context)

            logger.debug("》》》》 输出补考【第2次考试】后的 context 以作对比检查 context值={}".format(context))
        
            logger.debug("《《《《【考完了，禁外援】：停用 LINKAI 插件 ")
            DISABLE_LINKAI()

            logger.debug("《《《《【用🌎标记答案是补考来的】在回答的开头加上🌎说明这是互联网实时搜索得来的回答")
            reply.content = "🌎" + reply.content 

        logger.debug("《《《《 overwrite 《《《《【考试结束】《《《《（首考及或补考）完成《《《《")
        
        #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
        
        logger.debug("[chat_channel] ready to decorate reply: {}".format(reply))

        # reply的包装步骤
        if reply and reply.content:
            reply = self._decorate_reply(context, reply)

            # reply的发送步骤
            self._send_reply(context, reply)

    def _generate_reply(self, context: Context, reply: Reply = Reply()) -> Reply:
        #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
        #《《《《 把 EventContext 的构建从原 紧凑 代码中 提取到外面，放到前面来，
        #《《《《 以便后面的reply = e_context["reply"]要用到
        e_context = EventContext(
            Event.ON_HANDLE_CONTEXT,
            {"channel": self, "context": context, "reply": reply},
        )

        #《《《《 只在需要LINKAI时，才产生事件emit_event。  不用LINKAI时，就不会emit_event产生事件了
        if conf()["use_linkai"] == True:
            e_context = PluginManager().emit_event( e_context )        
        #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
        
        reply = e_context["reply"]
        if not e_context.is_pass():
            logger.debug("[chat_channel] ready to handle context: type={}, content={}".format(context.type, context.content))
            if context.type == ContextType.TEXT or context.type == ContextType.IMAGE_CREATE:  # 文字和图片消息
                context["channel"] = e_context["channel"]
                reply = super().build_reply_content(context.content, context)
            elif context.type == ContextType.VOICE:  # 语音消息
                cmsg = context["msg"]
                cmsg.prepare()
                file_path = context.content
                wav_path = os.path.splitext(file_path)[0] + ".wav"
                try:
                    any_to_wav(file_path, wav_path)
                except Exception as e:  # 转换失败，直接使用mp3，对于某些api，mp3也可以识别
                    logger.warning("[chat_channel]any to wav error, use raw path. " + str(e))
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
                    # logger.warning("[chat_channel]delete temp file error: " + str(e))

                if reply.type == ReplyType.TEXT:
                    new_context = self._compose_context(ContextType.TEXT, reply.content, **context.kwargs)
                    if new_context:
                        reply = self._generate_reply(new_context)

                        #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
                        logger.debug("《《《 语音识别后，把识别出的文本替换原来context中的语音，经修改context.type与context.content传出去。这样，当语音提问需要调LINKAI搜索时，再调LINKAI时就无需再做一遍语音识别了。")
                        # 《《《 这样，当语音提问需要调LINKAI搜索时，再调LINKAI时就无需再做一遍语音识别了。
                        context.type = ContextType.TEXT
                        context.content = new_context.content                        
                        #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
                    
                    else:
                        return
            elif context.type == ContextType.IMAGE:  # 图片消息，当前仅做下载保存到本地的逻辑
                memory.USER_IMAGE_CACHE[context["session_id"]] = {
                    "path": context.content,
                    "msg": context.get("msg")
                }
            elif context.type == ContextType.SHARING:  # 分享信息，当前无默认逻辑
                pass
            elif context.type == ContextType.FUNCTION or context.type == ContextType.FILE:  # 文件消息及函数调用等，当前无默认逻辑
                pass
            else:
                logger.warning("[chat_channel] unknown context type: {}".format(context.type))
                return
        return reply

    def _decorate_reply(self, context: Context, reply: Reply) -> Reply:
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
                    if context.get("isgroup", False):
                        if not context.get("no_need_at", False):
                            reply_text = "@" + context["msg"].actual_user_nickname + "\n" + reply_text.strip()
                        reply_text = conf().get("group_chat_reply_prefix", "") + reply_text + conf().get("group_chat_reply_suffix", "")
                    else:
                        reply_text = conf().get("single_chat_reply_prefix", "") + reply_text + conf().get("single_chat_reply_suffix", "")
                    
                    #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
                    #《《《 在回答后附加：随机显示3种小提示中的一种
                    # 生成一个0到1之间的随机数
                    x = random.random()
                
                    logger.debug("《《《 在回答后附加：随机显示3种小提示中的一种，随机数={}".format(x))
                    # 根据随机数的范围显示不同的情况
                    if 0 <= x < 0.1:
                        reply_text = reply_text + """
━━━━━━━━
开启【朗读回答】的方法：微信 > 我 > 设置 > 关怀模式【开启】> 听文字消息【开启】，返回聊天，轻点一下『回答的文字』"""
                    

                    
                    elif 0.1 <= x < 0.4:
                        reply_text = reply_text + """
━━━━━━━━
国产GPT增强版 https://n.we8.ai 文字出图 写简历 心理咨询 小红书文案 有多种预设面具角色可选 免费"""
                    
                    
                    
                    elif 0.4 <= x < 0.5:
                        reply_text = reply_text + """ """

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
        logger.debug("Worker return success, session_id = {}".format(session_id))

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
    if not keyword_list:
        return None
    for ky in keyword_list:
        if content.find(ky) != -1:
            return True
    return None
