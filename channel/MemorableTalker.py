# MemorableTalker.py

from channel.ChatRoomLog import *
from bridge.reply import *
from bridge.context import *
import datetime

def Take_a_Look_Maybe_generate_reply(aTextizedContextMsg: TextizedContextMsg) -> Reply:
    """
    根据给定的 context 生成回复。

    参数:
    aTextizedContextMsg (dict): 包含消息和上下文信息的字典。

    返回:
    Reply: 生成的回复，如果没有合适的回复则返回 None。
    """
    

    #记 日期
    #记 收到的消息
    WriteLog2Files(aTextizedContextMsg.RoomName, "", f"　\n　\n{aTextizedContextMsg.RoomName}\n{datetime.datetime.now().strftime('%d日%H:%M:%S')} 【{aTextizedContextMsg.SpeakerNickName}】说：\n{aTextizedContextMsg.TextizedText}\n")
    
    #记分析
    #WriteLog2Files(aTextizedContextMsg.RoomName, "    ", f"分析:aaaaaa\nbbbbbbbbbbb\nccccccccccccc\n")

    #返回 None 表示：静听分析，但不说话（没到说话的时机）
    #返回 Reply 表示：静听分析后，有回答
    return None