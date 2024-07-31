from common.expired_dict import ExpiredDict


#炳注：发送图片🖼️并在90秒内提出问题，才会进行图片识别及回答
#     90秒 内提出问题，才会进行图片识别及回答
USER_IMAGE_CACHE = ExpiredDict(90)