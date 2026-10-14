import os
import sys

import pymysql


def main():
    required = (
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
    )

    missing = [
        name for name in required
        if not os.environ.get(name, "").strip()
    ]

    if missing:
        print("缺少环境变量：", ", ".join(missing))
        return 1

    try:
        port = int(os.environ["MYSQL_PORT"])

        if not 1 <= port <= 65535:
            raise ValueError

    except ValueError:
        print("MYSQL_PORT 必须是 1 到 65535 之间的整数。")
        return 1

    try:
        with pymysql.connect(
            host=os.environ["MYSQL_HOST"],
            port=port,
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DATABASE"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=10,
            write_timeout=10,
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        CURRENT_USER() AS account,
                        DATABASE() AS database_name
                    """
                )
                identity = cursor.fetchone()

                print("实际账号：", identity["account"])
                print("当前数据库：", identity["database_name"])

                cursor.execute(
                    """
                    SELECT order_id, user_id, amount, created_at
                    FROM orders
                    ORDER BY order_id
                    LIMIT 10
                    """
                )
                rows = cursor.fetchall()

                print("\n=== 订单数据 ===")

                for row in rows:
                    print(
                        f"订单={row['order_id']}，"
                        f"用户={row['user_id']}，"
                        f"金额={row['amount']}，"
                        f"时间={row['created_at']}"
                    )

                print(f"\n本次读取 {len(rows)} 条记录。")

    except pymysql.MySQLError as exc:
        code = exc.args[0] if exc.args else "UNKNOWN"
        print("MySQL 操作失败，错误码：", code)
        return 1

    print("MySQL 连接与读取验证通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
