# Amazon 关键词排名采集系统

从领星 (LingXing) 和 SIF 两个平台批量采集亚马逊商品关键词排名数据，并写入本地 MySQL 数据库。

---

## 项目结构

```
├── main.py                    # Flask JSON-RPC 服务入口
├── _lx_get_keyword_rank.py    # 领星排名数据获取逻辑
├── _sif_get_keyword_rank.py   # SIF 排名数据获取逻辑
├── lx_response_to_mysql.py    # 领星数据写入 MySQL
├── sif_response_to_mysql.py   # SIF 数据写入 MySQL
├── batch_request_lx.py        # 领星批量请求脚本
├── batch_request_sif.py       # SIF 批量请求脚本
├── run_batch_request_lx.bat   # 领星批量任务启动脚本（Windows）
├── run_batch_request_sif.bat  # SIF 批量任务启动脚本（Windows）
├── config.py                  # 配置项（读取 .env）
├── db_config.py               # 数据库凭证加载
├── logger_config.py           # 日志配置
├── .env                       # 环境变量（本地填写，勿提交）
└── requirements.txt           # 依赖列表
```

---

## 运行流程

```
Excel 文件（ASIN + 站点 + 关键词）
        │
        ▼
batch_request_lx.py / batch_request_sif.py
        │  逐条发送 JSON-RPC 请求
        ▼
main.py（Flask RPC Server :5001）
        │  调用平台 API 获取排名
        ▼
lx_response_to_mysql / sif_response_to_mysql
        │  写入本地 MySQL
        ▼
ranking_db（MySQL 数据库）
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写真实配置：

```bash
cp .env.example .env
```

主要配置项说明：

| 配置项 | 说明 |
|---|---|
| `LOCAL_DB_*` | 本地 MySQL（存储排名数据） |
| `SIF_DB_*` | 存储 SIF Token 的数据库 |
| `LINGXING_DB_*` | 领星账户信息数据库（远程） |
| `UUID_*` | 用于动态获取领星数据库 IP 的鉴权信息 |
| `EXCEL_BASE_DIR` | Excel 文件根目录 |
| `RPC_PORT` | RPC 服务监听端口（默认 5001） |

### 3. 启动 RPC 服务

```bash
python main.py
```

### 4. 执行批量采集

**方式一：直接运行**
```bash
python batch_request_lx.py <组名>
python batch_request_sif.py <组名>
```

**方式二：通过 bat 脚本（Windows）**
```bat
run_batch_request_lx.bat <组名>
run_batch_request_sif.bat <组名>
```

`<组名>` 对应 Excel 文件名，脚本会自动读取 `{EXCEL_BASE_DIR}/产品信息汇总-{组名}.xlsx`。

---

## Excel 文件格式

| 列名 | 说明 |
|---|---|
| `ASIN` | 亚马逊商品编码 |
| `站点` | 国家（如：美国、日本、德国） |
| `关键词` | 单个关键词，多个用 `\|` 分隔 |

---

## 数据库表说明

**领星（本地 `ranking_db`）**

| 表名 | 说明 |
|---|---|
| `mobile_ad_rank` | 移动端广告排名 |
| `mobile_natural_rank` | 移动端自然排名 |
| `pc_ad_rank` | PC 端广告排名 |
| `pc_natural_rank` | PC 端自然排名 |

**SIF（本地 `ranking_db`）**

| 表名 | 说明 |
|---|---|
| `sif_natural_rank` | 自然排名 |
| `sif_ad_rank` | 广告排名 |

---

## 脚本退出码

| 退出码 | 含义 |
|---|---|
| `0` | 全部成功 |
| `1` | 无有效任务 |
| `2` | 部分失败 |
| `3` | 全部失败 |

---

## 日志

日志文件存放在 `LOG_DIR`（默认 `./logs/`），按模块分文件记录，单文件上限 10MB，保留 5 个备份。
