# 炳 2021-07-01 改写自讯飞官方示例代码，使用websocket连接新加坡服务器，实现语音识别功能

import websocket
import json
import base64
import time
import ssl
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
import hmac
import hashlib
from urllib.parse import urlencode
import _thread as thread
import logging

import sys
import os
# Add parent directory to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(parent_dir)
#若不加上面5行，会报错：ModuleNotFoundError: No module named 'bridge'
from bridge.reply import Reply, ReplyType


logger = logging.getLogger(__name__)

STATUS_FIRST_FRAME = 0  # The identity of the first frame
STATUS_CONTINUE_FRAME = 1  # Intermediate frame identification
STATUS_LAST_FRAME = 2  # The identity of the last frame

class Ws_Param(object):
    def __init__(self, APPID, APIKey, APISecret, AudioFile):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.AudioFile = AudioFile

        self.CommonArgs = {"app_id": self.APPID}
        self.BusinessArgs = {"domain": "iat", "language": "zh_cn", "accent": "mandarin", "vinfo": 1, "vad_eos": 10000}

    def create_url(self):
        url = 'wss://iat-api-sg.xf-yun.com/v2/iat'
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + "iat-api-sg.xf-yun.com" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/iat " + "HTTP/1.1"
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
            self.APIKey, "hmac-sha256", "host date request-line", signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')

        v = {
            "authorization": authorization,
            "date": date,
            "host": "iat-api-sg.xf-yun.com"
        }
        url = url + '?' + urlencode(v)
        return url


def on_message(ws, message):
    try:
        code = json.loads(message)["code"]
        sid = json.loads(message)["sid"]
        if code != 0:
            errMsg = json.loads(message)["message"]
            print("sid:%s call error:%s code is:%s" % (sid, errMsg, code))
        else:
            data = json.loads(message)["data"]["result"]["ws"]
            result = ""
            for i in data:
                for w in i["cw"]:
                    result += w["w"]
            print("sid:%s call success!,data is:%s" % (sid, json.dumps(data, ensure_ascii=False)))
            if not hasattr(ws, 'full_result'):
                ws.full_result = ""
            ws.full_result += result
    except Exception as e:
        print("receive msg,but parse exception:", e)


def on_error(ws, error):
    print("### 炳版讯飞语音识别 error:", error)

def on_close(ws, close_status_code, close_msg):
    print("### 炳版讯飞语音识别 closed ###")

def on_open(ws):
    def run(*args):
        frameSize = 8000
        intervel = 0.04
        status = STATUS_FIRST_FRAME

        with open(ws.wsParam.AudioFile, "rb") as fp:
            while True:
                buf = fp.read(frameSize)
                if not buf:
                    status = STATUS_LAST_FRAME
                if status == STATUS_FIRST_FRAME:
                    d = {"common": ws.wsParam.CommonArgs,
                         "business": ws.wsParam.BusinessArgs,
                         "data": {"status": 0, "format": "audio/L16;rate=16000",
                                  "audio": str(base64.b64encode(buf), 'utf-8'),
                                  "encoding": "raw"}}
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

class XunfeiVoice:
    def __init__(self, APPID, APIKey, APISecret):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret

    def voiceToText(self, voice_file):
        try:
            logger.debug("[Xunfei] voice file name={}".format(voice_file))
            wsParam = Ws_Param(self.APPID, self.APIKey, self.APISecret, voice_file)
            websocket.enableTrace(False)
            wsUrl = wsParam.create_url()
            ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
            ws.on_open = on_open
            ws.wsParam = wsParam
            ws.full_result = ""
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
            text = ws.full_result if ws.full_result else "No result obtained"
            logger.info("炳版讯飞语音识别 结果:> {}".format(text))
            reply = Reply(ReplyType.TEXT, text)
        except Exception as e:
            logger.warn("XunfeiVoice init failed: %s, ignore " % e)
            reply = Reply(ReplyType.ERROR, "炳版讯飞语音识别 出错了:> {}".format(str(e)))
        return reply