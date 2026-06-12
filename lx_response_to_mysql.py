
import pymysql
from datetime import datetime
from contextlib import contextmanager
from config import get_local_db_config

# 配置日志
from logger_config import setup_logger

logger = setup_logger('lx_process_to_mysql', 'lx_response_to_mysql.log')


class LXMySQLHandler:
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
        self.lx_table_mapping = {
            'mp_ad_rank': 'mobile_ad_rank',
            'mp_natural_rank': 'mobile_natural_rank',
            'pc_ad_rank': 'pc_ad_rank',
            'pc_natural_rank': 'pc_natural_rank'
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
        """创建所有排名表（如果不存在）"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    for table_name in self.lx_table_mapping.values():
                        create_sql = f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            id          INT AUTO_INCREMENT PRIMARY KEY,
                            asin        VARCHAR(20)  NOT NULL COMMENT 'ASIN编码',
                            country     VARCHAR(10)  NOT NULL COMMENT '国家',
                            keyword     VARCHAR(500) NOT NULL COMMENT '关键词',
                            r_date      VARCHAR(20)  COMMENT '排名日期',
                            rank_info_export VARCHAR(500) COMMENT '排名信息',
                            insert_time DATETIME     COMMENT '插入时间'
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='{table_name}排名数据';
                        """
                        cursor.execute(create_sql)
                        logger.info(f"表 {table_name} 已就绪")
            return True
        except Exception as e:
            logger.error(f"创建表失败: {e}")
            return False


    def insert_lx_data(self, cursor, rank_key, asin, country, keyword, data_list, insert_time):
        """
        插入排名数据

        Args:
            rank_key: 排名类型键 (mp_ad_rank, mp_natural_rank, etc.)
            asin: ASIN编码
            country: 国家
            keyword: 关键词
            data_list: 数据列表

        Returns:
            bool: 是否成功
        """
        table_name = self.lx_table_mapping.get(rank_key)
        if not table_name:
            logger.error(f"未知的排名类型: {rank_key}")
            return False

        if not data_list:
            logger.warning(f"{rank_key} 没有数据需要插入")
            return True

        try:
            insert_sql = f"""
            INSERT INTO {table_name} 
            (asin, country, keyword, r_date, rank_info_export, insert_time)
            VALUES (%s, %s, %s, %s, %s, %s)
            """

            insert_count = 0
            for row_data in data_list:
                r_date = row_data.get('r_date', '')

                # 从嵌套的 rank_info 字典中提取 rank_info_export
                rank_info_dict = row_data.get('rank_info', {})
                if isinstance(rank_info_dict, dict):
                    rank_info_export = rank_info_dict.get('rank_info_export', '')
                else:
                    rank_info_export = ''

                values = (asin, country, keyword, r_date, rank_info_export, insert_time)
                cursor.execute(insert_sql, values)
                insert_count += 1

            logger.info(f"成功向 {table_name} 插入 {insert_count} 条数据")
            return True
        except Exception as e:
            logger.error(f"插入LX数据失败 [表={table_name}, asin={asin}, country={country}, keyword={keyword}]: {e}")
            return False

    def process_lx_response_to_mysql(self, response_dict, asin, country, keyword):
        """
        处理JSON-RPC响应并写入MySQL数据库

        Args:
            response_dict: 响应字典
            asin: ASIN编码
            country: 国家
            keyword: 关键词

        Returns:
            bool: 是否成功
        """
        try:
            result = response_dict.get('result', {})
            insert_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    # 处理每个排名类型的数据
                    success = True
                    for rank_key in self.lx_table_mapping.keys():
                        if rank_key in result and result[rank_key]:
                            data_list = result[rank_key]
                            logger.info(f"处理 {rank_key}，共 {len(data_list)} 条数据")

                            if not self.insert_lx_data(cursor, rank_key, asin, country, keyword, data_list, insert_time):
                                logger.warning(f"rank_key={rank_key} 写入失败，继续处理其他表")
                                success = False

                    return success
        except Exception as e:
            logger.exception(f"处理异常: {e}")
            return False




