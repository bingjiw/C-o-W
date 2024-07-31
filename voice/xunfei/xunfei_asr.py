# -*- coding:utf-8 -*-
#
#  Author: njnuko 
#  Email: njnuko@163.com 
#
#  这个文档是基于官方的demo来改的，固体官方demo文档请参考官网
#
#  语音听写流式 WebAPI 接口调用示例 接口文档（必看）：https://doc.xfyun.cn/rest_api/语音听写（流式版）.html
#  webapi 听写服务参考帖子（必看）：http://bbs.xfyun.cn/forum.php?mod=viewthread&tid=38947&extra=
#  语音听写流式WebAPI 服务，热词使用方式：登陆开放平台https://www.xfyun.cn/后，找到控制台--我的应用---语音听写（流式）---服务管理--个性化热词，
#  设置热词
#  注意：热词只能在识别的时候会增加热词的识别权重，需要注意的是增加相应词条的识别率，但并不是绝对的，具体效果以您测试为准。
#  语音听写流式WebAPI 服务，方言试用方法：登陆开放平台https://www.xfyun.cn/后，找到控制台--我的应用---语音听写（流式）---服务管理--识别语种列表
#  可添加语种或方言，添加后会显示该方言的参数值
#  错误码链接：https://www.xfyun.cn/document/error-code （code返回错误码时必看）
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# 炳把以下所有代码替换为了：ChatGPT4o改进后的代码
# 代码说明
# 重试机制：xunfei_asr 函数添加了 max_retries 参数，默认尝试 3 次。如果在某次尝试中失败，会等待 2 秒后再重试。
# 错误处理：在每次尝试中捕获异常并记录失败信息。
# 日志记录：打印失败的尝试信息，帮助你调试和分析问题。
# 这些改进可以帮助你在网络不稳定的情况下提高代码的健壮性和可靠性。如果问题仍然存在，可以考虑进一步优化网络环境，或者联系讯飞的技术支持获取帮助。

import websocket
import datetime
import hashlib
import base64
import hmac
import json
from urllib.parse import urlencode
import time
import ssl
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
import _thread as thread
import os
import wave

STATUS_FIRST_FRAME = 0
STATUS_CONTINUE_FRAME = 1
STATUS_LAST_FRAME = 2

global whole_dict
global wsParam

class Ws_Param(object):
    def __init__(self, APPID, APIKey, APISecret, BusinessArgs, AudioFile):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.AudioFile = AudioFile
        self.BusinessArgs = BusinessArgs
        self.CommonArgs = {"app_id": self.APPID}

    def create_url(self):
        #原来连中国的，老是超时 丢包。改连迅飞新加坡的服务器 
        #url = 'wss://ws-api.xfyun.cn/v2/iat'
        url = 'wss://iat-api-sg.xf-yun.com/v2/iat'
        
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        #此行是原来连中国的，老是超时 丢包。
        #signature_origin = "host: " + "ws-api.xfyun.cn" + "\n"
        signature_origin = "host: " + "iat-api-sg.xf-yun.com" + "\n"

        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/iat " + "HTTP/1.1"
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
        authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
            self.APIKey, "hmac-sha256", "host date request-line", signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        v = {
            "authorization": authorization,
            "date": date,
            
            # 此行是原来连中国的，老是超时 丢包。
            # "host": "ws-api.xfyun.cn"
            
            #语音识别改连迅飞新加坡的服务器 
            "host": "iat-api-sg.xf-yun.com" 
        }
        url = url + '?' + urlencode(v)
        return url

def on_message(ws, message):
    global whole_dict
    try:
        code = json.loads(message)["code"]
        sid = json.loads(message)["sid"]
        if code != 0:
            errMsg = json.loads(message)["message"]
            print("sid:%s call error:%s code is:%s" % (sid, errMsg, code))
        else:
            temp1 = json.loads(message)["data"]["result"]
            data = json.loads(message)["data"]["result"]["ws"]
            sn = temp1["sn"]
            if "rg" in temp1.keys():
                rep = temp1["rg"]
                rep_start = rep[0]
                rep_end = rep[1]
                for sn in range(rep_start, rep_end + 1):
                    whole_dict.pop(sn, None)
                results = ""
                for i in data:
                    for w in i["cw"]:
                        results += w["w"]
                whole_dict[sn] = results
            else:
                results = ""
                for i in data:
                    for w in i["cw"]:
                        results += w["w"]
                whole_dict[sn] = results
    except Exception as e:
        print("receive msg, but parse exception:", e)

def on_error(ws, error):
    print("### error:", error)

def on_close(ws, a, b):
    print("### closed ###")

def on_open(ws):
    global wsParam

    def run(*args):
        frameSize = 8000
        intervel = 0.04
        status = STATUS_FIRST_FRAME

        with wave.open(wsParam.AudioFile, "rb") as fp:
            while True:
                buf = fp.readframes(frameSize)
                if not buf:
                    status = STATUS_LAST_FRAME
                if status == STATUS_FIRST_FRAME:
                    d = {"common": wsParam.CommonArgs,
                         "business": wsParam.BusinessArgs,
                         "data": {"status": 0, "format": "audio/L16;rate=16000", "audio": str(base64.b64encode(buf), 'utf-8'), "encoding": "raw"}}
                    d = json.dumps(d)
                    ws.send(d)
                    status = STATUS_CONTINUE_FRAME
                elif status == STATUS_CONTINUE_FRAME:
                    d = {"data": {"status": 1, "format": "audio/L16;rate=16000",
                                  "audio": str(base64.b64encode(buf), 'utf-8'),
                                  "encoding": "raw"}}
                    ws.send(json.dumps(d))
                elif status == STATUS_LAST_FRAME:
                    d = {"data": {"status": 2, "format": "audio/L16;rate=16000",
                                  "audio": str(base64.b64encode(buf), 'utf-8'),
                                  "encoding": "raw"}}
                    ws.send(json.dumps(d))
                    time.sleep(1)
                    break
                time.sleep(intervel)
        ws.close()

    thread.start_new_thread(run, ())

def xunfei_asr(APPID, APISecret, APIKey, BusinessArgsASR, AudioFile, max_retries=3):
    global whole_dict
    global wsParam
    whole_dict = {}
    wsParam1 = Ws_Param(APPID=APPID, APISecret=APISecret, APIKey=APIKey, BusinessArgs=BusinessArgsASR, AudioFile=AudioFile)
    wsParam = wsParam1

    for attempt in range(max_retries):
        try:
            websocket.enableTrace(False)
            wsUrl = wsParam.create_url()
            ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
            ws.on_open = on_open
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

            whole_words = ""
            for i in sorted(whole_dict.keys()):
                whole_words += whole_dict[i]

            if whole_words:
                return whole_words
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    return ""

# 示例调用
if __name__ == "__main__":
    APPID = "your_app_id"
    APIKey = "your_api_key"
    APISecret = "your_api_secret"
    BusinessArgsASR = {"domain": "iat", "language": "zh_cn", "accent": "mandarin", "vinfo": 1, "vad_eos": 10000}
    AudioFile = "path_to_your_audio_file.wav"

    result = xunfei_asr(APPID, APISecret, APIKey, BusinessArgsASR, AudioFile)
    print(result)
