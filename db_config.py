import pymysql

from config import get_lingxing_db_config, get_sif_db_config
from logger_config import setup_logger


logger = setup_logger("db_config", "db_config.log")


def load_sif_params(group):
    """Load SIF credentials from the configured SIF database."""
    connection = None
    db_config = get_sif_db_config()
    db_config["cursorclass"] = pymysql.cursors.DictCursor

    try:
        connection = pymysql.connect(**db_config)
        logger.info("Connected to SIF config database")

        with connection.cursor() as cursor:
            sql = "SELECT `参数名`, `参数值` FROM `sif_token_info` WHERE `组名` = %s"
            cursor.execute(sql, (group,))
            results = cursor.fetchall()

            params = {row["参数名"]: row["参数值"] for row in results}
            logger.info("Loaded %s SIF config values", len(params))
            return params

    except Exception as exc:
        logger.error("Failed to load SIF params: %s", exc)
        return None
    finally:
        if connection:
            connection.close()


def get_lingxing_credentials(ipaddr):
    """Load LingXing credentials from the configured remote database."""
    connection = None
    db_config = get_lingxing_db_config(ipaddr)
    db_config["cursorclass"] = pymysql.cursors.DictCursor

    try:
        logger.info("Connecting to LingXing config database")
        connection = pymysql.connect(**db_config)

        with connection.cursor() as cursor:
            sql = "SELECT `参数名`, `参数值` FROM `领星账户信息`"
            cursor.execute(sql)
            results = cursor.fetchall()

            credentials = {}
            for row in results:
                param_name = row["参数名"]
                param_value = row["参数值"]

                if param_name == "auth_token":
                    credentials["auth_token"] = param_value
                elif param_name == "company_id":
                    credentials["company_id"] = param_value
                elif param_name == "user_id":
                    credentials["uid"] = param_value

            logger.info("Loaded %s LingXing config values", len(credentials))

            required_params = ["auth_token", "company_id", "uid"]
            missing_params = [item for item in required_params if item not in credentials]
            if missing_params:
                raise ValueError(f"Missing params in LingXing database: {', '.join(missing_params)}")

            return credentials

    except pymysql.Error as exc:
        logger.error("LingXing database error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Failed to read LingXing credentials: %s", exc)
        raise
    finally:
        if connection:
            connection.close()
