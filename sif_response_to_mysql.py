from contextlib import contextmanager
from datetime import datetime
from threading import RLock

import pymysql

from config import get_local_db_config
from logger_config import setup_logger


logger = setup_logger("sif_process_to_mysql", "sif_response_to_mysql.log")


class SIFMySQLHandler:
    """Persist SIF ranking data into the local MySQL database."""

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

        self.sif_table_mapping = {
            "natural_rank": "sif_natural_rank",
            "ad_rank": "sif_ad_rank",
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
            logger.info("Closed cached SIF MySQL connection")
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
                logger.warning("SIF MySQL connection became unavailable, reconnecting: %s", exc)
                self._close_connection_unlocked()

        if self._connection is None or self._connection_database != target_database:
            self._close_connection_unlocked()
            self._connection = pymysql.connect(**self._build_connection_kwargs(use_database=use_database))
            self._connection_database = target_database
            if use_database:
                logger.info("Established cached SIF MySQL connection to database %s", self.database)
            else:
                logger.info("Established cached SIF MySQL server connection without selecting database")

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
            logger.error("SIF SQL execution failed, transaction rolled back: %s", exc)
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
                    logger.info("Ensured SIF database exists: %s", self.database)
            return True
        except Exception as exc:
            logger.error("Failed to ensure SIF database exists: %s", exc)
            return False

    def create_tables_if_not_exists(self):
        create_sql_template = """
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
            `asin` VARCHAR(20) NOT NULL COMMENT 'ASIN编码',
            `country` VARCHAR(10) NOT NULL COMMENT '国家',
            `keyword` VARCHAR(500) NOT NULL COMMENT '关键词',
            `r_date` VARCHAR(50) NOT NULL COMMENT '排名日期',
            `rank_value` INT DEFAULT NULL COMMENT '排名值',
            `insert_time` DATETIME NOT NULL COMMENT '插入时间',
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    for table_name in self.sif_table_mapping.values():
                        cursor.execute(create_sql_template.format(table_name=table_name))
                        logger.info("Ensured SIF table exists: %s", table_name)
            return True
        except Exception as exc:
            logger.error("Failed to ensure SIF tables exist: %s", exc)
            return False

    def insert_sif_data(self, cursor, rank_key, asin, country, keyword, rank_dict, insert_time):
        table_name = self.sif_table_mapping.get(rank_key)
        if not table_name:
            logger.error("Unknown SIF rank key: %s", rank_key)
            return False

        if not rank_dict:
            logger.warning("SIF rank key %s has no rows to insert", rank_key)
            return True

        try:
            insert_sql = f"""
            INSERT INTO {table_name}
            (asin, country, keyword, r_date, rank_value, insert_time)
            VALUES (%s, %s, %s, %s, %s, %s)
            """

            insert_count = 0
            for r_date, rank_value in rank_dict.items():
                values = (asin, country, keyword, r_date, rank_value, insert_time)
                cursor.execute(insert_sql, values)
                insert_count += 1

            logger.info("Inserted %s rows into SIF table %s", insert_count, table_name)
            return True
        except Exception as exc:
            logger.error(
                "Failed to insert SIF data [table=%s, asin=%s, country=%s, keyword=%s]: %s",
                table_name,
                asin,
                country,
                keyword,
                exc,
            )
            return False

    def process_sif_response_to_mysql(self, sif_result, asin, country, keyword):
        try:
            insert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    success = True
                    for rank_key in self.sif_table_mapping:
                        if rank_key in sif_result and sif_result[rank_key]:
                            rank_dict = sif_result[rank_key]
                            logger.info("Processing SIF rank key %s with %s rows", rank_key, len(rank_dict))
                            if not self.insert_sif_data(cursor, rank_key, asin, country, keyword, rank_dict, insert_time):
                                logger.warning("Failed to write SIF rank key %s, continuing with remaining tables", rank_key)
                                success = False

                    return success
        except Exception as exc:
            logger.exception("Failed to process SIF response: %s", exc)
            return False
