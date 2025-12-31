
# ? bbolt-exporter 使用说明

该工具用于将 [`bbolt`](https://github.com/etcd-io/bbolt) 数据库存储内容导出为 JSON 格式，适用于调试、备份或分析目的。支持自动遍历所有表（Bucket）并为每个表生成一个独立的 `.json` 文件，**键值以 base64 编码输出**以确保兼容性。

---

## ? 项目结构

```
.
├── go.mod               // Go模块定义文件
├── go.sum               // Go依赖校验和文件
├── export_bbolt.go      // 主程序入口
└── idmap.db             // 你要导出的 bbolt 数据库（运行时需放在当前目录）
```

---

## ? 编译方式

确保你已安装 Go ≥ 1.21（推荐使用 1.24+），并启用模块支持。

```bash
# 克隆或下载代码后，执行以下命令编译：
go build -o bbolt-exporter export_bbolt.go
```

编译成功后会生成一个可执行文件 `bbolt-exporter`（Windows 下为 `bbolt-exporter.exe`）。

如果你不会编译可以去DeluxeBOT的官方群文件里找，我也不会打包，打完包3MB..

---

## ? 依赖说明

模块中使用的依赖：

```go
require (
    go.etcd.io/bbolt v1.4.1         // 主数据库操作库
    golang.org/x/sys v0.29.0        // 系统兼容支持（indirect）
)
```

依赖由 Go Module 自动管理，你无需手动安装。

---

## ? 使用方法

确保当前目录存在名为 `idmap.db` 的 bbolt 数据库文件：

```bash
./bbolt-exporter
```

或（Windows）：

```cmd
bbolt-exporter.exe
```

### 运行效果示例：

```text
表 xxxx 导出成功
表 xxxxx 导出成功
```

---

## ? 输出说明

执行成功后，将在当前目录生成多个 JSON 文件，每个表对应一个：

```
ids.json
UserInfo.json
...
```

每个文件的结构如下（键值均为 base64 编码）：

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

只需要ids.json文件，放在Floodgate项目的根目录下（和 `run.py` 放在同一个目录）即可。
同时在config.py中设置 `MIGRATE_IDS = True`，运行 `run.py` 即可完成迁移。


---

## ? 注意事项

* 文件默认输出为 UTF-8 编码的 JSON
* 所有键值对均经过 Base64 编码，防止乱码或二进制数据格式问题
* 导出目录为当前执行目录，确保有写入权限
* 如数据库为空或表无内容，会输出空文件

---

## ? License

MIT（和Floodgate本体一样，这玩意真没什么技术）
