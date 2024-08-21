import logging

# 创建 总的日志 logger 对象
total_logger = logging.getLogger("MemorableTalker_Total")
total_logger.setLevel(logging.DEBUG) #要记录所有的日志，包括 DEBUG

#日志格式
formatter = logging.Formatter(
    f"%(message)s",
    datefmt=""
)

# 检查是否已经有相同的 FileHandler
log_file_path = "LogDir-ChatRoom/-(ALL_ROOMs)-.log"
handler_exists = any(
    isinstance(handler, logging.FileHandler) and handler.baseFilename == log_file_path
    for handler in total_logger.handlers
)

#防止被执行2次，
# 之前没检查时，因为每次 total_logger 记日志时，会有2条一样的日志被写到日志
if not handler_exists:
    # 创建 总日志的FileHandler 对象
    total_logger_file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    total_logger_file_handler.setFormatter(formatter)
    total_logger.addHandler(total_logger_file_handler)

# 创建 子模块日志(用于记录每个 聊天房间) 记录器
room_logger = logging.getLogger(f"MemorableTalker_Room")
room_logger.setLevel(logging.DEBUG) #要记录所有的日志，包括 DEBUG

# 记录 每个 聊天房间的日志的FileHandler 对象
# 性能开销：
# 每次创建和销毁 FileHandler 对象都会有一定的性能开销，尤其是在高频率调用的情况下。
# 频繁的文件操作（打开和关闭文件）也会增加 I/O 操作的开销。
# 内存使用：
# 使用 dict 来记录每个房间的 FileHandler 会增加内存使用，因为每个房间都会有一个对应的 FileHandler 对象。
# 但相对于性能开销，内存的增加通常是可以接受的
all_chat_rooms_log_file_handlers_dict: dict = {}

#记日志到2个文件：总日志 与 房间日志
def WriteLog2Files(strRoomName:str, strIndentSpaces:str, strLogText:str):
    # 为每一行添加缩进
    indented_log_text = "\n".join([f"{strIndentSpaces}{line}" for line in strLogText.split("\n")])

    # 若之前已经创建过此房间的FileHandler，就取现成的。
    # 否则就 新建 聊天房间的日志的FileHandler 对象，并记录到 handlers_dict 中，以便后用
    aRoomLogFileHandler = all_chat_rooms_log_file_handlers_dict.get(strRoomName)
    if aRoomLogFileHandler is None:
        aRoomLogFileHandler = logging.FileHandler(f"LogDir-ChatRoom/{strRoomName}.log", encoding="utf-8")
        aRoomLogFileHandler.setFormatter(formatter)
        all_chat_rooms_log_file_handlers_dict[strRoomName] = aRoomLogFileHandler
    
    room_logger.addHandler(aRoomLogFileHandler)

    total_logger.info(indented_log_text)
    room_logger.info(indented_log_text)

    room_logger.removeHandler(aRoomLogFileHandler)


