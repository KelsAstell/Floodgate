#—————————必填配置（和家人一样宝贵的东西，别截图谨防泄露）———————————#
BOT_SECRET = ""                                             # 你的 AppSecret (机器人密钥)，请自行从开放平台获取
BOT_APPID = 0                                               # 你的AppID(机器人ID)，请自行从开放平台获取
OB_ACCESS_TOKEN = ""                                        # onebot实现的 .env文件内的 onebot_access_token，不填写时禁用握手验证，可能降低安全性

#——————————————————常规配置（你可能会偶尔改的东西）———————————————#
# 可以改，也可以不改
SANDBOX_MODE = False                                        # 沙盒模式，我已经默认设置为 False 了，如果你有测试需求，记得改成 True
LOG_LEVEL = "INFO"                                          # 日志级别，可选: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR
REMOVE_AT =  True                                           # 是否移除onebotv11端返回数据里可能存在的at，你也可以在机器人里设置 at_sender=False
PORT = 48443                                                # Floodgate 服务端口，不管是回调还是websocket都走这个端口，你需要在nginx或apache中配置合适的https转发策略，将 WEBHOOK_ENDPOINT 转发到这个端口
WEBHOOK_ENDPOINT = "/floodgate"                             # 开放平台回调地址，比如你填写的是 https://example.com/floodgate，这里就应该是 /floodgate
WS_ENDPOINT = "/ws"                                         # websocket地址，比如onebot端填写的是 ws://127.0.0.1:48443/ws，这里就应该是 /ws
CUSTOM_TITLE = ""                                           # 如果你这里不填的话，我就要使用默认的标题了哦
ADD_RETURN = False                                          # 是否在群聊文字消息的第一位加一个\n，这样可能会好看点？DeluxeBOT内部做了相应适配，所以这个选项默认关闭，你可以主动打开它



#——————————————————特殊配置（Gensokyo配置迁移）—————————————————#
# 孩子们，对于为什么要迁移我没话说，哦不对，还是有的，请看下一行
# ids.json需要和本文件放在同级目录
MIGRATE_IDS = True                                         # 是否迁移 Gensokyo 的idmap数据，默认为False，注意，只支持最早期的数字id，不支持idmap_pro



#—————————————————CONSTANT(常量，正常来说不需要动)——————————————#
# 女士/先生/福瑞/无机生命/阳光哥布林们，我的意思是，不要动，除非艾斯说了可以动，就这么简单
QQ_API_BASE = "https://api.sgroup.qq.com"                   # 正式环境API地址，不需要改
QQ_API_BASE_SANDBOX = "https://sandbox.api.sgroup.qq.com"   # 沙箱环境API地址，不需要改
VERSION = "0.0.1-Beta"                                      # 版本号，小猫，你可以改版本号
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | <level>{level: <8}</level> | <level>{message}</level>"
from loguru import logger as log                            # 不要删，会让 Floodgate 鼠掉，你可以逝一下

