# encoding:utf-8

import time

import openai
import openai.error
import requests

from bot.bot import Bot
from bot.chatgpt.chat_gpt_session import ChatGPTSession
from bot.openai.open_ai_image import OpenAIImage
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.token_bucket import TokenBucket
from config import conf, load_config


# OpenAI对话模型API (可用)
class ChatGPTBot(Bot, OpenAIImage):
    def __init__(self, Which_LLM_To_Create="BasicLLM", session_manager=None):
        super().__init__()
        
        #存一份api_key，以便在reply_text（不传入api_key时）中使用
        self.the_API_KEY_gave_me_when_I_born = conf().get(Which_LLM_To_Create)["open_ai_api_key"]
        # set the default api_key
        openai.api_key = self.the_API_KEY_gave_me_when_I_born

        #存一份api_base
        self.the_API_BASE_gave_me_when_I_born = conf().get(Which_LLM_To_Create)["open_ai_api_base"]
        if self.the_API_BASE_gave_me_when_I_born:
            openai.api_base = self.the_API_BASE_gave_me_when_I_born

        proxy = conf().get("proxy")
        if proxy:
            openai.proxy = proxy
        if conf().get("rate_limit_chatgpt"):
            self.tb4chatgpt = TokenBucket(conf().get("rate_limit_chatgpt", 20))

        # 炳注：
        #以上的 openai.api_key, openai.api_base, openai.proxy, 都是库的全局变量，无法给每个bot实例设置不同的值
        #只有下方的 model 可以给每个bot实例设置不同的值
        # SessionManager及其子类ChatGPTSession 中的model仅用于计算令牌数量。
        
        #self.sessions = SessionManager(ChatGPTSession, model=conf().get(Which_LLM_To_Create)["model"] or "gpt-3.5-turbo")
        # 炳：原如上，现改为BasicLLM与FreeLLM这2个BOT用共享一个sessions     Use the provided session_manager or create a new one
        self.sessions = session_manager or SessionManager(ChatGPTSession, model=conf().get(Which_LLM_To_Create)["model"] or "gpt-3.5-turbo")
        
        self.args = {
            "model": conf().get(Which_LLM_To_Create)["model"] or "gpt-3.5-turbo",  # 对话模型的名称
            "temperature": conf().get("temperature", 0.9),  # 值在[0,1]之间，越大表示回复越具有不确定性
            # "max_tokens":4096,  # 回复最大的字符数
            "top_p": conf().get("top_p", 1),
            "frequency_penalty": conf().get("frequency_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "presence_penalty": conf().get("presence_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "request_timeout": conf().get("request_timeout", None),  # 请求超时时间，openai接口默认设置为600，对于难问题一般需要较长时间
            "timeout": conf().get("request_timeout", None),  # 重试超时时间，在这个时间内，将会自动重试
        }

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT or (context.TextizedText is not None) :
            logger.info("[CHATGPT] query={}".format(query))

            session_id = context["session_id"]
            reply = None
            clear_memory_commands = conf().get("clear_memory_commands", ["#清除记忆"])
            if query in clear_memory_commands:
                self.sessions.clear_session(session_id)
                reply = Reply(ReplyType.INFO, "记忆已清除")
            elif query == "#清除所有":
                self.sessions.clear_all_session()
                reply = Reply(ReplyType.INFO, "所有人记忆已清除")
            elif query == "#更新配置":
                load_config()
                reply = Reply(ReplyType.INFO, "配置已更新")
            if reply:
                return reply
            session = self.sessions.session_query(query, session_id)
            logger.debug("[CHATGPT] session query={}".format(session.messages))

            api_key = context.get("openai_api_key")
            model = context.get("gpt_model")
            new_args = None
            if model:
                new_args = self.args.copy()
                new_args["model"] = model
            # if context.get('stream'):
            #     # reply in stream
            #     return self.reply_text_stream(query, new_query, session_id)

            reply_content = self.reply_text(session, api_key, args=new_args)
            logger.debug(
                "[CHATGPT] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                    reply_content["completion_tokens"],
                )
            )
            if reply_content["completion_tokens"] == 0 and len(reply_content["content"]) > 0:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
            elif reply_content["completion_tokens"] > 0:
                self.sessions.session_reply(reply_content["content"], session_id, reply_content["total_tokens"])
                reply = Reply(ReplyType.TEXT, reply_content["content"])
            else:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
                logger.debug("[CHATGPT] reply {} used 0 tokens.".format(reply_content))
            return reply

        elif context.type == ContextType.IMAGE_CREATE:
            ok, retstring = self.create_img(query, 0)
            reply = None
            if ok:
                reply = Reply(ReplyType.IMAGE_URL, retstring)
            else:
                reply = Reply(ReplyType.ERROR, retstring)
            return reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply



    def reply_text(self, session: ChatGPTSession, api_key=None, args=None, retry_count=0) -> dict:
        """
        call openai's ChatCompletion to get the answer
        :param session: a conversation session
        :param session_id: session id
        :param retry_count: retry count
        :return: {}
        """
        try:
            if conf().get("rate_limit_chatgpt") and not self.tb4chatgpt.get_token():
                raise openai.error.RateLimitError("RateLimitError: rate limit exceeded")

            # 炳注：原此句胡说八道：害人：if api_key == None, the default openai.api_key will be used

            # 炳：plugin_summary\main.py 直接调用reply_text会出错（因api_key=None），因为没有传入api_key
            #    所以在此对没有转入api_key的情况进行处理
            if api_key == None:
                api_key = self.the_API_KEY_gave_me_when_I_born

            if args is None:
                args = self.args

            # 炳：打印出真正去调LLM时，调用发出的参数
            import json
            logger.debug(f"ChatGPTBot真正去调LLM时，调用发出哪些：\napi_key={api_key}\nmessages={session.messages}\nargs={json.dumps(args, ensure_ascii=False, indent=2)}")

            # 炳：这句是 真正去调 LLM    
            response = openai.ChatCompletion.create(api_key=api_key, messages=session.messages, **args)
            # logger.debug("[CHATGPT] response={}".format(response))
            # logger.info("[ChatGPT] reply={}, total_tokens={}".format(response.choices[0]['message']['content'], response["usage"]["total_tokens"]))
            


            #VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            #如果答案中含有“> **end-searching**”，说明是调gpt-4o产生的啰嗦答案，则要进行修剪
            #炳：拿出回复的内容，以去掉：开头的几行引导信息和参考的网页链接，样例如下
            # > search("Trump shooting latest news July 18 2024")
            # > mclick(["1", "3", "5", "6", "8"])
            # > search error
            #
            # > mclick(["2", "10", "12", "13", "17"])
            # > **end-searching**
            #
            # 昨天，特朗普总统在宾夕法尼亚州的集会上遭遇枪击。嫌疑人托马斯·马修·克鲁克斯从屋顶向舞台开枪。特朗普受轻伤，但情况稳定。一名消防员在事件中遇难，另有两人受伤。美国特勤局迅速行动，嫌疑人已被拘留。特朗普称此事件为“神的保佑”，并呼吁全国团结[Trump shooting latest updates](https://ny1.com/nyc/all-boroughs/news/2024/07/14/trump-shooting-live-updates-assassination-attempt-rally)【8†source】。
            # --------又一例，如下--------
            # > search("astaxanthin half-life 2024")
            # > search("current half-life of astaxanthin 2024")
            # > mclick(["1", "11", "6", "14", "9"])
            # > mclick([0, 1, 5, 6, 10])
            # > **end-searching**

            # 根据最新资料，虾青素的
            # > **end-searching**

            # 半
            # > **end-searching**

            # 衰期大约为16小时。这意味着在服用后，大约16小时后体内的虾青素浓度会减少一半[New study uncovers astaxanthin's anti-inflammatory potential against lipopolysaccharide-induced inflammation](https://medicalxpress.com/news/2024-05-uncovers-astaxanthin-anti-inflammatory-potential.html)[New Astaxanthin Formulation Said to Provide Ideal, More-Absorbable Dose](https://www.nutritionaloutlook.com/view/new-astaxanthin-formulation-said-provide-ideal-more-absorbable-dose)[Astaxanthin - Wikipedia](https://en.wikipedia.org/wiki/Astaxanthin)。虾青素作为🌍一种🌍脂🌍最新的研究表明，虾青溶素的性半物衰质期大，其约为在16到体20小时内可以。这一持续数据更表长明，时间虾青，素在通常体在内能够血维持清相中对稳定的可浓度检测，到支持其的抗氧时间化和长抗炎达功能72小时[Molecules | Free Full-Text | The Role of Astaxanthin as a Nutraceutical in Health and Age-Related Conditions](https://www.mdpi.com/1420-3049/27/21/7167)[New study uncovers astaxanthin's anti-inflammatory potential against lipopolysaccharide-induced inflammation](https://medicalxpress.com/news/2024-05-uncovers-astaxanthin-anti-inflammatory-potential.html)【7†source】[Evidence-based Analysis on Supplements & Nutrition | Examine](https://examine.com/supplements/astaxanthin/research/)。

            # 。希望这些信息对你有帮助！如果还有其他问题，欢迎继续提问。

            strResponseText = response.choices[0]["message"]["content"]
            if "> **end-searching**" in strResponseText:
                import re
                # 删除以 `>` 后面跟随空格和小写字母开头的每一行
                cleaned_text = re.sub(r'^> [a-z].*$', '', strResponseText, flags=re.MULTILINE)
                # 删除带有 URL 的方括号部分
                cleaned_text = re.sub(r'\[.*?\]\((?:http|https)://\S+\)', '', cleaned_text)
                # 删除类似 【7†source】 的字串
                cleaned_text = re.sub(r'【\d+†source】', '', cleaned_text)
                #删除  > **end-searching**
                cleaned_text = cleaned_text.replace("> **end-searching**\n","")
                # 删除文章开头多余的换行与空格
                cleaned_text = re.sub(r'^\s*', '', cleaned_text, flags=re.MULTILINE)
                #加🌐，表示 是 gpt-4o搜索得来的，故意与LINKAI的地球不同样子
                cleaned_text = "🌐"+cleaned_text
                logger.debug("原始啰唆答案：\n{}\n🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚🪚\n修剪后的干净答案：\n{}".format(strResponseText, cleaned_text))
            else:
                cleaned_text = strResponseText

            return {
                "total_tokens": response["usage"]["total_tokens"],
                "completion_tokens": response["usage"]["completion_tokens"],
                "content": cleaned_text,
            }
        except Exception as e:
            need_retry = retry_count < 2

            #炳《《《《 针对用户问了 **相关的敏感问题 引发的异常 的处理
            #炳《《《《 Input data may contain inappropriate content.
            exception_message = str(e)  # Convert the exception to a string
            if "data may contain inappropriate content" in exception_message:
                textToReplyUser = exception_message + conf().get("warning_reply_for_inappropriate_content")

                result = {"completion_tokens": 0, "content": textToReplyUser}
            else:
                result = {"completion_tokens": 0, "content": "我现在有点累了，等会再来吧"}
            
            if isinstance(e, openai.error.RateLimitError):
                logger.warn("[CHATGPT] RateLimitError: {}".format(e))
                result["content"] = f"我现在很忙，已接近回答问题的极限能力（每分钟{conf().get('rate_limit_chatgpt')}个）。\n\n再等我2分钟,一有空就回答你\n\n2分钟后再问我\n\n若几次都没答，请让技术员 bingjiw 增加我的能力"
                if need_retry:
                    time.sleep(20)
            elif isinstance(e, openai.error.Timeout):
                logger.warn("[CHATGPT] Timeout: {}".format(e))
                result["content"] = "我没有收到你的消息"
                if need_retry:
                    time.sleep(5)
            elif isinstance(e, openai.error.APIError):
                logger.warn("[CHATGPT] Bad Gateway: {}".format(e))
                result["content"] = "网络故障，请稍候再问。如果几次都不行，请联系技术员 bingjiw"
                if need_retry:
                    time.sleep(10)
            elif isinstance(e, openai.error.APIConnectionError):
                logger.warn("[CHATGPT] APIConnectionError: {}".format(e))
                result["content"] = "我连接不到你的网络"
                if need_retry:
                    time.sleep(5)
            else:
                logger.exception("[CHATGPT] Exception: {}".format(e))
                need_retry = False
                self.sessions.clear_session(session.session_id)

            if need_retry:
                logger.warn("[CHATGPT] 第{}次重试".format(retry_count + 1))
                return self.reply_text(session, api_key, args, retry_count + 1)
            else:
                return result


