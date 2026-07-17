# GDA-MCP-Server

通过 MCP 调用 [GDA](https://github.com/charles2gan/GDA-android-reversing-Tool) 的 **CLI Server 模式**（`gda.exe -sv`），在 Cursor / Claude 等客户端里做 Android APK 静态分析。

**不依赖 GDA GUI，不需要 32 位 Python。**

```text
Cursor / Claude
    │  MCP (stdio)
    ▼
gda_mcp_server.py          ← FastMCP
    │  TCP 文本协议
    ▼
gda.exe -sv <apk> <port>   ← 默认端口 18888
```

---

## 环境要求

| 项 | 说明 |
|----|------|
| OS | Windows（GDA 仅支持 Windows） |
| Python | 3.10+（推荐 64 位，如 `D:\py312\python.exe`） |
| 依赖 | `fastmcp>=3.0.2`（见 `requirements.txt`） |
| GDA | 本机已安装 `GDA.exe`（例如 `D:\mytools\GDA4.12\GDA.exe`） |

安装依赖：

```bash
pip install -r requirements.txt
```

---

## Cursor 配置

编辑 `%USERPROFILE%\.cursor\mcp.json`，增加（路径按本机修改）：

```json
{
  "mcpServers": {
    "gda-mcp": {
      "command": "D:\\py312\\python.exe",
      "args": [
        "C:\\Users\\ZW\\Desktop\\新建文件夹\\gda-mcp-server\\gda_mcp_server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "GDA_EXE": "D:\\mytools\\GDA4.12\\GDA.exe",
        "GDA_PORT": "18888"
      },
      "timeout": 1800,
      "disabled": false
    }
  }
}
```

| 环境变量 | 含义 | 默认 |
|----------|------|------|
| `GDA_EXE` | `GDA.exe` 绝对路径 | `D:\mytools\GDA4.12\GDA.exe` |
| `GDA_PORT` | `-sv` 监听端口 | `18888`（避开常见代理占用的 8888） |
| `GDA_HOST` | 连接地址 | `127.0.0.1` |
| `GDA_PAGE_SIZE` | 分页默认行数 | `200` |
| `GDA_MAX_PAGE_SIZE` | 单页最大行数 | `2000` |

配置后在 Cursor **Settings → MCP** 中启用 `gda-mcp`，必要时刷新 / 重启。

---

## 基本用法

在 Cursor 对话里用自然语言即可，例如：

```text
使用 gda-mcp 分析 C:\path\to\xxx.apk
使用 gadmcp 分析 C:\Users\ZW\Desktop\新建文件夹\RshMod_6.69-RshMod.apk
帮我用 GDA MCP 看一下这个 APK 的登录和授权逻辑：D:\samples\app.apk
```

Agent 会自动调用 `gda_start_server` 并继续 `binfo` / `attsf` / `find` 等工具，无需手写命令。

分析前必须先启动（或挂接）GDA server（工具层流程）：

```text
1. gda_start_server(apk_file="C:\\path\\to\\app.apk")
2. gda_binfo() / gda_attsf() / gda_malscan() / gda_find(...) / gda_dec(...)
3. gda_stop_server()
```

若本机已有 `gda.exe -sv` 在跑：

```text
gda_attach(host="127.0.0.1", port=18888)
```

### 推荐分析顺序

1. **侦察**：`gda_binfo` → `gda_permission` → `gda_axml` → `gda_packer` → `gda_cert`
2. **攻击面**：`gda_attsf` → `gda_malscan` → `gda_sensinf` → `gda_uri` / `gda_api`
3. **深挖**：`gda_find` → `gda_listm` → `gda_dec` / `gda_dasm` → `gda_xref`

与 **jadx-mcp** 搭配：GDA 找可疑点，jadx 精读 Java / 资源 / 重命名。

---

## 工具一览

### 会话

| 工具 | 说明 |
|------|------|
| `gda_start_server` | 启动 `gda.exe -sv <apk> <port>` |
| `gda_attach` | 连接已在运行的 `-sv` |
| `gda_stop_server` | 停止本 MCP 拉起的进程 |
| `gda_status` | 查看运行状态 / APK / 端口 |

### 侦察

| 工具 | 说明 |
|------|------|
| `gda_binfo` | 包名、哈希、MainActivity、DEX 统计 |
| `gda_pname` | 包名 |
| `gda_permission` | 权限 |
| `gda_axml` | AndroidManifest |
| `gda_cert` | 证书 |
| `gda_packer` | 加壳检测 |
| `gda_header` | 第 n 个 DEX 头 |
| `gda_appstr` | 方法引用的字符串（可分页） |
| `gda_interface` | 接口类 |
| `gda_help` | GDA shell 帮助 |

### 安全 / 攻击面

| 工具 | 说明 |
|------|------|
| `gda_attsf` | 导出组件 / 攻击面 |
| `gda_malscan` | 恶意行为扫描（可分页） |
| `gda_sensinf` | 敏感信息（可分页） |
| `gda_uri` | URL / 路径（可分页） |
| `gda_api` | 敏感 API（可分页） |
| `gda_native` | Native 方法 |

### 代码

| 工具 | 说明 |
|------|------|
| `gda_listm` | 列类方法（可分页） |
| `gda_dec` | 反编译类/方法（可分页），推荐 `class@xxxxxx` |
| `gda_dasm` | 反汇编方法，如 `method@0045F0` |
| `gda_sclass` / `gda_pclass` | 子类 / 父类（class index 十六进制） |
| `gda_find` | 搜索 class/method/field/string/api/all（可分页） |
| `gda_xref` | 交叉引用（可分页） |
| `gda_raw` | 发送原始 GDA 命令（可分页） |
| `gda_set_output` | `set -o` 输出到文件 |

---

## 分页（大输出）

下列工具支持 **按行** `offset` / `count`（默认每页 200 行，单页最多 2000）：

`gda_malscan` · `gda_api` · `gda_find` · `gda_appstr` · `gda_sensinf` · `gda_uri` · `gda_dec` · `gda_listm` · `gda_xref` · `gda_raw`

返回示例：

```json
{
  "ok": true,
  "cmd": "malscan",
  "total_lines": 5000,
  "offset": 0,
  "count": 200,
  "truncated": true,
  "next_offset": 200,
  "text": "..."
}
```

翻页时对同一命令会缓存全文，避免重复跑 GDA。`start` / `stop` / `attach` 会清空缓存。

```text
gda_malscan()
gda_malscan(offset=200, count=200)
gda_find(search_type="string", name="http", offset=0, count=100)
```

### `gda_find` / `gda_xref` 参数

**find** `search_type`：

`class` · `class_with_package` · `method` · `method_with_package` · `field` · `api_method` · `string` · `all`

**xref** `xref_type`：

`class` · `method` · `field` · `string` · `resource` · `all`

**dec 提示**：优先用 `find` 得到的 `class@xxxxxx` / `method@xxxxxx`，比 `Lcom/...;` 更稳。

---

## 命令行启动（可选）

Cursor 一般用 stdio，无需手动传参。若要单独跑：

```bash
# 默认 stdio（给 MCP 客户端用）
python gda_mcp_server.py

# 指定 GDA 路径
python gda_mcp_server.py --gda-exe "D:\mytools\GDA4.12\GDA.exe"

# HTTP 传输（少用）
python gda_mcp_server.py --http --host 127.0.0.1 --port 8765
```

注意：`--port` 是 **MCP HTTP 端口**，不是 GDA `-sv` 的 `GDA_PORT`。

本地自检（不启 GDA）：

```bash
python smoke_check.py
```

---

## 目录结构

```text
gda-mcp-server/
  gda_mcp_server.py   # FastMCP 入口与工具注册
  src/
    gda_sv.py         # -sv 进程管理、TCP 客户端、分页、命令映射
    __init__.py
  requirements.txt
  smoke_check.py
  README.md           # 本说明
```

---

## 能力边界（与 jadx-mcp）

| GDA-MCP 更强 | jadx-MCP 更强 |
|--------------|---------------|
| malscan / attsf / packer / cert / sensinf | GUI 选中类、可读 Java 精读 |
| 无头启停 APK | 资源文件、重命名写回 |
| 原生恶意/攻击面扫描 | 调试器、包树与字段 API |

**不做**：GDA GUI 联动、进程内 Python 脚本 bridge（需 32 位 Python）。

---

## 常见问题

**1. `GDA -sv is not running`**  
先调用 `gda_start_server(apk_file=...)`。

**2. 端口被占用**  
改 `GDA_PORT`（不要用 8888，若本机 Reqable 等已占用）。

**3. 启动失败 / 找不到 GDA**  
检查 `GDA_EXE` 是否指向真实的 `GDA.exe`。

**4. 大结果把上下文撑爆**  
用分页：先看 `truncated` / `next_offset`，再翻页。

**5. `find -C .` 一类「列全部类」**  
不可靠且可能拖死 `-sv`；请用具体包名或关键词搜索。

**6. 改了工具但 Cursor 仍是旧列表**  
在 MCP 面板刷新或重启 Cursor。
