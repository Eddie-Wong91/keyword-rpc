from contextlib import contextmanager
from datetime import datetime
from threading import RLock

import pymysql

from config import get_local_db_config
from logger_config import setup_logger


logger = setup_logger("lx_process_to_mysql", "lx_response_to_mysql.log")


class LXMySQLHandler:
    """Persist LX ranking data into the local MySQL database."""

    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        default_db_config = get_local_db_config()
        self.host = default_db_config["host"] if host is None else host
        self.port = default_db_config["port"] if port is None else port
        self.user = default_db_config["user"] if user is None else user
        self.password = default_db_config["password"] if password is None else password
        self.database = default_db_config["database"] if database is None else database

        self._connection = None
        self._connection_database = None
        self._lock = RLock()

        self.lx_table_mapping = {
            "mp_ad_rank": "mobile_ad_rank",
            "mp_natural_rank": "mobile_natural_rank",
            "pc_ad_rank": "pc_ad_rank",
            "pc_natural_rank": "pc_natural_rank",
        }

    def _build_connection_kwargs(self, use_database=True):
        connection_kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
        }
        if use_database:
            connection_kwargs["database"] = self.database
        return connection_kwargs

    def _close_connection_unlocked(self):
        if self._connection is None:
            return

        try:
            self._connection.close()
            logger.info("Closed cached LX MySQL connection")
        finally:
            self._connection = None
            self._connection_database = None

    def close(self):
        with self._lock:
            self._close_connection_unlocked()

    def _ensure_connection(self, use_database=True):
        target_database = self.database if use_database else None

        if self._connection is not None:
            try:
                self._connection.ping(reconnect=True)
            except Exception as exc:
                logger.warning("LX MySQL connection became unavailable, reconnecting: %s", exc)
                self._close_connection_unlocked()

        if self._connection is None or self._connection_database != target_database:
            self._close_connection_unlocked()
            self._connection = pymysql.connect(**self._build_connection_kwargs(use_database=use_database))
            self._connection_database = target_database
            if use_database:
                logger.info("Established cached LX MySQL connection to database %s", self.database)
            else:
                logger.info("Established cached LX MySQL server connection without selecting database")

        return self._connection

    @contextmanager
    def get_connection(self, use_database=True):
        with self._lock:
            try:
                connection = self._ensure_connection(use_database=use_database)
                yield connection
            except Exception:
                self._close_connection_unlocked()
                raise

    @contextmanager
    def get_cursor(self, connection):
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except Exception as exc:
            connection.rollback()
            logger.error("LX SQL execution failed, transaction rolled back: %s", exc)
            self.close()
            raise
        finally:
            cursor.close()

    def create_database_if_not_exists(self):
        try:
            with self.get_connection(use_database=False) as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS {self.database} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    logger.info("Ensured LX database exists: %s", self.database)
            return True
        except Exception as exc:
            logger.error("Failed to ensure LX database exists: %s", exc)
            return False

    def create_tables_if_not_exists(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    for table_name in self.lx_table_mapping.values():
                        create_sql = f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            asin VARCHAR(20) NOT NULL COMMENT 'ASIN编码',
                            country VARCHAR(10) NOT NULL COMMENT '国家',
                            keyword VARCHAR(500) NOT NULL COMMENT '关键词',
                            r_date VARCHAR(20) COMMENT '排名日期',
                            rank_info_export VARCHAR(500) COMMENT '排名信息',
                            insert_time DATETIME COMMENT '插入时间'
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='{table_name}排名数据';
                        """
                        cursor.execute(create_sql)
                        logger.info("Ensured LX table exists: %s", table_name)
            return True
        except Exception as exc:
            logger.error("Failed to ensure LX tables exist: %s", exc)
            return False

    def insert_lx_data(self, cursor, rank_key, asin, country, keyword, data_list, insert_time):
        table_name = self.lx_table_mapping.get(rank_key)
        if not table_name:
            logger.error("Unknown LX rank key: %s", rank_key)
            return False

        if not data_list:
            logger.warning("LX rank key %s has no rows to insert", rank_key)
            return True

        try:
            insert_sql = f"""
            INSERT INTO {table_name}
            (asin, country, keyword, r_date, rank_info_export, insert_time)
            VALUES (%s, %s, %s, %s, %s, %s)
            """

            insert_count = 0
            for row_data in data_list:
                r_date = row_data.get("r_date", "")
                rank_info_dict = row_data.get("rank_info", {})
                rank_info_export = rank_info_dict.get("rank_info_export", "") if isinstance(rank_info_dict, dict) else ""
                values = (asin, country, keyword, r_date, rank_info_export, insert_time)
                cursor.execute(insert_sql, values)
                insert_count += 1

            logger.info("Inserted %s rows into LX table %s", insert_count, table_name)
            return True
        except Exception as exc:
            logger.error(
                "Failed to insert LX data [table=%s, asin=%s, country=%s, keyword=%s]: %s",
                table_name,
                asin,
                country,
                keyword,
                exc,
            )
            return False

    def process_lx_response_to_mysql(self, response_dict, asin, country, keyword):
        try:
            result = response_dict.get("result", {})
            insert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    success = True
                    for rank_key in self.lx_table_mapping:
                        if rank_key in result and result[rank_key]:
                            data_list = result[rank_key]
                            logger.info("Processing LX rank key %s with %s rows", rank_key, len(data_list))
                            if not self.insert_lx_data(cursor, rank_key, asin, country, keyword, data_list, insert_time):
                                logger.warning("Failed to write LX rank key %s, continuing with remaining tables", rank_key)
                                success = False

                    return success
        except Exception as exc:
            logger.exception("Failed to process LX response: %s", exc)
            return False
