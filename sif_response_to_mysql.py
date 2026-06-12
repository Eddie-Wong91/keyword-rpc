
import pymysql
from datetime import datetime
from contextlib import contextmanager
from config import get_local_db_config

# 配置日志
from logger_config import setup_logger

logger = setup_logger('sif_process_to_mysql', 'sif_response_to_mysql.log')


class SIFMySQLHandler:
    """MySQL数据库处理类"""

    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        """
        初始化数据库连接参数

        Args:
            host: 数据库主机地址
            port: 数据库端口
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名称
        """
        default_db_config = get_local_db_config()
        self.host = default_db_config['host'] if host is None else host
        self.port = default_db_config['port'] if port is None else port
        self.user = default_db_config['user'] if user is None else user
        self.password = default_db_config['password'] if password is None else password
        self.database = default_db_config['database'] if database is None else database

        # 表名映射
        self.sif_table_mapping = {
            'natural_rank': 'sif_natural_rank',
            'ad_rank': 'sif_ad_rank'
        }

    @contextmanager
    def get_connection(self, use_database=True):
        """
        获取数据库连接的上下文管理器

        Args:
            use_database: 是否连接到指定数据库

        Yields:
            connection: 数据库连接对象
        """
        connection = None
        try:
            connection_kwargs = {
                'host': self.host,
                'port': self.port,
                'user': self.user,
                'password': self.password,
                'charset': 'utf8mb4',
                'cursorclass': pymysql.cursors.DictCursor
            }

            if use_database:
                connection_kwargs['database'] = self.database
                connection = pymysql.connect(**connection_kwargs)
                logger.info(f"成功连接到MySQL数据库: {self.database}")
            else:
                connection = pymysql.connect(**connection_kwargs)
                logger.info("成功连接到MySQL服务器")

            yield connection

        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise
        finally:
            if connection:
                connection.close()
                logger.info("数据库连接已关闭")

    @contextmanager
    def get_cursor(self, connection):
        """
        获取游标的上下文管理器

        Args:
            connection: 数据库连接对象

        Yields:
            cursor: 游标对象
        """
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.error(f"执行SQL失败，已回滚: {e}")
            raise
        finally:
            cursor.close()

    def create_database_if_not_exists(self):
        """创建数据库（如果不存在）"""
        try:
            with self.get_connection(use_database=False) as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS {self.database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    logger.info(f"数据库 {self.database} 已就绪")
            return True
        except Exception as e:
            logger.error(f"创建数据库失败: {e}")
            return False

    def create_tables_if_not_exists(self):
        """创建所需数据表（如果不存在）"""
        # 两张表结构完全相同，统一建表
        create_sql_template = """
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
            `asin`        VARCHAR(20)  NOT NULL                COMMENT 'ASIN编码',
            `country`     VARCHAR(10)  NOT NULL                COMMENT '国家',
            `keyword`     VARCHAR(500) NOT NULL                COMMENT '关键词',
            `r_date`      VARCHAR(50)  NOT NULL                COMMENT '排名日期',
            `rank_value`  INT          DEFAULT NULL            COMMENT '排名值',
            `insert_time` DATETIME     NOT NULL                COMMENT '插入时间',
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    for rank_key, table_name in self.sif_table_mapping.items():
                        cursor.execute(create_sql_template.format(table_name=table_name))
                        logger.info(f"数据表 {table_name} 已就绪")
            return True
        except Exception as e:
            logger.error(f"创建数据表失败: {e}")
            return False

    def insert_sif_data(self, cursor, rank_key, asin, country, keyword, rank_dict, insert_time):
        """
        插入SIF排名数据

        Args:
            rank_key: 排名类型键 (natural_rank 或 ad_rank)
            asin: ASIN编码
            country: 国家
            keyword: 关键词
            rank_dict: 排名字典，格式为 {'日期': 排名值}

        Returns:
            bool: 是否成功
        """
        table_name = self.sif_table_mapping.get(rank_key)
        if not table_name:
            logger.error(f"未知的SIF排名类型: {rank_key}")
            return False

        if not rank_dict:
            logger.warning(f"SIF {rank_key} 没有数据需要插入")
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

            logger.info(f"成功向SIF表 {table_name} 插入 {insert_count} 条数据")
            return True
        except Exception as e:
            logger.error(f"插入SIF数据失败 [表={table_name}, asin={asin}, country={country}, keyword={keyword}]: {e}")
            return False

    def process_sif_response_to_mysql(self, sif_result, asin, country, keyword):
        """
        处理SIF接口返回的数据并写入MySQL数据库

        Args:
            sif_result: SIF接口返回的结果字典，格式为
                       {'natural_rank': {'日期': 排名}, 'ad_rank': {'日期': 排名}}
            asin: ASIN编码
            country: 国家
            keyword: 关键词

        Returns:
            bool: 是否成功
        """
        try:
            insert_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    # 处理每个排名类型的数据
                    success = True
                    for rank_key in self.sif_table_mapping.keys():
                        if rank_key in sif_result and sif_result[rank_key]:
                            rank_dict = sif_result[rank_key]
                            logger.info(f"处理SIF {rank_key}，共 {len(rank_dict)} 条数据")

                            if not self.insert_sif_data(cursor, rank_key, asin, country, keyword, rank_dict, insert_time):
                                logger.warning(f"rank_key={rank_key} 写入失败，继续处理其他表")
                                success = False

                    return success
        except Exception as e:
            logger.exception(f"处理SIF数据异常: {e}")
            return False


