"""
Azure SQL Free Tier Integration
================================
Azure SQL Database free tier: 32 GB storage, 100K vCore-seconds/month.
Up to 10 free databases per subscription, no expiry.

Connection: pyodbc (MSSQL) or sqlalchemy with pyodbc driver.
Falls back gracefully to no-op if unavailable or unconfigured.

Free tier provisioning:
  az sql server create --name tranc3-sql --resource-group tranc3-rg \\
    --location uksouth --admin-user tranc3admin \\
    --admin-password <password> --enable-public-network true
  az sql db create --resource-group tranc3-rg --server tranc3-sql \\
    --name tranc3 --edition GeneralPurpose --family Gen5 \\
    --capacity 1 --free-limit OnlyFreeDb
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("tranc3.database.azure_sql")

_CONN_STRING = os.environ.get("AZURE_SQL_CONNECTION_STRING", "")
_DRIVER = "{ODBC Driver 18 for SQL Server}"


def _conn():
    """Return a pyodbc connection or None if unavailable/unconfigured."""
    if not _CONN_STRING:
        return None
    try:
        import pyodbc  # type: ignore[import]

        return pyodbc.connect(_CONN_STRING, timeout=10)
    except ImportError:
        logger.debug("azure_sql: pyodbc not installed — Azure SQL unavailable")
        return None
    except Exception as exc:
        logger.debug("azure_sql: connection failed (%s)", exc)
        return None


def is_available() -> bool:
    """Return True if Azure SQL is configured and reachable."""
    conn = _conn()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        return True
    except Exception:
        return False
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """
    Execute a query against Azure SQL. Returns list of row dicts.
    Returns [] if Azure SQL is unavailable.
    """
    conn = _conn()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if cur.description:
            cols = [col[0] for col in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
        conn.commit()
        return []
    except Exception as exc:
        logger.warning("azure_sql.execute failed: %s", exc)
        return []
    finally:
        conn.close()


def bootstrap_table(table_name: str, ddl: str) -> bool:
    """
    Create a table if it doesn't exist. Returns True on success.
    DDL should be a CREATE TABLE IF NOT EXISTS ... statement.
    """
    conn = _conn()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        # Azure SQL uses IF NOT EXISTS via: IF NOT EXISTS (SELECT ...)
        # table_name is an internal constant, never user input — nosec B608
        check_sql = f"IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{table_name}') BEGIN {ddl} END"  # nosec B608
        cur.execute(check_sql)
        conn.commit()
        logger.info("azure_sql: table %s bootstrapped", table_name)
        return True
    except Exception as exc:
        logger.warning("azure_sql.bootstrap_table failed: %s", exc)
        return False
    finally:
        conn.close()


def upsert_json(table: str, key_col: str, key_val: str, data_col: str, data: str) -> bool:
    """
    Upsert a JSON blob using MERGE. Returns True on success.
    Assumes table has (key_col NVARCHAR, data_col NVARCHAR(MAX)).
    """
    conn = _conn()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        # table/column names are internal constants, never user input — nosec B608
        sql = f"MERGE {table} AS target USING (SELECT ? AS {key_col}, ? AS {data_col}) AS source ON target.{key_col} = source.{key_col} WHEN MATCHED THEN UPDATE SET {data_col} = source.{data_col} WHEN NOT MATCHED THEN INSERT ({key_col}, {data_col}) VALUES (source.{key_col}, source.{data_col});"  # nosec B608
        cur.execute(sql, (key_val, data))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("azure_sql.upsert_json failed: %s", exc)
        return False
    finally:
        conn.close()


def connection_info() -> dict[str, Any]:
    """Return Azure SQL connection metadata for health checks."""
    if not _CONN_STRING:
        return {"available": False, "reason": "AZURE_SQL_CONNECTION_STRING not set"}
    conn = _conn()
    if conn is None:
        return {"available": False, "reason": "connection failed"}
    try:
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION AS version, DB_NAME() AS db_name")
        row = cur.fetchone()
        return {
            "available": True,
            "db_name": row.db_name if row else "unknown",
            "version": (row.version or "")[:80] if row else "unknown",
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    finally:
        conn.close()
