
# `/upload_image` 图片上传接口文档

## 接口说明

该接口用于将本地图片上传至 QQ 频道（开放平台），支持两种上传方式：

* `file_image`：通过指定本地文件路径读取并上传（仅限 Floodgate 与 Ob11 运行于同一主机）；
* `base64_image`：通过上传 base64 编码后的图片内容进行上传（可跨服务器通信）。

> ?仅需传入其中一个参数，若同时存在，`base64_image` 优先。

---

## 接口信息

| 项目   | 内容                         |
| ---- |----------------------------|
| 接口地址 | `POST /upload_image`       |
| 请求类型 | `application/json`         |
| 鉴权方式 | 无，公网部署时请自行部署鉴权             |
| 上传目标 | QQ 频道图片（由 `channel_id` 指定） |
| 响应格式 | JSON                       |

---

## 请求参数

| 字段名            | 类型     | 是否必填 | 示例                          | 说明                         |
| -------------- | ------ |------| --------------------------- | -------------------------- |
| `file_image`   | string | 否    | `/path/to/image.jpg`        | 本地图片路径，需确保 Floodgate 有权限读取 |
| `base64_image` | string | 否    | `/9j/4AAQSkZJRgABAQAAAQ...` | 图片内容的 base64 编码字符串         |
| `channel_id`   | string | 是    | `"632624627"`               | QQ 频道中的目标频道 ID             |

> `file_image` 与 `base64_image` 至少提供一个，要不然你传啥。

---

##  OneBot v11 客户端代码示例

###  1. Base64 方式上传（推荐用于跨服务器通信）

```python
import aiohttp
import aiofiles
import base64

async def encode_image_to_base64(image_path):
    async with aiofiles.open(image_path, "rb") as image_file:
        image_data = await image_file.read()
        return base64.b64encode(image_data).decode('utf-8')

async def post_base64_image_to_server(base64_image):
    data = {
        'base64_image': base64_image,
        'channel_id': "632624627",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("http://xxx.xxx.xxx.xxx:48443/upload_image", json=data) as response:
            if response.status == 200:
                image_info = await response.json(content_type=None)
                return image_info
            else:
                text = await response.text()
                raise Exception(f"Error uploading image: {text}")
```

### 2. 文件路径方式上传（需同机部署Ob11和Floodgate）

```python
async def post_file_image_to_server(image_path):
    data = {
        'file_image': image_path,
        'channel_id': "632624627",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("http://127.0.0.1:48443/upload_image", json=data) as response:
            if response.status == 200:
                image_info = await response.json(content_type=None)
                return image_info
            else:
                text = await response.text()
                raise Exception(f"Error uploading image: {text}")
```

### 示例调用（如命令触发时）：

```python
@cache.handle()
async def _(arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip()
    image_path = os.path.join(fr"E:\DeluxeBOT\oss-bucket\mrjm\{args}.jpg")
    data = await post_file_image_to_server(image_path)
    print(data)
```

---

## Floodgate 中间件处理逻辑（简述）

* 接收请求体，自动判断为 `base64_image` 或 `file_image`；
* 若为 `base64_image`：直接解码为二进制；
* 若为 `file_image`：尝试从本地路径读取文件；
* 将图片封装为表单字段并上传至对应频道；
* 上传成功后，根据原始图片生成 `MD5` 哈希，拼接为 QQ 图片链接并返回。

---

## 使用方式对比

| 上传方式           | 是否跨主机 | IO效率 | 开发调试友好度 | 传输大小  | 优势              |
| -------------- | ----- | ---- | ------- | ----- | --------------- |
| `file_image`   | 否   | 高  | 简单    | 最小 | 不需中间转换，速度快，读取直观 |
| `base64_image` | 是   | 稍慢 | 通用    | 稍大 | 支持远程上传，平台无关性强   |

---

## 响应字段说明

| 字段名     | 类型     | 示例                                           | 说明             |
| ------- | ------ | -------------------------------------------- | -------------- |
| `url`   | string | `https://gchat.qpic.cn/qmeetpic/0/0-0-XXX/0` | 上传成功后的 QQ 图片地址 |
| `error` | string | `Upload failed: ...`                         | 上传失败时的错误信息     |

