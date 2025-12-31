package main

import (
	"encoding/base64"
    "encoding/json"
    "fmt"
    "go.etcd.io/bbolt"
    "os"
)

func exportTableToJSON(db *bbolt.DB, tableName string) error {
    // 创建JSON文件
    fileName := fmt.Sprintf("%s.json", tableName)
    file, err := os.Create(fileName)
    if err != nil {
        return fmt.Errorf("创建文件失败: %w", err)
    }
    defer file.Close()

    // 遍历表并导出为JSON
    return db.View(func(tx *bbolt.Tx) error {
        bucket := tx.Bucket([]byte(tableName))
        if bucket != nil {
            cursor := bucket.Cursor()
            var data []map[string]interface{}
            for k, v := cursor.First(); k != nil; k, v = cursor.Next() {
                // 将键值对转换为JSON对象
                item := map[string]interface{}{
                    "key":   base64.StdEncoding.EncodeToString(k),
                    "value": base64.StdEncoding.EncodeToString(v),
                }
                data = append(data, item)
            }

            // 将数据集合转换为JSON并写入文件
            jsonBytes, err := json.Marshal(data)
            if err != nil {
                return fmt.Errorf("转换数据失败: %w", err)
            }
            _, err = file.Write(jsonBytes)
            if err != nil {
                return fmt.Errorf("写入文件失败: %w", err)
            }
        }
        return nil
    })
}

func main() {
    // 打开bbolt数据库
    db, err := bbolt.Open("idmap.db", 0666, nil)
    if err != nil {
        fmt.Println("打开数据库失败:", err)
        return
    }
    defer db.Close()

    // 获取所有表名
    var tableNames []string
    err = db.View(func(tx *bbolt.Tx) error {
        tx.ForEach(func(name []byte, _ *bbolt.Bucket) error {
            tableNames = append(tableNames, string(name))
            return nil
        })
        return nil
    })
    if err != nil {
        fmt.Println("获取表名失败:", err)
        return
    }

    // 导出每张表为JSON文件
    for _, tableName := range tableNames {
        err = exportTableToJSON(db, tableName)
        if err != nil {
            fmt.Println("导出表失败:", err)
        } else {
            fmt.Printf("表 %s 导出成功\n", tableName)
        }
    }
}