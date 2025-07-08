#—————————必填配置（和家人一样宝贵的东西，别截图谨防泄露）———————————#
BOT_SECRET = ""                                             # 你的 AppSecret (机器人密钥)，请自行从开放平台获取
BOT_APPID = 0                                               # 你的AppID(机器人ID)，请自行从开放平台获取
OB_ACCESS_TOKEN = ""                                        # onebot实现的 .env文件内的 onebot_access_token，不填写时禁用握手验证，可能降低安全性
BOT_NAME = "BOT"                                            # 机器人名字，可不填
ADMIN_LIST = []                                             # 管理员的数字ID，如果 TRANSPARENT_OPENID 为 True （开启透传模式）时，
                                                            # 需要填写OpenID，可在DEBUG模式下获取，用于部分管理功能调用


#——————————————————常规配置（你可能会偶尔改的东西）———————————————#
# 可以改，也可以不改
SANDBOX_MODE = False                                        # 沙盒模式，我已经默认设置为 False 了，如果你有测试需求，记得改成 True
LOG_LEVEL = "INFO"                                          # 日志级别，可选: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR
REMOVE_AT =  True                                           # 是否移除onebotv11端返回数据里可能存在的at，你也可以在机器人里设置 at_sender=False
PORT = 48443                                                # Floodgate 服务端口，不管是回调还是websocket都走这个端口，你需要在nginx或apache中配置合适的https转发策略，将 WEBHOOK_ENDPOINT 转发到这个端口
WEBHOOK_ENDPOINT = "/floodgate"                             # 开放平台回调地址，比如你填写的是 https://example.com/floodgate，这里就应该是 /floodgate
WS_ENDPOINT = "/ws"                                         # websocket地址，比如onebot端填写的是 ws://127.0.0.1:48443/ws，这里就应该是 /ws
CUSTOM_TITLE = ""                                           # 如果你这里不填的话，我就要使用默认的标题了哦
ADD_RETURN = False                                          # 是否在群聊文字消息的第一位加一个\n，这样可能会好看点？DeluxeBOT内部做了相应适配，所以这个选项默认关闭
SANDBOX_CHANNEL_ID = 0                                      # 沙箱频道ID，使用 /upload_image 接口时，若未填写 channel_id ，则使用该参数
MAINTAINING_MESSAGE = ""                                    # 维护公告，可不填
IDMAP_INITIAL_ID = 100000                                   # 起始数字ID，用于创建idmap映射，可填大于0的数字
IDMAP_TTL = 3600                                            # idmap的缓存时间，默认1小时，缓存时间越长，IDMAP理论性能越好，但同时会增加内存占用
NAP_MILLSECONDS = 300                                      # 发送前等待的时间，小助手给的说法说是降速，要不然就会出现诡异的调用不支持(404)


#—————————————————特殊配置（给高级用户用的选项）——————————————————#
# 孩子们，对于为什么要迁移我没话说，哦不对，还是有的，请看下一行
# ids.json需要和本文件放在同级目录
MIGRATE_IDS = False                                         # 是否迁移 Gensokyo 的idmap数据，默认为False，注意，只支持最早期的数字id，不支持idmap_pro
TRANSPARENT_OPENID = False                                  # OpenID 透传，好东西...但是除非你知道你在干什么，否则不要启用这个选项，
                                                            # 需要你的 OneBot 实现自行适配string格式的ID，如果你开了这个选项，那你用的一定不是原生OneBot
RATE_LIMIT = True                                           # 是否开启中间件级别限速
MAX_MESSAGES = 6                                            # 时间窗口内消息数
TIME_WINDOW_SECONDS = 10                                    # 时间窗口时长，单位为秒
BLOCK_DURATION_SECONDS = 60                                 # 封禁时长，单位为秒

#—————————————————成就系统（DeluxeBOT特化代码）——————————————————#
# 小猫，你可以用成就系统，但是它并不完善，可能暂时也没有文档..
ACHIEVEMENT_PERSIST = True                                  # 在Floodgate端持久化储存成就，防止重复发送成就信息，默认关；如果不开启的话同样的也无法查询成就


#—————————————————CONSTANT(常量，正常来说不需要动)——————————————#
# 女士/先生/福瑞/无机生命/阳光哥布林们，我的意思是，不要动，除非艾斯说了可以动，就这么简单
QQ_API_BASE = "https://api.sgroup.qq.com"                   # 正式环境API地址，不需要改
QQ_API_BASE_SANDBOX = "https://sandbox.api.sgroup.qq.com"   # 沙箱环境API地址，不需要改
VERSION = "0.0.3"                                      # 版本号，小猫，你可以改版本号
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | <level>{level: <8}</level> | <level>{message}</level>"
from loguru import logger as log                            # 不要删，会让 Floodgate 鼠掉，你可以逝一下
SEQ_CACHE_SIZE = 300                                        # 消息队列缓存大小，如果你的BOT涉及到一个事件多次回复，可能需要调的很大，如果没有这样的需求，300足矣
STAT_LOG = "logs/usage_summary.json"                        # 保存你的DAU和DAI记录
STAT_LOG_MAX_DAYS = 7                                       # DAU和DAI的最长保存期限，单位为天