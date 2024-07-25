#《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
#《《《《《 引入另一个 专门判断回答是否是“很抱歉，我无法”之类的 函数 .py 文件
#《《《《《 判断 AI回复的文本 决定要不要实时搜索
from channel.ANSWER_APOLOGY import analyze_text_features__need_search

from bot.bot_factory import create_bot
from bridge.context import Context,ContextType
from bridge.reply import Reply
from common import const
from common.log import logger
from common.singleton import singleton
from config import conf
from translate.factory import create_translator
from voice.factory import create_voice
from common import memory
from bot.chatgpt.chat_gpt_bot import ChatGPTBot 

@singleton
class Bridge(object):

    def __init__(self):
        # 炳：原先是写成类变量,但说singleton的类变量访问有问题，所以改为实例变量。
        # 来确定get_bot时返回哪种LLM，是Basic还是Advan
        self.the_Bot_I_Want = "BasicLLM"

        self.btype = {
            "chat": const.CHATGPT,
            "voice_to_text": conf().get("voice_to_text", "openai"),
            "text_to_voice": conf().get("text_to_voice", "google"),
            "translate": conf().get("translate", "baidu"),
        }
        # 这边取配置的模型
        bot_type = conf().get("bot_type")
        if bot_type:
            self.btype["chat"] = bot_type
        else:
            model_type = conf().get("model") or const.GPT35
            if model_type in ["text-davinci-003"]:
                self.btype["chat"] = const.OPEN_AI
            if conf().get("use_azure_chatgpt", False):
                self.btype["chat"] = const.CHATGPTONAZURE
            if model_type in ["wenxin", "wenxin-4"]:
                self.btype["chat"] = const.BAIDU
            if model_type in ["xunfei"]:
                self.btype["chat"] = const.XUNFEI
            if model_type in [const.QWEN]:
                self.btype["chat"] = const.QWEN
            if model_type in [const.QWEN_TURBO, const.QWEN_PLUS, const.QWEN_MAX]:
                self.btype["chat"] = const.QWEN_DASHSCOPE
            if model_type and model_type.startswith("gemini"):
                self.btype["chat"] = const.GEMINI
            if model_type in [const.ZHIPU_AI]:
                self.btype["chat"] = const.ZHIPU_AI
            if model_type and model_type.startswith("claude-3"):
                self.btype["chat"] = const.CLAUDEAPI

            if model_type in ["claude"]:
                self.btype["chat"] = const.CLAUDEAI

            if model_type in ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]:
                self.btype["chat"] = const.MOONSHOT

            if model_type in ["abab6.5-chat"]:
                self.btype["chat"] = const.MiniMax

            if conf().get("use_linkai") and conf().get("linkai_api_key"):
                self.btype["chat"] = const.LINKAI
                if not conf().get("voice_to_text") or conf().get("voice_to_text") in ["openai"]:
                    self.btype["voice_to_text"] = const.LINKAI
                if not conf().get("text_to_voice") or conf().get("text_to_voice") in ["openai", const.TTS_1, const.TTS_1_HD]:
                    self.btype["text_to_voice"] = const.LINKAI

        self.bots = {}
        self.chat_bots = {}

    # 模型对应的接口
    def get_bot(self, typename):
        if self.bots.get(typename) is None:
            logger.info("create bot {} for {}".format(self.btype[typename], typename))
            if typename == "text_to_voice":
                self.bots[typename] = create_voice(self.btype[typename])
            elif typename == "voice_to_text":
                self.bots[typename] = create_voice(self.btype[typename])
            elif typename == "chat":

                #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
                # chat bot有3个，使self.bots["chat"]指向一个dict, 
                # 此dict含3个键值对，键为string型: 
                #   LinkAI -> LINKAI BOT,  
                #   BasicLLM -> QWEN_DASHSCOPE,
                #   AdvanLLM -> CHATGPT (One-api中再指向GPT4,4o,claude等)
                #
                # 初始化 self.bots[typename] 为一个字典
                self.bots[typename] = {}
                #
                # 创建 几 个 chat bot
                # 创建 LINKAI 用的 chat bot
                #
                # 创建 BasicLLM 用的 CHATGPT chat bot(One-api中再指向 Deepseek-v2, qwen-max 等 高级LLM)
                self.bots[typename]["BasicLLM"] = create_bot("ChatGPTBot.BasicLLM")
                #
                # 创建 AdvanLLM 用的 CHATGPT chat bot(One-api中再指向GPT4,4o,claude等 高级LLM)
                self.bots[typename]["AdvanLLM"] = create_bot("ChatGPTBot.AdvanLLM")
                #
                # 自带搜索能力的SearchableLLM: XUNFEI 的 Spark Max 》》经试搜索效果不好
                # self.bots[typename]["SearchableLLM"] = create_bot(const.XUNFEI)
                # LinkAI充值额度用完后将废弃LINKAI搜索。将来有gpt-4-all等可直接上网搜索答案的LLM
                #self.bots[typename]["SearchableLLM"] = create_bot(const.LINKAI)
                # 【识图】和【搜索】共用同一个LINKAI bot
                self.bots[typename]["LinkAI"] = create_bot(const.LINKAI)
                #
                logger.debug("《《《《 Bridge().get_bot 函数内：创建几个同时存在的chat bot完成：[ LinkAI, BasicLLM(QWEN_DASHSCOPE), AdvanLLM(chatGPT)(One-api中再指向GPT4,4o,claude等) ]")
                #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
            
            elif typename == "translate":
                self.bots[typename] = create_translator(self.btype[typename])


        if typename == "chat" :

            #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
            # 当创建好，或已经存在时，则返回 bot
            # 根据 实例变量 the_Bot_I_Want ，要啥bot 给啥bot 
            result_bot = self.bots[typename][self.the_Bot_I_Want]
            self.the_Bot_I_Want = "BasicLLM" #马上恢复为默认的 基本LLM的bot
            return result_bot
            # 》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》

        else :
            return self.bots[typename]
        


    
    def get_bot_type(self, typename):
        return self.btype[typename]



    #炳：本函数中 只处理 "chat" 的文本问答。不用考虑语音的处理，语音由另一个兄弟函数fetch_voice_to_text处理
    def fetch_reply_content(self, query, context: Context) -> Reply:
        #炳：本函数中 用 self.bots["chat"]["BasicLLM"] 会出错，因为self.bots["chat"]还没创建
        #炳：所以，都要用self.get_bot("chat"), 此函数中若bot还没创建，它会创建

        #如果3分钟内有上传过图片，则认为需要识图
        needRecognizeImage = memory.USER_IMAGE_CACHE.get( context["session_id"] ) is not None

        #如果需要识图（那么就不用特地问基础LLM并判断要不要上网找答案了）
        if needRecognizeImage :
            # 🚩🚩调用：LinkAI
            self.the_Bot_I_Want = "LinkAI"
            strQuerySendToLinkAI = f"先描述这张图片整体，再一一描述图片中的所有细节。图中如有文字，写出所有文字。图中如有人物，则分析人物的动作、表情、面容、体态、年纪、服饰、心情。最后参考此图回答问题：{query}"
            #因LINKAI自带搜索，所以识图的时候 应该也能上网搜索的。
            BasicReply = self.get_bot("chat").reply(strQuerySendToLinkAI, context)        
            #
            logger.debug("正在bridge.py - fetch_reply_content函数中：在回答的开头加上🖼️说明需要识图（3分钟内有上传过图片）")
            BasicReply.content = "🖼️" + BasicReply.content 

        else :

            #不用识图，则先问基础LLM，再根据回答决定要不要上网搜索。
            #炳：先用基础LLM 偿试拿 回复
            context["gpt_model"] = conf().get("BasicLLM")["model"]
            # 🚩🚩调用：基本LLM
            self.the_Bot_I_Want = "BasicLLM"
            BasicReply = self.get_bot("chat").reply(query, context)

            text = None if BasicReply is None else BasicReply.content
            analyze_result_string, final_score = analyze_text_features__need_search(text)
            logger.debug("\n" + analyze_result_string)
                
            # analyze_text_features__need_search 如果 need_search 结果值较小，则不需要再 上网实时搜索
            # 3.5 这个“及格分数线” 是拿多十多个回复测试后，得到的一个较好的 分界值
            if final_score < 3.5 :
                logger.debug("《《《《 基础LLM 已得到答案。不用上网搜索。")
                needOnlineSearch = False
                strQuerySendToLinkAI = f"{query}"
            else :
                logger.debug("《《《《 基础LLM 的知识库无答案。需要 上网🌎搜索 找答案")
                needOnlineSearch = True
                strQuerySendToLinkAI = f"上网搜索：{query}"

            #如果需要搜索，则用LINKAI机器人
            if needOnlineSearch :
                # 🚩🚩调用：LinkAI
                self.the_Bot_I_Want = "LinkAI"
                BasicReply = self.get_bot("chat").reply(strQuerySendToLinkAI, context)            
                #
                logger.debug("正在bridge.py - fetch_reply_content函数中：在回答的开头加上🌎说明这是互联网实时搜索得来的回答")
                BasicReply.content = "🌎" + BasicReply.content 

        # 到此，基础LLM 肯定已得到答案

        #炳：如果 基础LLM 返回说有：不当敏感内容（图片也有可能会导致LLM产生色情或政治的敏感内容的答案）
        if "data may contain inappropriate content" in BasicReply.content :
            strWarning = conf().get("warning_reply_for_inappropriate_content")
            BasicReply.content = f"{BasicReply.content}\n\n{strWarning}"

        #炳：基础LLM没发现 不当敏感内容，则 一问二答，再问高级LLM
        else :

            # 如果用过LINKAI，就把LINKAI的最近添加的session中的内容copy给BasicLLM一份。
            # 这样 BasicLLM的Session 也能知道【搜索】或【问图】的结果内容, 下次问答时就能用到
            if needRecognizeImage or needOnlineSearch :                               #不能用这句来判断，因为get_bot后会马上把这个变量改为BasicLLM    if self.the_Bot_I_Want == "LinkAI" :
                self.the_Bot_I_Want = "BasicLLM"
                BasicBot = self.get_bot("chat")
                BasicBot.sessions.session_reply(BasicReply.content, context["session_id"])    
                logger.debug("把LINKAI的最近添加的session中的内容copy给BasicLLM一份。这样 BasicLLM的Session 也能知道【搜索】或【问图】的结果内容, 下次问答时就能用到。")

            if needRecognizeImage :
                #把图像识别的内容也给AdvanLLM的Session知道一下,以便后面顺畅自然的问答
                self.the_Bot_I_Want = "AdvanLLM"
                AdvanBot = self.get_bot("chat")
                AdvanBot.sessions.session_reply(BasicReply.content, context["session_id"])
                logger.debug("把图像识别的结果答案也给AdvanLLM的Session知道一下,以便后面顺畅自然的问答")
                strQueryToLLM = f"根据刚才描述图片的文字，回答问题：{query}"
            else :
                strQueryToLLM = query
        
            #炳：再用高级LLM拿到回复，
            # 因得到了识图的文字答案，所以AdvanLLM也能仅通过识图的答案文字来回答用户的问题 
            # (看不到图，仅通过听到对图的描述 来“盲答”用户的问题)
            context["gpt_model"] = conf().get("AdvanLLM")["model"]
            # 🚩🚩调用：高级LLM
            self.the_Bot_I_Want = "AdvanLLM"
            AdvanReply = self.get_bot("chat").reply(strQueryToLLM, context)

            #炳：合并2个回复 到一个回复中
            BasicReply.content = f"{BasicReply.content}\n━━━━━━━━\n\n👽{AdvanReply.content}"
        
        return BasicReply



    def fetch_voice_to_text(self, voiceFile) -> Reply:
        return self.get_bot("voice_to_text").voiceToText(voiceFile)

    def fetch_text_to_voice(self, text) -> Reply:
        return self.get_bot("text_to_voice").textToVoice(text)

    def fetch_translate(self, text, from_lang="", to_lang="en") -> Reply:
        return self.get_bot("translate").translate(text, from_lang, to_lang)

    def find_chat_bot(self, bot_type: str):
        if self.chat_bots.get(bot_type) is None:
            self.chat_bots[bot_type] = create_bot(bot_type)
        return self.chat_bots.get(bot_type)

    def reset_bot(self):
        """
        重置bot路由
        """
        self.__init__()
