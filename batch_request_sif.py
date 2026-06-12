import sys
import time

import pandas as pd
import requests

from config import (
    BATCH_REQUEST_INTERVAL_SECONDS,
    REQUEST_TIMEOUT,
    RPC_URL,
    build_excel_path,
)
from db_config import load_sif_params
from logger_config import setup_logger


logger = setup_logger("batch_request_sif", "batch_request_sif.log")


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
        sif_params = load_sif_params(group_name)
        if not sif_params:
            logger.error("Failed to load SIF credentials")
            sys.exit(1)
        logger.info("Loaded SIF credentials")
    except Exception as exc:
        logger.error("Failed to get SIF credentials: %s", exc)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Start batch processing")
    logger.info("=" * 60)

    sif_success_count = 0
    sif_fail_count = 0

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

            time.sleep(BATCH_REQUEST_INTERVAL_SECONDS)

            request_body = {
                "jsonrpc": "2.0",
                "method": "sif_get_keyword_rank_data",
                "params": {
                    "country": item["country"],
                    "token": sif_params.get("sif_token", ""),
                    "search_value": item["keyword"],
                    "asin": item["asin"],
                },
                "id": index,
            }

            response = requests.post(RPC_URL, json=request_body, timeout=REQUEST_TIMEOUT)
            response_dict = response.json()

            if not isinstance(response_dict, dict):
                logger.error(
                    "Invalid SIF RPC response type [ASIN=%s, country=%s, keyword=%s]: %s",
                    item["asin"],
                    item["country"],
                    item["keyword"],
                    type(response_dict).__name__,
                )
                sif_fail_count += 1
                continue

            rpc_error = response_dict.get("error")
            if rpc_error is not None:
                logger.error(
                    "SIF RPC error [ASIN=%s, country=%s, keyword=%s]: %s",
                    item["asin"],
                    item["country"],
                    item["keyword"],
                    rpc_error,
                )
                sif_fail_count += 1
                continue

            result = response_dict.get("result")
            if not isinstance(result, dict):
                logger.error(
                    "Invalid SIF result type [ASIN=%s, country=%s, keyword=%s]: %s",
                    item["asin"],
                    item["country"],
                    item["keyword"],
                    type(result).__name__,
                )
                sif_fail_count += 1
                continue

            if result.get("success") is True:
                sif_success_count += 1
                logger.info("SIF success [ASIN=%s, keyword=%s]", item["asin"], item["keyword"])
            else:
                sif_fail_count += 1
                logger.error(
                    "SIF task failed [ASIN=%s, country=%s, keyword=%s]: %s",
                    item["asin"],
                    item["country"],
                    item["keyword"],
                    result.get("error", "Unknown SIF error"),
                )

        except requests.exceptions.Timeout:
            logger.error(
                "Request timeout [ASIN=%s, country=%s, keyword=%s]",
                item["asin"],
                item["country"],
                item["keyword"],
            )
            sif_fail_count += 1
        except requests.exceptions.ConnectionError:
            logger.error(
                "RPC connection failed [ASIN=%s, country=%s, keyword=%s]",
                item["asin"],
                item["country"],
                item["keyword"],
            )
            sif_fail_count += 1
        except Exception as exc:
            logger.error(
                "Unhandled error [ASIN=%s, country=%s, keyword=%s]: %s",
                item["asin"],
                item["country"],
                item["keyword"],
                exc,
            )
            sif_fail_count += 1

    logger.info("=" * 60)
    logger.info("Finished. total=%s", len(batch_data))
    logger.info("SIF success=%s fail=%s", sif_success_count, sif_fail_count)
    logger.info("=" * 60)
    sys.exit(determine_exit_code(len(batch_data), sif_success_count, sif_fail_count))


if __name__ == "__main__":
    main()