class AzureChatGPTBot(ChatGPTBot):
    def __init__(self):
        super().__init__()
        openai.api_type = "azure"
        openai.api_version = conf().get("azure_api_version", "2023-06-01-preview")
        self.args["deployment_id"] = conf().get("azure_deployment_id")

    def create_img(self, query, retry_count=0, api_key=None):
        text_to_image_model = conf().get("text_to_image")
        if text_to_image_model == "dall-e-2":
            api_version = "2023-06-01-preview"
            endpoint = conf().get("azure_openai_dalle_api_base","open_ai_api_base")
            # 检查endpoint是否以/结尾
            if not endpoint.endswith("/"):
                endpoint = endpoint + "/"
            url = "{}openai/images/generations:submit?api-version={}".format(endpoint, api_version)
            api_key = conf().get("azure_openai_dalle_api_key","open_ai_api_key")
            headers = {"api-key": api_key, "Content-Type": "application/json"}
            try:
                body = {"prompt": query, "size": conf().get("image_create_size", "256x256"),"n": 1}
                submission = requests.post(url, headers=headers, json=body)
                operation_location = submission.headers['operation-location']
                status = ""
                while (status != "succeeded"):
                    if retry_count > 3:
                        return False, "图片生成失败"
                    response = requests.get(operation_location, headers=headers)
                    status = response.json()['status']
                    retry_count += 1
                image_url = response.json()['result']['data'][0]['url']
                return True, image_url
            except Exception as e:
                logger.error("create image error: {}".format(e))
                return False, "图片生成失败"
        elif text_to_image_model == "dall-e-3":
            api_version = conf().get("azure_api_version", "2024-02-15-preview")
            endpoint = conf().get("azure_openai_dalle_api_base","open_ai_api_base")
            # 检查endpoint是否以/结尾
            if not endpoint.endswith("/"):
                endpoint = endpoint + "/"
            url = "{}openai/deployments/{}/images/generations?api-version={}".format(endpoint, conf().get("azure_openai_dalle_deployment_id","text_to_image"),api_version)
            api_key = conf().get("azure_openai_dalle_api_key","open_ai_api_key")
            headers = {"api-key": api_key, "Content-Type": "application/json"}
            try:
                body = {"prompt": query, "size": conf().get("image_create_size", "1024x1024"), "quality": conf().get("dalle3_image_quality", "standard")}
                submission = requests.post(url, headers=headers, json=body)
                image_url = submission.json()['data'][0]['url']
                return True, image_url
            except Exception as e:
                logger.error("create image error: {}".format(e))
                return False, "图片生成失败"
        else:
            return False, "图片生成失败，未配置text_to_image参数"
