from common.expired_dict import ExpiredDict


#炳注：发送图片🖼️并在3分钟内提出问题，才会进行图片识别及回答。原来3分钟是在此设置的。
#     原来是3分钟（60 * 3），炳改为 3小时（60 * 60 * 3） 内提出问题，才会进行图片识别及回答
USER_IMAGE_CACHE = ExpiredDict(60 * 60 * 3)