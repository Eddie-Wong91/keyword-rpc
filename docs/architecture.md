# Architecture

## Overview

The project is structured as a local orchestration layer around two upstream data sources:

- LingXing
- SIF

The local Flask service exposes a single JSON-RPC endpoint. Batch clients read Excel input, resolve credentials, submit one RPC call per keyword task, and the server writes normalized ranking data into local MySQL tables.

## High-Level Components

### 1. Batch clients

- `batch_request_lx.py`
- `batch_request_sif.py`
- `run_batch_request_lx.bat`
- `run_batch_request_sif.bat`

Responsibilities:

- provide a Windows/RPA-friendly entry point
- read Excel by group name
- expand rows into individual keyword tasks
- load upstream credentials
- call the local RPC service
- aggregate success/failure counts

### Batch wrapper role

The `.bat` files are thin wrappers around the Python batch clients.

Responsibilities:

- switch to the project directory
- prefer `.venv\Scripts\python.exe` when present
- fall back to system `python` otherwise
- pass the group name argument through to the Python script
- return the final process exit code back to the caller

The final line:

```bat
exit /b %ERRORLEVEL%
```

does not affect log capture. Its purpose is to propagate the Python script exit code to the parent process, such as RPA or another scheduler.

That means the caller can distinguish between:

- completed successfully
- completed with partial failures
- completed with full failure
- completed with initialization or input errors

RPA can capture console logs independently because Python logging is configured with a console `StreamHandler`.

### 2. RPC server

- `main.py`

Responsibilities:

- host `/rpc`
- route requests by `method`
- initialize local storage
- invoke the LingXing or SIF business flow
- persist results into local MySQL

### 3. Upstream adapters

- `_lx_get_keyword_rank.py`
- `_sif_get_keyword_rank.py`

Responsibilities:

- translate local task input into upstream API calls
- validate upstream responses
- normalize the response shape expected by persistence code

### 4. Persistence layer

- `lx_response_to_mysql.py`
- `sif_response_to_mysql.py`

Responsibilities:

- create the local database if necessary
- create required tables if necessary
- persist normalized rank data
- reuse long-lived MySQL connections

### 5. Configuration and support utilities

- `config.py`
- `db_config.py`
- `logger_config.py`
- `utils/uuid_client.py`

Responsibilities:

- load env-based settings
- resolve Excel paths
- read credentials from configured databases
- configure logging
- resolve the remote LingXing DB host from the UUID API

## Request Flows

## LingXing Flow

```text
run_batch_request_lx.bat
  -> batch_request_lx.py
    -> read 产品信息汇总-{group_name}.xlsx
    -> select_value_from_uuid(...)
    -> get_lingxing_credentials(remote_ip)
    -> POST /rpc { method: lx_get_keyword_rank_data }
      -> main.py
        -> _ensure_lx_storage()
        -> lx_get_keyword_rank_data(...)
          -> search_monitored_products(...)
          -> search_monitored_keywords(...)
          -> get_keyword_chart(...)
        -> LXMySQLHandler.process_lx_response_to_mysql(...)
          -> write local MySQL tables
```

### LingXing credential dependency chain

1. UUID API returns the remote DB host.
2. `db_config.get_lingxing_credentials()` connects to that remote DB.
3. The remote DB returns `auth_token`, `company_id`, and `uid`.
4. Those credentials are used in LingXing API requests.

### LingXing output tables

- `mobile_ad_rank`
- `mobile_natural_rank`
- `pc_ad_rank`
- `pc_natural_rank`

## SIF Flow

```text
run_batch_request_sif.bat
  -> batch_request_sif.py
    -> read 产品信息汇总-{group_name}.xlsx
    -> load_sif_params(group_name)
    -> POST /rpc { method: sif_get_keyword_rank_data }
      -> main.py
        -> _ensure_sif_storage()
        -> sif_get_keyword_rank_data(...)
          -> search_asin_keywords(...)
          -> get_asin_keyword_rank_data(...)
        -> SIFMySQLHandler.process_sif_response_to_mysql(...)
          -> write local MySQL tables
```

### SIF credential dependency chain

1. `db_config.load_sif_params(group_name)` reads token-related rows from the SIF config DB.
2. The batch client extracts `sif_token`.
3. The server uses that token when calling SIF APIs.

### SIF output tables

