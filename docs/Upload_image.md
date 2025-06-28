
# `/upload_image` ͼƬ�ϴ��ӿ��ĵ�

## �ӿ�˵��

�ýӿ����ڽ�����ͼƬ�ϴ��� QQ Ƶ��������ƽ̨����֧�������ϴ���ʽ��

* `file_image`��ͨ��ָ�������ļ�·����ȡ���ϴ������� Floodgate �� Ob11 ������ͬһ��������
* `base64_image`��ͨ���ϴ� base64 ������ͼƬ���ݽ����ϴ����ɿ������ͨ�ţ���

> ?���贫������һ����������ͬʱ���ڣ�`base64_image` ���ȡ�

---

## �ӿ���Ϣ

| ��Ŀ   | ����                         |
| ---- |----------------------------|
| �ӿڵ�ַ | `POST /upload_image`       |
| �������� | `application/json`         |
| ��Ȩ��ʽ | �ޣ���������ʱ�����в����Ȩ             |
| �ϴ�Ŀ�� | QQ Ƶ��ͼƬ���� `channel_id` ָ���� |
| ��Ӧ��ʽ | JSON                       |

---

## �������

| �ֶ���            | ����     | �Ƿ���� | ʾ��                          | ˵��                         |
| -------------- | ------ |------| --------------------------- | -------------------------- |
| `file_image`   | string | ��    | `/path/to/image.jpg`        | ����ͼƬ·������ȷ�� Floodgate ��Ȩ�޶�ȡ |
| `base64_image` | string | ��    | `/9j/4AAQSkZJRgABAQAAAQ...` | ͼƬ���ݵ� base64 �����ַ���         |
| `channel_id`   | string | ��    | `"632624627"`               | QQ Ƶ���е�Ŀ��Ƶ�� ID             |

> `file_image` �� `base64_image` �����ṩһ����Ҫ��Ȼ�㴫ɶ��

---

##  OneBot v11 �ͻ��˴���ʾ��

###  1. Base64 ��ʽ�ϴ����Ƽ����ڿ������ͨ�ţ�

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

### 2. �ļ�·����ʽ�ϴ�����ͬ������Ob11��Floodgate��

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

### ʾ�����ã��������ʱ����

```python
@cache.handle()
async def _(arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip()
    image_path = os.path.join(fr"E:\DeluxeBOT\oss-bucket\mrjm\{args}.jpg")
    data = await post_file_image_to_server(image_path)
    print(data)
```

---

## Floodgate �м�������߼���������

* ���������壬�Զ��ж�Ϊ `base64_image` �� `file_image`��
* ��Ϊ `base64_image`��ֱ�ӽ���Ϊ�����ƣ�
* ��Ϊ `file_image`�����Դӱ���·����ȡ�ļ���
* ��ͼƬ��װΪ���ֶβ��ϴ�����ӦƵ����
* �ϴ��ɹ��󣬸���ԭʼͼƬ���� `MD5` ��ϣ��ƴ��Ϊ QQ ͼƬ���Ӳ����ء�

---

## ʹ�÷�ʽ�Ա�

| �ϴ���ʽ           | �Ƿ������ | IOЧ�� | ���������Ѻö� | �����С  | ����              |
| -------------- | ----- | ---- | ------- | ----- | --------------- |
| `file_image`   | ��   | ��  | ��    | ��С | �����м�ת�����ٶȿ죬��ȡֱ�� |
| `base64_image` | ��   | ���� | ͨ��    | �Դ� | ֧��Զ���ϴ���ƽ̨�޹���ǿ   |

---

## ��Ӧ�ֶ�˵��

| �ֶ���     | ����     | ʾ��                                           | ˵��             |
| ------- | ------ | -------------------------------------------- | -------------- |
| `url`   | string | `https://gchat.qpic.cn/qmeetpic/0/0-0-XXX/0` | �ϴ��ɹ���� QQ ͼƬ��ַ |
| `error` | string | `Upload failed: ...`                         | �ϴ�ʧ��ʱ�Ĵ�����Ϣ     |

