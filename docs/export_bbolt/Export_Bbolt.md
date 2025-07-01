
# ? bbolt-exporter ʹ��˵��

�ù������ڽ� [`bbolt`](https://github.com/etcd-io/bbolt) ���ݿ�洢���ݵ���Ϊ JSON ��ʽ�������ڵ��ԡ����ݻ����Ŀ�ġ�֧���Զ��������б�Bucket����Ϊÿ��������һ�������� `.json` �ļ���**��ֵ�� base64 �������**��ȷ�������ԡ�

---

## ? ��Ŀ�ṹ

```
.
������ go.mod               // Goģ�鶨���ļ�
������ go.sum               // Go����У����ļ�
������ export_bbolt.go      // ���������
������ idmap.db             // ��Ҫ������ bbolt ���ݿ⣨����ʱ����ڵ�ǰĿ¼��
```

---

## ? ���뷽ʽ

ȷ�����Ѱ�װ Go �� 1.21���Ƽ�ʹ�� 1.24+����������ģ��֧�֡�

```bash
# ��¡�����ش����ִ������������룺
go build -o bbolt-exporter export_bbolt.go
```

����ɹ��������һ����ִ���ļ� `bbolt-exporter`��Windows ��Ϊ `bbolt-exporter.exe`����

����㲻��������ȥDeluxeBOT�Ĺٷ�Ⱥ�ļ����ң���Ҳ�������������3MB..

---

## ? ����˵��

ģ����ʹ�õ�������

```go
require (
    go.etcd.io/bbolt v1.4.1         // �����ݿ������
    golang.org/x/sys v0.29.0        // ϵͳ����֧�֣�indirect��
)
```

������ Go Module �Զ������������ֶ���װ��

---

## ? ʹ�÷���

ȷ����ǰĿ¼������Ϊ `idmap.db` �� bbolt ���ݿ��ļ���

```bash
./bbolt-exporter
```

��Windows����

```cmd
bbolt-exporter.exe
```

### ����Ч��ʾ����

```text
�� xxxx �����ɹ�
�� xxxxx �����ɹ�
```

---

## ? ���˵��

ִ�гɹ��󣬽��ڵ�ǰĿ¼���ɶ�� JSON �ļ���ÿ�����Ӧһ����

```
ids.json
UserInfo.json
...
```

ÿ���ļ��Ľṹ���£���ֵ��Ϊ base64 ���룩��

```json
[
  {
    "key": "a2V5MQ==",
    "value": "dmFsdWUx"
  },
  {
    "key": "a2V5Mg==",
    "value": "dmFsdWUy"
  }
]
```

ֻ��Ҫids.json�ļ�������Floodgate��Ŀ�ĸ�Ŀ¼�£��� `run.py` ����ͬһ��Ŀ¼�����ɡ�
ͬʱ��config.py������ `MIGRATE_IDS = True`������ `run.py` �������Ǩ�ơ�


---

## ? ע������

* �ļ�Ĭ�����Ϊ UTF-8 ����� JSON
* ���м�ֵ�Ծ����� Base64 ���룬��ֹ�������������ݸ�ʽ����
* ����Ŀ¼Ϊ��ǰִ��Ŀ¼��ȷ����д��Ȩ��
* �����ݿ�Ϊ�ջ�������ݣ���������ļ�

---

## ? License

MIT����Floodgate����һ������������ûʲô������
