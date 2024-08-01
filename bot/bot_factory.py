"""
channel factory
"""
from common import const


#炳注：不用import SessionManager，因仅传参数，并没真正使用此类。得益于python的动态类型特性
#  you don't need to import SessionManager in bot_factory.py if you are not directly using the class is due to Python's dynamic typing and flexible import system. In Python, you can pass objects around without needing to explicitly import their types in every file where they are used, as long as the objects are passed correctly at runtime.
# In statically typed languages like Java or C#, you typically need to import or include the class definitions because the compiler needs to know the types of all objects at compile time. This is necessary for type checking and ensuring that the code adheres to the language's type system.


def create_bot(bot_type, shared_session_manager=None):
    """
    create a bot_type instance
    :param bot_type: bot type code
    :return: bot instance
    """
    if bot_type == const.BAIDU:
        # 替换Baidu Unit为Baidu文心千帆对话接口
        # from bot.baidu.baidu_unit_bot import BaiduUnitBot
        # return BaiduUnitBot()
        from bot.baidu.baidu_wenxin import BaiduWenxinBot
        return BaiduWenxinBot()


    #炳，免费LLM
    elif bot_type == "ChatGPTBot.FreeLLM":
        # ChatGPT 网页端web接口
        from bot.chatgpt.chat_gpt_bot import ChatGPTBot
        return ChatGPTBot("FreeLLM", session_manager=shared_session_manager)

    #炳，基本LLM
    elif bot_type == "ChatGPTBot.BasicLLM":
        # ChatGPT 网页端web接口
        from bot.chatgpt.chat_gpt_bot import ChatGPTBot
        return ChatGPTBot("BasicLLM", session_manager=shared_session_manager)
    
    #炳，高级LLM
    elif bot_type == "ChatGPTBot.AdvanLLM":
        # ChatGPT 网页端web接口
        from bot.chatgpt.chat_gpt_bot import ChatGPTBot
        return ChatGPTBot("AdvanLLM")

    #原来的代码，不传参数指定，则默认是用 BasicLLM
    elif bot_type == const.CHATGPT:
        # ChatGPT 网页端web接口
        from bot.chatgpt.chat_gpt_bot import ChatGPTBot
        return ChatGPTBot()


    elif bot_type == const.OPEN_AI:
        # OpenAI 官方对话模型API
        from bot.openai.open_ai_bot import OpenAIBot
        return OpenAIBot()

    elif bot_type == const.CHATGPTONAZURE:
        # Azure chatgpt service https://azure.microsoft.com/en-in/products/cognitive-services/openai-service/
        from bot.chatgpt.chat_gpt_bot import AzureChatGPTBot
        return AzureChatGPTBot()

    elif bot_type == const.XUNFEI:
        from bot.xunfei.xunfei_spark_bot import XunFeiBot
        return XunFeiBot()

    elif bot_type == const.LINKAI:
        from bot.linkai.link_ai_bot import LinkAIBot
        return LinkAIBot()

    elif bot_type == const.CLAUDEAI:
        from bot.claude.claude_ai_bot import ClaudeAIBot
        return ClaudeAIBot()
    elif bot_type == const.CLAUDEAPI:
        from bot.claudeapi.claude_api_bot import ClaudeAPIBot
        return ClaudeAPIBot()
    elif bot_type == const.QWEN:
        from bot.ali.ali_qwen_bot import AliQwenBot
        return AliQwenBot()
    elif bot_type == const.QWEN_DASHSCOPE:
        from bot.dashscope.dashscope_bot import DashscopeBot
        return DashscopeBot()
    elif bot_type == const.GEMINI:
        from bot.gemini.google_gemini_bot import GoogleGeminiBot
        return GoogleGeminiBot()

    elif bot_type == const.ZHIPU_AI:
        from bot.zhipuai.zhipuai_bot import ZHIPUAIBot
        return ZHIPUAIBot()

    elif bot_type == const.MOONSHOT:
        from bot.moonshot.moonshot_bot import MoonshotBot
        return MoonshotBot()
    
    elif bot_type == const.MiniMax:
        from bot.minimax.minimax_bot import MinimaxBot
        return MinimaxBot()


    raise RuntimeError
