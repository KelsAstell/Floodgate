
# ? OneBot v11 `audio` ��Ϣ�����ĵ���Ⱥ��/˽�� Silk ��Ƶ��

## ? ���ܸ���

ʹ�� OneBot v11 �� `record` ��Ϣ�Σ�����Ϊ `audio`���������� QQ ��**Ⱥ�Ļ�˽��**���� `.silk` ��ʽ������Ϣ��Floodgate �м����ʶ�� base64 ��ʽ�����ݣ�ת�벢ͨ�� QQ �ٷ� API��˽���ϴ������ļ���

---

## ? OneBot v11 ʾ������

```python
import base64
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment, MessageEvent

send_dummy_silk = on_command("������")

@send_dummy_silk.handle()
async def _(event: MessageEvent):
    try:
        with open(r"E:\DeluxeBOT\testbot\test.silk", "rb") as f:
            silk_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"Failed to encode silk audio: {e}")
        await send_dummy_silk.finish("silk����ʧ��", reply_message=True)

    # ��������    
    await send_dummy_silk.finish(MessageSegment.record(f"base64://{silk_base64}"))
    # ����..
    await send_dummy_silk.finish(MessageSegment.record(r"file:///E:\DeluxeBOT\testbot\test.silk"))
    # ������..
    await send_dummy_silk.finish(MessageSegment.record(f"https://your-website.com/test.silk"))
```

---

## ? ��Ϣ��˵��

| ��Ϣ������    | �ֶ���  | ֵ��ʽ               | ˵��                                      |
| -------- | ---- |-------------------|-----------------------------------------|
| `record` | file | `base64://...` �� `http(s)://...`�� `file:///...` | base64 ����� `.silk` ��Ƶ����Զ��ֱ�� URL���򱾵��ļ�·�� |

---

## ? Floodgate �м���������

1. �ж���Ϣ������Ϊ `record`��
2. �� `file` �ֶ��� `base64://` ��ͷ��

    * ��ȡ base64 ���ݣ�
    * ����Ϊ������ `.silk`��
    * ͨ�� QQ �ӿڣ�Ⱥ/˽����Ϣ���ϴ�Ϊ������
3. �� `file` �ֶ��� `http(s)://...` ��ͷ��
    * ���Ի�ȡ����
    * ͨ�� QQ �ӿڣ�Ⱥ/˽����Ϣ���ϴ�Ϊ������

4. �ϴ��ɹ����Զ��滻Ϊ��ʶ���������Ϣ��ʽ���͡�

---

## ? ֧��������˵��

| ������      | ״̬    | ˵��                  |
|----------|-------|---------------------|
| Ⱥ������֧��   | ? ֧��  | ��ֱ��ʹ�� record �η���Ⱥ��  |
| ˽������֧��   | ? ֧��  | ��ֱ��ʹ�� record �η���˽��  |
| Զ������ URL | ? ֧��  | ��Ƶ�ļ��蹫���ɷ���          |
| �ļ�·������   | ?? ֧�� | ��ͬ������Ob11��Floodgate |


---

## ? ע������

* `.silk` �ļ������ QQ Ҫ��16kHz ����������� 60s��
* base64 ���Ȳ�Ӧ���� 1MB������������ 60 ���ڵ�������
* ������ʧ�ܣ��縻ý���ʽ���󣩣�Floodgate Ӧ�ṩ������־��
* ����ֱ�ӷ��� mp3/wav����ת��Ϊ QQ ֧�ֵ� `.silk` ��ʽ��(�Զ�ת������δ����ͨ���µ���Ϣ������ʵ��)

---

## ? ��ѡ�����Ƽ�

���轫������Ƶ��ʽ���� mp3��wav��ת��Ϊ silk����ʹ�ã�

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -f s16le -acodec pcm_s16le raw.pcm
silk_v3_encoder raw.pcm output.silk -tencent
```
