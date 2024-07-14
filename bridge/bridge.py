from bot.bot_factory import create_bot
from bridge.context import Context
from bridge.reply import Reply
from common import const
from common.log import logger
from common.singleton import singleton
from config import conf
from translate.factory import create_translator
from voice.factory import create_voice


@singleton
class Bridge(object):
    # 炳：在这里添加类变量,来确定用哪种LLM，是Basic还是Advan
    class_bool_NowNeedAdvanLLM = False

    def __init__(self):
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
                # 创建 3 个 chat bot
                # 创建 LINKAI 用的 chat bot
                self.bots[typename]["LinkAI"] = create_bot(const.LINKAI)
                # 创建 BasicLLM 用的 QWEN_DASHSCOPE chat bot
                self.bots[typename]["BasicLLM"] = create_bot(const.QWEN_DASHSCOPE)
                # 创建 AdvanLLM 用的 CHATGPT chat bot(One-api中再指向GPT4,4o,claude等)
                self.bots[typename]["AdvanLLM"] = create_bot(const.CHATGPT)
                #
                logger.debug("《《《《 Bridge().get_bot 函数内：创建3个同时存在的chat bot完成：[ LinkAI, BasicLLM(QWEN_DASHSCOPE), AdvanLLM(chatGPT)(One-api中再指向GPT4,4o,claude等) ]")
                #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》
            
            elif typename == "translate":
                self.bots[typename] = create_translator(self.btype[typename])

        #《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《《
        # 当创建好，或已经存在时，则返回 bot
        # 用不用LINKAI随时在变，取最新的情况，根据不同情况(要基本LLM还是高级LLM)而返回不同的bot
        bool_use_linkai = conf()["use_linkai"]
        if typename == "chat" :
            if Bridge.class_bool_NowNeedAdvanLLM :      #必须首先判 是否要高级LLM，否则一问2答 2次都会拿到LinkAI
                return self.bots[typename]["AdvanLLM"]
            else :
                if bool_use_linkai :
                    return self.bots[typename]["LinkAI"]
                else :
                    return self.bots[typename]["BasicLLM"] 
        else :
            return self.bots[typename]
        #》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》》


    
    def get_bot_type(self, typename):
        return self.btype[typename]




    def fetch_reply_content(self, query, context: Context) -> Reply:
        #炳：先用基础LLM拿到回复
        Bridge.class_bool_NowNeedAdvanLLM = False
        context["gpt_model"] = conf()["basic_llm_gpt_model"]
        BasicReply = self.get_bot("chat").reply(query, context)

        #炳：基础LLM没发现 不当敏感内容，则 一问二答，再问高级LLM
        if conf().get("warning_reply_for_inappropriate_content") not in BasicReply.content:

            #炳：再用高级LLM拿到回复
            Bridge.class_bool_NowNeedAdvanLLM = True
            context["gpt_model"] = conf()["advan_llm_gpt_model"]
            AdvanReply = self.get_bot("chat").reply(query, context)
            Bridge.class_bool_NowNeedAdvanLLM = False  #重置回 False，确保后续的调用都使用BasicLLM

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
