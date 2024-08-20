# encoding:utf-8

from enum import Enum

import re

def sanitize_filename(filename):
    """
    去除字符串中不能用于文件名的字符
    :param filename: 原始文件名字符串
    :return: 处理后的文件名字符串
    """
    # 定义不能用于文件名的字符
    invalid_chars = r'[\/:*?"<>|]'
    
    # 使用正则表达式替换掉这些字符
    sanitized_filename = re.sub(invalid_chars, "", filename)
    
    return sanitized_filename

# # 示例
# original_filename = "invalid:/file*name?.txt"
# clean_filename = sanitize_filename(original_filename)
# print(clean_filename)  # 输出: invalidfilename.txt



class ContextType(Enum):
    TEXT = 1  # 文本消息
    VOICE = 2  # 音频消息
    IMAGE = 3  # 图片消息
    FILE = 4  # 文件信息
    VIDEO = 5  # 视频信息
    SHARING = 6  # 分享信息

    IMAGE_CREATE = 10  # 创建图片命令
    ACCEPT_FRIEND = 19 # 同意好友请求
    JOIN_GROUP = 20  # 加入群聊
    PATPAT = 21  # 拍了拍
    FUNCTION = 22  # 函数调用
    EXIT_GROUP = 23 #退出


    def __str__(self):
        return self.name


class Context:
    def __init__(self, type: ContextType = None, content=None, kwargs=dict()):
        self.type = type
        self.content = content
        self.kwargs = kwargs

    def __contains__(self, key):
        if key == "type":
            return self.type is not None
        elif key == "content":
            return self.content is not None
        else:
            return key in self.kwargs

    def __getitem__(self, key):
        if key == "type":
            return self.type
        elif key == "content":
            return self.content
        else:
            return self.kwargs[key]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __setitem__(self, key, value):
        if key == "type":
            self.type = value
        elif key == "content":
            self.content = value
        else:
            self.kwargs[key] = value

    def __delitem__(self, key):
        if key == "type":
            self.type = None
        elif key == "content":
            self.content = None
        else:
            del self.kwargs[key]

    def __str__(self):
        return "Context(type={}, content={}, kwargs={})".format(self.type, self.content, self.kwargs)




#炳加的代码
#文本化的上下文消息，作为原Context的子类，增加了一个TextizedText属性，用于存储文本化的消息内容    
#只在读取TextizedText且为None时才去转化非文本类型的内容为文本，
# 并赋给TextizedText，因此只需转化一次
# 第2次再读取TextizedText时无需再转化
class TextizedContextMsg(Context):
    def __init__(self, type: ContextType = None, content=None, kwargs=dict()):
        
        ###################
        #内部 实例变量
        self._textized_text = None
        self._room_name = None

        ###################
        #公开 实例变量，外部像访问属性一样可直接访问
        self.Is_at_Me_in_Group = False 
        self.GroupName = None
        self.GroupID = None

        #说话人的昵称，单聊时为对方昵称，群聊时为说话人昵称
        self.SpeakerNickName = None

        #很重要的标志信息：在群聊中，是否被@了。
        #因若被@，则必须要回答。
        #否则group-talker可答 可不答
        self.Being_at_Me_in_Group = False

        super().__init__(type, content, kwargs)

    
    def getTextizedText(self):
        if self._textized_text is None:
            #只在TextizedText为None时
            # 才去转化非文本类型的内容为文本，

            #如原本就是文本类型，直接把文本内容给TextizedText
            if self.type == ContextType.TEXT:
                self._textized_text = self.content

            #如果是图片类型，调用Bridge的Recognize_Image_and_return_Text_Description_of_Image方法，返回图片的文本描述 
            elif self.type == ContextType.IMAGE:
                from bridge.bridge import Bridge
                aReplyOfImage = Bridge().Recognize_Image_and_return_Text_Description_of_Image(self)
                self._textized_text = f"[图片]:{aReplyOfImage.content}"

            else :
                self._textized_text = f"[此消息类型暂无TextizedText]{self.content}"

        #如果 _textized_text 已经有值后，则返回 _textized_text
        return self._textized_text



    def __str__(self):
        return "TextizedContextMsg(type={}, content={}, kwargs={}, TextizedText={})".format(
            self.type, self.content, self.kwargs, self._textized_text
        )


    #是否是群聊
    @property
    def IsGroupChat(self):
        return super().get("isgroup", False)
    

    #是否是单聊
    @property
    def IsSingleChat(self):
        return not self.IsGroupChat
    

    #sessionID聊天的会话thread的ID
    @property
    def SessionID(self):
        return super()["session_id"]
    

    #当回复此消息时，发给谁，也就是： 回复的接收者
    @property
    def ReceiverID_WhenReply(self):
        return super()["receiver"]
    


    #聊天房间名，单聊时为对方昵称，群聊时为群名。并去除不能用于文件名的字符
    @property
    def RoomName(self):
        if self._room_name is None :
            if self.IsGroupChat:
                self._room_name = self.GroupName
            else:
                self._room_name = self.SpeakerNickName
        
            self._room_name = sanitize_filename(self._room_name)

        return self._room_name