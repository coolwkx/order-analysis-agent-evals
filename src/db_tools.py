import logging
import os
from datetime import datetime

import pymysql


logger = logging.getLogger(__name__)


def failure(code, message):
    """构造统一的失败结果。"""
    return {
        "ok": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def get_connection():
    """根据环境变量创建数据库连接。"""
    required = [
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
    ]

    missing = [
        name for name in required
        if not os.environ.get(name, "").strip()
    ]

    if missing:
        raise ValueError(
            "缺少环境变量：" + ", ".join(missing)
        )

    port = int(os.environ["MYSQL_PORT"])

    if not 1 <= port <= 65535:
        raise ValueError("MYSQL_PORT 必须在 1 到 65535 之间")

    return pymysql.connect(
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
    )


def query_user_monthly_orders(year, month):
    """查询指定月份有订单的用户及其订单统计。"""

    # bool 是 int 的子类，这里明确拒绝布尔值。
    if type(year) is not int or type(month) is not int:
        return failure(
            "INVALID_ARGUMENT",
            "year 和 month 必须是整数，不能是布尔值。",
        )

    # 这是当前练习项目约定的支持范围。
    if not 2000 <= year <= 2100:
        return failure(
            "INVALID_ARGUMENT",
            "year 必须在 2000 到 2100 之间。",
        )

    if not 1 <= month <= 12:
        return failure(
            "INVALID_ARGUMENT",
            "month 必须在 1 到 12 之间。",
        )

    start = datetime(year, month, 1)

    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    sql = """
        SELECT
            user_id,
            COUNT(*) AS order_count,
            SUM(amount) AS total_amount
        FROM orders
        WHERE created_at >= %s
          AND created_at < %s
        GROUP BY user_id
        ORDER BY user_id
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (start, end))
                rows = cursor.fetchall()

    except ValueError as exc:
        logger.error("数据库配置错误：%s", exc)

        return failure(
            "CONFIG_ERROR",
            "数据库配置无效，请检查环境变量。",
        )

    except pymysql.MySQLError as exc:
        error_code = exc.args[0] if exc.args else "UNKNOWN"
        logger.error("数据库操作失败，错误码：%s", error_code)

        return failure(
            "DATABASE_ERROR",
            "数据库查询失败，请检查连接、权限和表结构。",
        )

    # 金额转为字符串，保留十进制精度并便于 JSON 序列化。
    data = [
        {
            "user_id": int(row["user_id"]),
            "order_count": int(row["order_count"]),
            "total_amount": format(row["total_amount"], ".2f"),
        }
        for row in rows
    ]

    return {
        "ok": True,
        "data": data,
        "error": None,
    }
