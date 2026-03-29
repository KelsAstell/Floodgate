#!/usr/bin/env python3
"""
SQLite 到 PostgreSQL 数据迁移脚本

使用方法:
1. 安装依赖: pip install asyncpg aiosqlite
2. 确保 PostgreSQL 数据库已创建
3. 修改本脚本底部的 DATABASE_URL
4. 运行: python migrate_to_postgres.py
"""

import asyncio
import json
import aiosqlite
import asyncpg
from typing import List, Tuple, Any
from contextlib import asynccontextmanager


class SQLiteSource:
    """SQLite 数据源"""

    def __init__(self, db_path: str = "storage.db"):
        self.db_path = db_path
        self.conn = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def get_tables(self) -> List[str]:
        """获取所有表名"""
        cursor = await self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_table_schema(self, table_name: str) -> List[dict]:
        """获取表结构"""
        cursor = await self.conn.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        return [
            {
                "name": row[1],
                "type": row[2],
                "notnull": row[3],
                "default": row[4],
                "pk": row[5]
            }
            for row in rows
        ]

    async def get_all_data(self, table_name: str) -> List[Tuple]:
        """获取表中所有数据"""
        cursor = await self.conn.execute(f"SELECT * FROM {table_name}")
        rows = await cursor.fetchall()
        return rows

    async def get_row_count(self, table_name: str) -> int:
        """获取表行数"""
        cursor = await self.conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = await cursor.fetchone()
        return row[0]


class PostgreSQLTarget:
    """PostgreSQL 目标数据库"""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=10
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def create_table(self, table_name: str, columns: List[dict]):
        """根据 SQLite 结构创建 PostgreSQL 表"""

        # 类型映射: SQLite -> PostgreSQL
        type_mapping = {
            "INTEGER": "INTEGER",
            "TEXT": "TEXT",
            "REAL": "REAL",
            "BLOB": "BYTEA",
            "NUMERIC": "NUMERIC",
            "BOOLEAN": "BOOLEAN",
            "DATETIME": "TIMESTAMP",
            "TIMESTAMP": "TIMESTAMP",
            "VARCHAR": "TEXT",
            "CHAR": "TEXT"
        }

        column_defs = []
        primary_keys = []

        for col in columns:
            col_name = col["name"]
            col_type = col["type"].upper()

            # 映射类型
            pg_type = None
            for sqlite_type, pg_t in type_mapping.items():
                if sqlite_type in col_type:
                    pg_type = pg_t
                    break
            if not pg_type:
                pg_type = "TEXT"

            # 处理自增主键
            if col["pk"] == 1 and pg_type == "INTEGER":
                pg_type = "SERIAL"

            col_def = f'"{col_name}" {pg_type}'

            if col["notnull"]:
                col_def += " NOT NULL"

            if col["default"] is not None:
                # 处理默认值
                default_val = col["default"]
                if isinstance(default_val, str):
                    # 处理 SQL 关键字（如 CURRENT_TIMESTAMP, NOW() 等），不需要加引号
                    sql_keywords = ['CURRENT_TIMESTAMP', 'CURRENT_DATE', 'CURRENT_TIME', 'NOW()', 'TRUE', 'FALSE', 'NULL']
                    if default_val.upper() in sql_keywords:
                        col_def += f" DEFAULT {default_val}"
                    else:
                        col_def += f" DEFAULT '{default_val}'"
                else:
                    col_def += f" DEFAULT {default_val}"

            column_defs.append(col_def)

            if col["pk"] == 1:
                primary_keys.append(f'"{col_name}"')

        # 构建建表语句
        create_sql = f"CREATE TABLE IF NOT EXISTS \"{table_name}\" (\n    "
        create_sql += ",\n    ".join(column_defs)

        if primary_keys:
            create_sql += f",\n    PRIMARY KEY ({', '.join(primary_keys)})"

        create_sql += "\n)"

        async with self.pool.acquire() as conn:
            await conn.execute(create_sql)

    async def insert_data(self, table_name: str, columns: List[str], data: List[Tuple], pk_columns: List[str] = None):
        """批量插入数据"""
        if not data:
            return 0

        # 过滤掉主键为 NULL 的行
        filtered_data = []
        skipped = 0
        for row in data:
            # 检查是否有 NULL 值在主键列中
            has_null_pk = False
            if pk_columns:
                for pk_col in pk_columns:
                    if pk_col in columns:
                        idx = columns.index(pk_col)
                        if row[idx] is None:
                            has_null_pk = True
                            break
            # 检查第一列（通常是主键）是否为 NULL
            elif row[0] is None:
                has_null_pk = True

            if has_null_pk:
                skipped += 1
                continue
            filtered_data.append(row)

        if skipped > 0:
            print(f"    ⚠ 跳过 {skipped} 行（主键为 NULL）")

        if not filtered_data:
            return 0

        col_names = ', '.join([f'"{c}"' for c in columns])
        placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])

        insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        async with self.pool.acquire() as conn:
            # 使用 executemany 批量插入
            await conn.executemany(insert_sql, filtered_data)

        return len(filtered_data)

    async def create_indexes(self, table_name: str):
        """创建常用索引"""
        # idmap 表的 digit_id 索引
        if table_name == "idmap":
            async with self.pool.acquire() as conn:
                await conn.execute(
                    'CREATE INDEX IF NOT EXISTS idx_digit_id ON idmap(digit_id)'
                )


