import atexit

from flask import Flask, jsonify, request

from _lx_get_keyword_rank import lx_get_keyword_rank_data
from _sif_get_keyword_rank import sif_get_keyword_rank_data
from config import RPC_DEBUG, RPC_HOST, RPC_PORT
from logger_config import setup_logger
from lx_response_to_mysql import LXMySQLHandler
from sif_response_to_mysql import SIFMySQLHandler


logger = setup_logger("rpc_server", "rpc_server.log")
app = Flask(__name__)

lx_mysql_handler = None
sif_mysql_handler = None
lx_storage_ready = False
sif_storage_ready = False


def _build_result(success, error=None):
    result = {"success": success}
    if error:
        result["error"] = error
    return result


def _ensure_lx_storage():
    global lx_mysql_handler, lx_storage_ready

    if lx_storage_ready and lx_mysql_handler is not None:
        return True

    lx_mysql_handler = lx_mysql_handler or LXMySQLHandler()
    if not lx_mysql_handler.create_database_if_not_exists():
        logger.error("Failed to initialize LX database")
        return False
    if not lx_mysql_handler.create_tables_if_not_exists():
        logger.error("Failed to initialize LX tables")
        return False

    lx_storage_ready = True
    return True


def _ensure_sif_storage():
    global sif_mysql_handler, sif_storage_ready

    if sif_storage_ready and sif_mysql_handler is not None:
        return True

    sif_mysql_handler = sif_mysql_handler or SIFMySQLHandler()
    if not sif_mysql_handler.create_database_if_not_exists():
        logger.error("Failed to initialize SIF database")
        return False
    if not sif_mysql_handler.create_tables_if_not_exists():
        logger.error("Failed to initialize SIF tables")
        return False

    sif_storage_ready = True
    return True


@app.route("/rpc", methods=["POST"])
def rpc_handler():
    req = None
    try:
        req = request.get_json() or {}
        logger.info("Received RPC request: method=%s, id=%s", req.get("method"), req.get("id"))

        method = req.get("method")
        params = req.get("params", {})
        req_id = req.get("id")

        if method == "lx_get_keyword_rank_data":
            if not _ensure_lx_storage():
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "LX storage initialization failed"), "id": req_id})

            lx_result = lx_get_keyword_rank_data(
                params["asin"],
                params["country"],
                params["keyword"],
                params["start_time"],
                params["end_time"],
                params["auth_token"],
                params["company_id"],
                params["uid"],
            )
            if not isinstance(lx_result, dict):
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "Invalid LX result type"), "id": req_id})
            if lx_result.get("error"):
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, lx_result["error"]), "id": req_id})

            write_success = lx_mysql_handler.process_lx_response_to_mysql(
                {"result": lx_result},
                params["asin"],
                params["country"],
                params["keyword"],
            )
            if not write_success:
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "LX database write failed"), "id": req_id})

            return jsonify({"jsonrpc": "2.0", "result": _build_result(True), "id": req_id})

        if method == "sif_get_keyword_rank_data":
            if not _ensure_sif_storage():
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "SIF storage initialization failed"), "id": req_id})

            sif_result = sif_get_keyword_rank_data(
                params["country"],
                params["token"],
                params["search_value"],
                params["asin"],
            )
            if sif_result is None:
                logger.warning("SIF returned no data: ASIN=%s, keyword=%s", params["asin"], params["search_value"])
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "Keyword not found or request failed"), "id": req_id})
            if not isinstance(sif_result, dict):
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "Invalid SIF result type"), "id": req_id})

            write_success = sif_mysql_handler.process_sif_response_to_mysql(
                sif_result,
                params["asin"],
                params["country"],
                params["search_value"],
            )
            if not write_success:
                return jsonify({"jsonrpc": "2.0", "result": _build_result(False, "SIF database write failed"), "id": req_id})

            return jsonify({"jsonrpc": "2.0", "result": _build_result(True), "id": req_id})

        logger.error("Unknown RPC method: %s", method)
        return jsonify(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": req_id,
            }
        )

    except Exception as exc:
        logger.exception("RPC handler error: %s", exc)
        return jsonify(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(exc)},
                "id": None if req is None else req.get("id"),
            }
        )


if __name__ == "__main__":
    atexit.register(lambda: lx_mysql_handler.close() if lx_mysql_handler is not None else None)
    atexit.register(lambda: sif_mysql_handler.close() if sif_mysql_handler is not None else None)
    app.run(host=RPC_HOST, port=RPC_PORT, debug=RPC_DEBUG, use_reloader=False)
