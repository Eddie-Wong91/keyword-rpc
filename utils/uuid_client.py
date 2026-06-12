import requests

from config import REQUEST_TIMEOUT, UUID_RESOURCE_VARIABLE_URL


def select_value_from_uuid(uuid: str, appKey: str, appSecret: str):
    """
    Query a resource variable value by UUID.
    """
    headers = {
        "Content-Type": "application/json",
        "appKey": appKey,
        "appSecret": appSecret,
    }
    data = {"resourceVariableUUID": uuid}

    try:
        response = requests.post(
            UUID_RESOURCE_VARIABLE_URL,
            json=data,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        resp_json = response.json()

        if resp_json.get("code") == 0:
            return resp_json

        return {
            "code": resp_json.get("code"),
            "msg": resp_json.get("msg", "Unknown business error"),
            "data": None,
        }

    except requests.exceptions.Timeout:
        return {"msg": "Request timed out", "code": -1, "data": None}
    except requests.exceptions.RequestException as exc:
        return {"msg": f"Network request error: {exc}", "code": -1, "data": None}
    except ValueError:
        return {"msg": "Failed to parse JSON response", "code": -1, "data": None}