async def migrate(sqlite_path: str = "storage.db", postgres_dsn: str = None):
    """执行迁移"""

    if not postgres_dsn:
        print("错误: 请提供 PostgreSQL 连接字符串")
        print("示例: postgresql://user:password@localhost:5432/dbname")
        return

    print(f"开始迁移...")
    print(f"源: SQLite ({sqlite_path})")
    print(f"目标: PostgreSQL")
    print("-" * 50)

    source = SQLiteSource(sqlite_path)
    target = PostgreSQLTarget(postgres_dsn)

    try:
        await source.connect()
        await target.connect()

        # 获取所有表
        tables = await source.get_tables()
        print(f"发现 {len(tables)} 个表: {', '.join(tables)}")

        total_rows = 0

        for table_name in tables:
            print(f"\n处理表: {table_name}")

            # 获取表结构
            schema = await source.get_table_schema(table_name)
            column_names = [col["name"] for col in schema]
            print(f"  列: {', '.join(column_names)}")

            # 创建目标表
            await target.create_table(table_name, schema)
            print(f"  ✓ 表结构已创建")

            # 获取数据
            row_count = await source.get_row_count(table_name)
            print(f"  数据行数: {row_count}")

            if row_count > 0:
                # 分批读取和插入
                batch_size = 1000
                offset = 0

                while offset < row_count:
                    cursor = await source.conn.execute(
                        f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}"
                    )
                    rows = await cursor.fetchall()

                    if rows:
                        inserted = await target.insert_data(table_name, column_names, rows)
                        total_rows += inserted
                        print(f"  已迁移 {min(offset + len(rows), row_count)}/{row_count} 行")

                    offset += batch_size

            # 创建索引
            await target.create_indexes(table_name)
            print(f"  ✓ 索引已创建")

        print("\n" + "=" * 50)
        print(f"迁移完成! 共迁移 {total_rows} 行数据")
        print("\n下一步:")
        print("1. 修改 config.py 中的 DATABASE_TYPE = 'postgresql'")
        print("2. 修改 config.py 中的 DATABASE_URL 为你的 PostgreSQL 连接字符串")
        print("3. 安装依赖: pip install asyncpg")
        print("4. 重启应用")

    except Exception as e:
        print(f"\n迁移失败: {e}")
        raise

    finally:
        await source.close()
        await target.close()


if __name__ == "__main__":
    import sys

    # 默认配置，可以修改这里或使用命令行参数
    SQLITE_DB = "storage.db"
    POSTGRES_DSN = None  # 例如: "postgresql://user:password@localhost:5432/floodgate"

    if len(sys.argv) >= 2:
        POSTGRES_DSN = sys.argv[1]
    if len(sys.argv) >= 3:
        SQLITE_DB = sys.argv[2]

    if not POSTGRES_DSN:
        print("用法: python migrate_to_postgres.py <postgresql_dsn> [sqlite_db_path]")
        print("")
        print("示例:")
        print('  python migrate_to_postgres.py "postgresql://admin:secret@localhost:5432/floodgate"')
        print("")
        print("或者直接修改脚本底部的 POSTGRES_DSN 变量")
        sys.exit(1)

    asyncio.run(migrate(SQLITE_DB, POSTGRES_DSN))