- `sif_natural_rank`
- `sif_ad_rank`

## Input Model

The input source is an Excel workbook located at:

```text
{EXCEL_BASE_DIR}\产品信息汇总-{group_name}.xlsx
```

Each row is converted into one or more tasks:

- `asin`
- `country`
- `keyword`

If the keyword cell contains `a|b|c`, the batch client expands it into three tasks.

## Exit Code Contract

The batch scripts exit with the same code returned by the Python batch clients.

Current meaning:

- `0`: all tasks succeeded
- `1`: initialization failure, invalid input, missing argument, missing Excel file, or no valid tasks
- `2`: partially successful batch
- `3`: all tasks failed

Interpretation notes:

- once RPA receives an exit code, the batch process has finished
- the numeric value indicates business outcome, not whether the process ended
- whether RPA treats non-zero codes as failure depends on the RPA-side rule configuration

## RPC Contract

The service uses HTTP POST JSON-RPC style messages on:

```text
/rpc
```

Supported methods:

- `lx_get_keyword_rank_data`
- `sif_get_keyword_rank_data`

### LingXing request shape

```json
{
  "jsonrpc": "2.0",
  "method": "lx_get_keyword_rank_data",
  "params": {
    "asin": "B000000000",
    "country": "美国",
    "keyword": "example",
    "start_time": "2026-06-01 00:00:00",
    "end_time": "2026-06-07 23:59:59",
    "auth_token": "...",
    "company_id": "...",
    "uid": "..."
  },
  "id": 1
}
```

### SIF request shape

```json
{
  "jsonrpc": "2.0",
  "method": "sif_get_keyword_rank_data",
  "params": {
    "country": "美国",
    "token": "...",
    "search_value": "example",
    "asin": "B000000000"
  },
  "id": 1
}
```

### Response pattern

Success:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "success": true
  },
  "id": 1
}
```

Failure:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "success": false,
    "error": "message"
  },
  "id": 1
}
```

Unknown method:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "Method not found"
  },
  "id": 1
}
```

## Persistence Design

The server owns persistence. Batch clients never write to local result tables directly.

### Initialization

On first use of each flow:

- create the local database if needed
- create the required tables if needed
- keep the handler instance alive in module globals

### Connection reuse

Both persistence handlers now keep a cached MySQL connection:

- `LXMySQLHandler`
- `SIFMySQLHandler`

Behavior:

- use one cached connection per handler instance
- guard connection lifecycle with `RLock`
- validate liveness with `ping(reconnect=True)`
- reconnect when a cached connection is stale
- close the cached connection on process exit via `atexit`

This reduces per-request MySQL connect/close overhead while keeping connection state under one place in the server.

## Configuration Model

Configuration is loaded from `.env` through `pydantic-settings`.

Main categories:

- RPC server host/port
- request timeouts and retry settings
- Excel base directory
- UUID API settings
- LingXing API settings
- SIF API settings
- local result DB settings
- remote credential DB settings

`config.py` also exposes helper functions:

- `build_excel_path(group_name)`
- `get_local_db_config()`
- `get_sif_db_config()`
- `get_lingxing_db_config(ipaddr)`

## Logging Model

`logger_config.py` writes logs to both:

- rotating files under `logs/`
- console stream

This design is useful for:

- local debugging
- RPA capture of console output
- post-run troubleshooting from files

## Concurrency Notes

The current design is safe for light concurrency, but it is optimized for sequential or low-parallel batch execution.

Important characteristics:

- one cached local MySQL connection per handler
- one `RLock` per handler
- writes inside a given handler are serialized by that lock
- LX and SIF handlers do not share a lock

This is a reasonable fit for the current usage pattern:

- RPC service stays up
- LingXing batch runs
- SIF batch runs afterward

If future throughput requirements increase, likely next steps are:

1. switch insert loops to batched SQL execution
2. replace single cached connections with a connection pool
3. introduce explicit batch RPC methods instead of per-keyword RPC calls

## Failure Domains

Main external failure points:

- Excel file missing or malformed
- UUID API unavailable
- LingXing remote credential DB unavailable
- SIF config DB unavailable
- LingXing API unavailable or changed
- SIF API unavailable or changed
- local MySQL unavailable
- local RPC service not running

The current implementation logs failures and keeps per-task success/failure accounting in the batch clients.
