"""
voice factory
"""
import json
import os

##############取迅飞语言识别的参数

# Load configuration from xunfei/config.json
config_path = os.path.join(os.path.dirname(__file__), 'xunfei/config.json')
with open(config_path, 'r') as config_file:
    config = json.load(config_file)

# Extract values from the configuration
XunFei_APPID = config['APPID']
XunFei_APIKey = config['APIKey']
XunFei_APISecret = config['APISecret']

###############################


def create_voice(voice_type):
    """
    可视作建一个语音识别的机器人  create a voice instance
    :param voice_type: voice type code
    :return: voice instance
    """
    if voice_type == "baidu":
        from voice.baidu.baidu_voice import BaiduVoice

        return BaiduVoice()
    elif voice_type == "google":
        from voice.google.google_voice import GoogleVoice
        return GoogleVoice()
    
    
    elif voice_type == "openai":
        from voice.openai.openai_voice import OpenaiVoice
        return OpenaiVoice()
    

    elif voice_type == "pytts":
        from voice.pytts.pytts_voice import PyttsVoice

        return PyttsVoice()
    elif voice_type == "azure":
        from voice.azure.azure_voice import AzureVoice

        return AzureVoice()
    elif voice_type == "elevenlabs":
        from voice.elevent.elevent_voice import ElevenLabsVoice

        return ElevenLabsVoice()

    elif voice_type == "linkai":
        from voice.linkai.linkai_voice import LinkAIVoice

        return LinkAIVoice()
    elif voice_type == "ali":
        from voice.ali.ali_voice import AliVoice

        return AliVoice()
    elif voice_type == "edge":
        from voice.edge.edge_voice import EdgeVoice

        return EdgeVoice()
    


    elif voice_type == "xunfei":
        from voice.xunfei.xunfei_voice_by_BJ_with_websocket_singapore_server import XunfeiVoice
        return XunfeiVoice(XunFei_APPID, XunFei_APIKey, XunFei_APISecret)


    raise RuntimeError
