import time
import uuid

import requests

from config import (
    REQUEST_TIMEOUT,
    SIF_API_BASE_URL,
    SIF_ORIGIN,
    SIF_RETRY_COUNT,
    SIF_RETRY_SLEEP_SECONDS,
    SIF_USER_AGENT,
)
from logger_config import setup_logger


logger = setup_logger("sif_keyword", "sif_keyword.log")


COUNTRY_MAP = {
    "美国": "US",
    "德国": "DE",
    "英国": "UK",
    "日本": "JP",
    "加拿大": "CA",
    "法国": "FR",
    "西班牙": "ES",
    "意大利": "IT",
    "澳大利亚": "AU",
    "墨西哥": "MX",
    "阿联酋": "AE",
    "巴西": "BR",
    "沙特": "SA",
}


def _post_json(url, *, params=None, headers=None, cookies=None, json_body=None):
    response = requests.post(
        url,
        params=params,
        headers=headers,
        cookies=cookies,
        json=json_body,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("SIF response is not a JSON object")
    return payload


def _extract_dict(value, field_name):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} is not a dict")
    return value


def _extract_list(value, field_name):
    if not isinstance(value, list):
        raise ValueError(f"{field_name} is not a list")
    return value


def generate_device_id():
    base_uuid = uuid.uuid4().hex
    return f"Sif_{base_uuid[:8]}-{base_uuid[8:12]}-{base_uuid[12:16]}-{base_uuid[16:20]}-{base_uuid[20:32]}"


def search_asin_keywords(country, device_id, token, search_value, asin):
    logger.info("Search SIF keywords: country=%s, asin=%s, keyword=%s", country, asin, search_value)

    country_code = COUNTRY_MAP.get(country)
    if not country_code:
        logger.error("Unsupported SIF country: %s", country)
        return None

    url = f"{SIF_API_BASE_URL}/api/search/asinKeywords"
    params = {"country": country_code, "_t": int(time.time() * 1000), "_m": device_id}
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": token,
        "User-Agent": SIF_USER_AGENT,
        "Referer": f"{SIF_API_BASE_URL}/reverse?country={country_code}",
        "Origin": SIF_ORIGIN,
    }
    cookies = {"sif_token": token}
    data = {
        "timePieceType": "latelyDay",
        "timePieceValue": "7",
        "asin": asin,
        "pageNum": 1,
        "pageSize": 100,
        "desc": True,
        "keyword": search_value,
    }

    response = {}
    for attempt in range(SIF_RETRY_COUNT):
        try:
            time.sleep(SIF_RETRY_SLEEP_SECONDS)
            response = _post_json(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                json_body=data,
            )
            if isinstance(response.get("data"), dict):
                logger.info("Fetched first keyword page on attempt %s", attempt + 1)
                break
            logger.warning("Missing or invalid `data` on attempt %s", attempt + 1)
        except Exception as exc:
            logger.error("Keyword page request failed on attempt %s: %s", attempt + 1, exc)
    else:
        logger.error("Failed to fetch first keyword page after %s retries", SIF_RETRY_COUNT)
        return None

    try:
        data = _extract_dict(response.get("data"), "response.data")
        keywords_list = _extract_list(data.get("keywords"), "response.data.keywords")
        total = data.get("total", 0)
        if not isinstance(total, int):
            raise ValueError("response.data.total is not an int")
    except ValueError as exc:
        logger.error("Invalid first keyword page payload: %s", exc)
        return None

    if total > 100:
        total_page = int(total / 100) + 1
        for page in range(2, total_page + 1):
            if keywords_list and search_value in [row.get("keyword") for row in keywords_list if isinstance(row, dict)]:
                break

            page_data = {
                "timePieceType": "latelyDay",
                "timePieceValue": "7",
                "asin": asin,
                "pageNum": page,
                "pageSize": 100,
                "desc": True,
                "keyword": search_value,
            }

            page_response = {}
            for attempt in range(SIF_RETRY_COUNT):
                try:
                    time.sleep(SIF_RETRY_SLEEP_SECONDS)
                    page_response = _post_json(
                        url,
                        params=params,
                        headers=headers,
                        cookies=cookies,
                        json_body=page_data,
                    )
                    if isinstance(page_response.get("data"), dict):
                        logger.info("Fetched keyword page %s/%s", page, total_page)
                        break
                    logger.warning("Keyword page %s returned invalid `data`", page)
                except Exception as exc:
                    logger.error("Keyword page %s failed on attempt %s: %s", page, attempt + 1, exc)
            if isinstance(page_response.get("data"), dict):
                page_data_dict = page_response.get("data") or {}
                page_keywords = page_data_dict.get("keywords")
                if isinstance(page_keywords, list):
                    keywords_list += page_keywords
                else:
                    logger.warning("Keyword page %s returned invalid keywords list", page)

    if not keywords_list:
        logger.warning("SIF keyword list is empty")
        return False

    keyword_list = [row.get("keyword") for row in keywords_list if isinstance(row, dict)]
    if search_value in keyword_list:
        logger.info("Found target keyword: %s", search_value)
        return True

    logger.warning("Target keyword not found: %s", search_value)
    return False


