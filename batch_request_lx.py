import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import (
    BATCH_REQUEST_INTERVAL_SECONDS,
    REQUEST_TIMEOUT,
    RPC_URL,
    UUID_APP_KEY,
    UUID_APP_SECRET,
    UUID_RESOURCE_VARIABLE_UUID,
    build_excel_path,
    require_env,
)
from db_config import get_lingxing_credentials
from logger_config import setup_logger
from utils.uuid_client import select_value_from_uuid


logger = setup_logger("batch_request_lx", "batch_request_lx.log")


def is_valid_keyword(value):
    if pd.isna(value):
        return False
    str_value = str(value).strip().lower()
    return str_value not in {"", "nan", "none", "null"}


def determine_exit_code(total_count, success_count, fail_count):
    if total_count <= 0:
        return 1
    if success_count == total_count:
        return 0
    if fail_count == total_count:
        return 3
    return 2


def main():
    if len(sys.argv) < 2:
        logger.error("Missing group name argument")
        sys.exit(1)

    group_name = sys.argv[1]
    excel_path = build_excel_path(group_name)

    try:
        df = pd.read_excel(excel_path)
        logger.info("Loaded Excel file: %s, rows=%s", excel_path, len(df))
    except FileNotFoundError:
        logger.error("Excel file not found: %s", excel_path)
        sys.exit(1)
    except Exception as exc:
        logger.error("Failed to read Excel file: %s", exc)
        sys.exit(1)

    batch_data = []
    for row_num, (_, row) in enumerate(df.iterrows(), start=2):
        try:
            asin = str(row["ASIN"]).strip()
            country = str(row["站点"]).strip()
            keyword_raw = row["关键词"]

            if not is_valid_keyword(keyword_raw):
                continue

            keywords = [item.strip() for item in str(keyword_raw).split("|") if item.strip()]
            for keyword in keywords:
                batch_data.append({"asin": asin, "country": country, "keyword": keyword})
        except Exception as exc:
            logger.error("Failed to process Excel row %s: %s", row_num, exc)

    logger.info("Valid tasks: %s", len(batch_data))
    if not batch_data:
        logger.error("No valid request data, exiting")
        sys.exit(1)

    try:
        require_env("UUID_RESOURCE_VARIABLE_UUID", "UUID_APP_KEY", "UUID_APP_SECRET")
        uuid_result = select_value_from_uuid(
            UUID_RESOURCE_VARIABLE_UUID,
            UUID_APP_KEY,
            UUID_APP_SECRET,
        )
        if uuid_result.get("code") != 0:
            logger.error("Failed to query remote database IP: %s", uuid_result.get("msg"))
            sys.exit(1)

        remote_ip = (uuid_result.get("data") or {}).get("value")
        if not remote_ip:
            logger.error("Remote database IP is empty")
            sys.exit(1)

        logger.info("Resolved remote database IP: %s", remote_ip)
        credentials = get_lingxing_credentials(ipaddr=remote_ip)
        logger.info("Loaded LingXing credentials")
    except Exception as exc:
        logger.error("Failed to load LingXing credentials: %s", exc)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Start batch processing")
    logger.info("=" * 60)

    lx_success_count = 0
    lx_fail_count = 0

    end_time = datetime.now() - timedelta(days=1)
    start_time = end_time - timedelta(days=6)
    start_time_str = start_time.strftime("%Y-%m-%d 00:00:00")
    end_time_str = end_time.strftime("%Y-%m-%d 23:59:59")

    for index, item in enumerate(batch_data, start=1):
        try:
            logger.info(
                "[%s/%s] Processing: %s - %s - %s",
                index,
                len(batch_data),
                item["asin"],
                item["country"],
                item["keyword"],
            )

            request_body = {
                "jsonrpc": "2.0",
                "method": "lx_get_keyword_rank_data",
                "params": {
                    "asin": item["asin"],
                    "country": item["country"],
                    "keyword": item["keyword"],
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    **credentials,
                },
                "id": index,
            }

            response = requests.post(RPC_URL, json=request_body, timeout=REQUEST_TIMEOUT)
            response_dict = response.json()

            if not isinstance(response_dict, dict):
                logger.error(
                    "Invalid LX RPC response type [ASIN=%s, country=%s, keyword=%s]: %s",
                    item["asin"],
                    item["country"],
                    item["keyword"],
                    type(response_dict).__name__,
                )
                lx_fail_count += 1
            else:
                rpc_error = response_dict.get("error")
                if rpc_error is not None:
                    logger.error(
                        "LX RPC error [ASIN=%s, country=%s, keyword=%s]: %s",
                        item["asin"],
                        item["country"],
                        item["keyword"],
                        rpc_error,
                    )
                    lx_fail_count += 1
                else:
                    result = response_dict.get("result")
                    if not isinstance(result, dict):
                        logger.error(
                            "Invalid LX result type [ASIN=%s, country=%s, keyword=%s]: %s",
                            item["asin"],
                            item["country"],
                            item["keyword"],
                            type(result).__name__,
                        )
                        lx_fail_count += 1
                    elif result.get("success") is True:
                        lx_success_count += 1
                        logger.info("LX success [ASIN=%s, keyword=%s]", item["asin"], item["keyword"])
                    else:
                        lx_fail_count += 1
                        logger.error(
                            "LX task failed [ASIN=%s, country=%s, keyword=%s]: %s",
                            item["asin"],
                            item["country"],
                            item["keyword"],
                            result.get("error", "Unknown LX error"),
                        )

            time.sleep(BATCH_REQUEST_INTERVAL_SECONDS)
        except requests.exceptions.Timeout:
            logger.error(
                "Request timeout [ASIN=%s, country=%s, keyword=%s]",
                item["asin"],
                item["country"],
                item["keyword"],
            )
            lx_fail_count += 1
        except requests.exceptions.ConnectionError:
            logger.error(
                "RPC connection failed [ASIN=%s, country=%s, keyword=%s]",
                item["asin"],
                item["country"],
                item["keyword"],
            )
            lx_fail_count += 1
        except Exception as exc:
            logger.error(
                "Unhandled error [ASIN=%s, country=%s, keyword=%s]: %s",
                item["asin"],
                item["country"],
                item["keyword"],
                exc,
            )
            lx_fail_count += 1

    logger.info("=" * 60)
    logger.info("Finished. total=%s", len(batch_data))
    logger.info("LX success=%s fail=%s", lx_success_count, lx_fail_count)
    logger.info("=" * 60)
    sys.exit(determine_exit_code(len(batch_data), lx_success_count, lx_fail_count))


if __name__ == "__main__":
    main()
