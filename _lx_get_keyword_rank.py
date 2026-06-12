import requests

from config import LINGXING_API_BASE_URL, LINGXING_REFERER, REQUEST_TIMEOUT
from logger_config import setup_logger


logger = setup_logger("lx_keyword", "lx_keyword.log")


MID_DICT = {
    "美国": 1,
    "加拿大": 2,
    "墨西哥": 3,
    "巴西": 17,
    "英国": 4,
    "意大利": 7,
    "德国": 5,
    "法国": 6,
    "西班牙": 8,
    "荷兰": 15,
    "瑞典": 18,
    "土耳其": 20,
    "波兰": 19,
    "比利时": 21,
    "爱尔兰": 22,
    "埃及": 23,
    "印度": 9,
    "日本": 10,
    "澳大利亚": 12,
    "阿联酋": 13,
    "新加坡": 14,
    "沙特阿拉伯": 16,
}


def search_monitored_products(current_mid, search_value, auth_token, company_id, uid):
    url = f"{LINGXING_API_BASE_URL}/api/tool_kw_rank/lists"
    payload = {
        "mids": [current_mid],
        "search_value": search_value,
        "offset": 0,
        "length": 50,
        "is_parent": 0,
        "follow_status": 1,
        "create_uids": [],
        "monitor_uids": [],
        "req_time_sequence": "/api/tool_kw_rank/lists$$1",
    }
    headers = {
        "auth-token": auth_token,
        "X-AK-Company-Id": company_id,
        "X-AK-Uid": uid,
        "Referer": LINGXING_REFERER,
        "Content-Type": "application/json;charset=UTF-8",
    }
    response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    data = response.json()
    if data.get("msg") != "请求成功":
        return {"msg": False, "data": []}

    asin_dict_list = data.get("list", [])
    asin_list = [[row["id"], row["asin"], row["country"], row["country_code"]] for row in asin_dict_list]
    return {"msg": True, "data": asin_list}


def search_monitored_keywords(pid, search_value, auth_token, company_id, uid):
    url = f"{LINGXING_API_BASE_URL}/api/tool_kw_rank/kwLists"
    params = {
        "pid": pid,
        "search_value": search_value,
        "offset": 0,
        "length": 200,
        "follow_status": "all",
        "rank_field": "",
        "rank_type": "",
        "req_time_sequence": "/api/tool_kw_rank/kwLists$$1",
    }
    headers = {
        "auth-token": auth_token,
        "X-AK-Company-Id": company_id,
        "X-AK-Uid": uid,
        "Referer": LINGXING_REFERER,
    }
    response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    data = response.json()
    if data.get("msg") != "操作成功":
        return {"msg": False, "data": []}

    keyword_dict_list = data.get("data", {}).get("list", [])
    keyword_list = [
        [row["mid"], row["asin"], row["pid"], row["keyword"], row["postcode"], row["postcode_name"]]
        for row in keyword_dict_list
    ]
    return {"msg": True, "data": keyword_list}


def get_keyword_chart(pid, search_value, start_time, end_time, postcode, auth_token, company_id, uid):
    url = f"{LINGXING_API_BASE_URL}/api/tool_kw_rank/chart"
    payload = {
        "pid": pid,
        "keyword": search_value,
        "start_time": start_time,
        "end_time": end_time,
        "postcode": postcode,
        "req_time_sequence": "/api/tool_kw_rank/chart$$1",
    }
    headers = {
        "auth-token": auth_token,
        "X-AK-Company-Id": company_id,
        "X-AK-Uid": uid,
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": LINGXING_REFERER,
        "User-Agent": "Mozilla/5.0",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    data = response.json()
    if data.get("msg") != "操作成功":
        return {"msg": False, "data": {}}

    keyword_chart_dict = data.get("list") or {}
    return {"msg": True, "data": keyword_chart_dict}


def lx_get_keyword_rank_data(asin, country, keyword, start_time, end_time, auth_token, company_id, uid):
    logger.info("Start LingXing flow: asin=%s, country=%s, keyword=%s", asin, country, keyword)

    current_mid = MID_DICT.get(country)
    if not current_mid:
        logger.error("No mid mapping for country=%s", country)
        return {"error": f"{country}没有对应的mid"}

    result1 = search_monitored_products(current_mid, keyword, auth_token, company_id, uid)
    if not result1["msg"] or not result1["data"]:
        logger.error("search_monitored_products failed or returned no data")
        return {"error": "获取商品列表失败"}

    pid = None
    for row in result1["data"]:
        if row[1] == asin and row[2] == country:
            pid = row[0]
            logger.info("Matched pid=%s", pid)
            break

    if not pid:
        logger.error("No matching ASIN found: asin=%s, country=%s", asin, country)
        return {"error": "未找到匹配的商品"}

    result2 = search_monitored_keywords(pid, keyword, auth_token, company_id, uid)
    if not result2["msg"] or not result2["data"]:
        logger.error("search_monitored_keywords failed or returned no data")
        return {"error": "获取关键词列表失败"}

    postcode = None
    for row in result2["data"]:
        if row[0] == current_mid and row[1] == asin and row[2] == pid and row[3] == keyword:
            postcode = row[4]
            logger.info("Matched postcode=%s", postcode)
            break

    if not postcode:
        logger.error("No matching keyword found: asin=%s, country=%s, keyword=%s", asin, country, keyword)
        return {"error": "未找到匹配的关键词"}

    result3 = get_keyword_chart(pid, keyword, start_time, end_time, postcode, auth_token, company_id, uid)
    if not result3["msg"] or not result3["data"]:
        logger.error("get_keyword_chart failed")
        return {"error": "获取排名数据失败"}

    logger.info("LingXing flow completed successfully")
    return result3["data"]