def get_asin_keyword_rank_data(country, token, asin, keyword, device_id):
    logger.info("Fetch SIF rank history: country=%s, asin=%s, keyword=%s", country, asin, keyword)

    country_code = COUNTRY_MAP.get(country)
    if not country_code:
        logger.error("Unsupported SIF country: %s", country)
        return None

    url = f"{SIF_API_BASE_URL}/api/search/asinKeywordRankHistory"
    params = {"country": country_code, "_t": int(time.time() * 1000), "_m": device_id}
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": token,
        "User-Agent": SIF_USER_AGENT,
        "Origin": SIF_ORIGIN,
        "Referer": f"{SIF_API_BASE_URL}/reverse?asin={asin}&isListingSearch=false&trafficType=",
    }
    data = {"isListingSearch": False, "asin": asin, "keyword": keyword, "lastMonths": 1}

    response = {}
    for attempt in range(SIF_RETRY_COUNT):
        try:
            time.sleep(SIF_RETRY_SLEEP_SECONDS)
            response = _post_json(
                url,
                params=params,
                headers=headers,
                json_body=data,
            )
            if isinstance(response.get("data"), dict):
                logger.info("Fetched SIF rank history on attempt %s", attempt + 1)
                break
            logger.warning("No valid SIF rank response on attempt %s", attempt + 1)
        except Exception as exc:
            logger.error("SIF rank request failed on attempt %s: %s", attempt + 1, exc)
    else:
        logger.error("Failed to fetch SIF rank history after %s retries", SIF_RETRY_COUNT)
        return None

    try:
        data = _extract_dict(response.get("data"), "response.data")
        natural_rank_list = _extract_list(data.get("nfRankHistory"), "response.data.nfRankHistory")
        ad_rank_list = _extract_list(data.get("spRankHistory"), "response.data.spRankHistory")
        dates = _extract_list(data.get("dates"), "response.data.dates")
    except ValueError as exc:
        logger.error("Invalid SIF rank history payload: %s", exc)
        return None

    if not (len(dates) == len(natural_rank_list) == len(ad_rank_list)):
        logger.error(
            "SIF rank history length mismatch: dates=%s natural=%s ad=%s",
            len(dates),
            len(natural_rank_list),
            len(ad_rank_list),
        )
        return None

    natural_rank = {}
    ad_rank = {}
    for index, date in enumerate(dates):
        if not date:
            logger.warning("Skipping empty SIF rank date at index %s", index)
            continue
        current_natural_data = natural_rank_list[index]
        current_ad_data = ad_rank_list[index]
        if current_natural_data is not None and not isinstance(current_natural_data, dict):
            logger.warning("Invalid natural rank item at index %s", index)
            current_natural_data = None
        if current_ad_data is not None and not isinstance(current_ad_data, dict):
            logger.warning("Invalid ad rank item at index %s", index)
            current_ad_data = None

        natural_rank[date] = None if current_natural_data is None else current_natural_data.get("rank")
        ad_rank[date] = None if current_ad_data is None else current_ad_data.get("rank")

    return {"natural_rank": natural_rank, "ad_rank": ad_rank}


def sif_get_keyword_rank_data(country, token, search_value, asin):
    logger.info("=" * 60)
    logger.info("Start SIF flow")

    device_id = generate_device_id()
    keyword_exists = search_asin_keywords(country, device_id, token, search_value, asin)

    if keyword_exists is None:
        logger.error("Keyword lookup request failed")
        return None

    if keyword_exists is True:
        logger.info("Keyword exists, fetching rank data")
        rank_data = get_asin_keyword_rank_data(country, token, asin, search_value, device_id)
        if rank_data is None:
            logger.error("Failed to fetch SIF rank data")
            return None

        logger.info("SIF flow completed")
        return rank_data

    logger.warning("Keyword does not exist, skipping rank fetch")
    return None
