import logging
import sys


def _reset_logger(log):
    for handler in log.handlers:
        handler.close()
        log.removeHandler(handler)
        del handler
    log.handlers.clear()
    log.propagate = False
    console_handle = logging.StreamHandler(sys.stdout)
    console_handle.setFormatter(
        logging.Formatter(
            "[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # 炳注：因SHELL-stdout.log记录的日志比 run.log 更详细（如print命令的内容也会记录），
    #      所以不再记录 run.log
    # file_handle = logging.FileHandler("run.log", encoding="utf-8")
    # file_handle.setFormatter(
    #     logging.Formatter(
    #         "[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d] - %(message)s",
    #         datefmt="%Y-%m-%d %H:%M:%S",
    #     )
    # )
    # log.addHandler(file_handle)

    log.addHandler(console_handle)


def _get_logger():
    log = logging.getLogger("log")
    _reset_logger(log)
    log.setLevel(logging.INFO)
    return log


# 日志句柄
logger = _get_logger()
