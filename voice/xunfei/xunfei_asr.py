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

import websocket
import json
import base64
import time
import wave
import ssl
import threading
from tenacity import retry, stop_after_attempt, wait_exponential

class Ws_Param:
    # ... (keep the existing Ws_Param class implementation)

class WebSocketClient:
    def __init__(self, url, on_message, on_error, on_close):
        self.url = url
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        self.ws = None

    def connect(self):
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.on_open = self.on_open
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_open(self, ws):
        print("WebSocket connection opened")

    def send(self, data):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.ws.send(data)
        else:
            raise Exception("WebSocket is not connected")

    def close(self):
        if self.ws:
            self.ws.close()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def xunfei_asr(APPID, APISecret, APIKey, BusinessArgsASR, AudioFile):
    global whole_dict
    whole_dict = {}

    wsParam = Ws_Param(APPID=APPID, APISecret=APISecret,
                       APIKey=APIKey, BusinessArgs=BusinessArgsASR,
                       AudioFile=AudioFile)
    
    wsUrl = wsParam.create_url()
    
    def on_message(ws, message):
        global whole_dict
        try:
            response = json.loads(message)
            code = response["code"]
            sid = response["sid"]
            if code != 0:
                errMsg = response["message"]
                print(f"sid:{sid} call error:{errMsg} code is:{code}")
            else:
                process_result(response["data"]["result"])
        except Exception as e:
            print(f"Error processing message: {e}")

    def process_result(result):
        global whole_dict
        sn = result["sn"]
        if "rg" in result:
            rep_start, rep_end = result["rg"]
            for i in range(rep_start, rep_end + 1):
                whole_dict.pop(i, None)
        
        results = "".join(w["w"] for i in result["ws"] for w in i["cw"])
        whole_dict[sn] = results

    def on_error(ws, error):
        print(f"WebSocket error: {error}")

    def on_close(ws, close_status_code, close_msg):
        print(f"WebSocket connection closed: {close_status_code} - {close_msg}")

    client = WebSocketClient(wsUrl, on_message, on_error, on_close)
    
    def run_websocket():
        client.connect()
    
    websocket_thread = threading.Thread(target=run_websocket)
    websocket_thread.start()

    # Wait for WebSocket connection to establish
    time.sleep(2)

    try:
        with wave.open(AudioFile, "rb") as fp:
            frame_size = 8000
            interval = 0.04
            status = 0  # 0: first frame, 1: continue frame, 2: last frame

            while True:
                buf = fp.readframes(frame_size)
                if not buf:
                    status = 2  # last frame

                d = {
                    "data": {
                        "status": status,
                        "format": "audio/L16;rate=16000",
                        "audio": base64.b64encode(buf).decode('utf-8'),
                        "encoding": "raw"
                    }
                }

                if status == 0:
                    d["common"] = wsParam.CommonArgs
                    d["business"] = wsParam.BusinessArgs
                    
                client.send(json.dumps(d))

                if status == 2:
                    break

                status = 1
                time.sleep(interval)

    except Exception as e:
        print(f"Error during audio processing: {e}")
    finally:
        client.close()
        websocket_thread.join()

    whole_words = "".join(whole_dict[i] for i in sorted(whole_dict.keys()))
    return whole_words

# Usage example
# result = xunfei_asr(APPID, APISecret, APIKey, BusinessArgsASR, AudioFile)
# print(result)