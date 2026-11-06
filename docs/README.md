# RAG Agent v2

RAG Agent v2 是一个 Python 文档问答项目。它将上传的资料解析为 Markdown，按知识库建立检索索引，再将召回片段交给对话模型生成流式回答。仓库包含 FastAPI 后端和 Streamlit 演示界面。

- [架构与源码分析](ARCHITECTURE.md)记录文档入库、检索、会话记忆、数据存储和已知问题。
- [演示截图](images/)展示聊天、文档管理、知识库管理和会话管理界面。

## 本地启动

以下命令使用 PowerShell，请在仓库根目录执行。`config.py` 和部分提示词加载逻辑使用相对于当前目录的路径。

1. 准备 Python 3.11 或以上版本、uv，以及可连接的 MongoDB。默认连接 `mongodb://localhost:27017`。如果 Windows 已安装名为 `MongoDB` 的系统服务，可用管理员终端执行 `Start-Service MongoDB`。
2. 安装锁定的依赖，并在启动后端的终端设置密钥。

   ```powershell
   uv sync --locked --no-install-project
   $env:BAILIAN_API_KEY = '<百炼 API Key>'
   $env:DEEPSEEK_API_KEY = '<DeepSeek API Key>'
   ```

   默认对话、检索辅助和文档元数据提取使用百炼 `qwen-plus`，向量调用使用百炼 `text-embedding-v4`。百炼向量适配器在导入应用时就会读取密钥。会话服务默认还会初始化 DeepSeek 作为记忆摘要模型。只有百炼密钥时，可在现有的 `[tool.memory]` 下增加 `llm_provider = "bailian"` 和 `llm_model = "qwen-plus"`。

3. 启动 FastAPI。

   ```powershell
   uv run --no-sync uvicorn src.api.main:app --host 127.0.0.1 --port 8000
   ```

   浏览器访问 [Swagger UI](http://127.0.0.1:8000/docs)。`GET /health` 返回 `{"status":"ok"}`，用于确认 HTTP 服务响应。MongoDB 初始化失败时，先核对服务状态和连接字符串，再检查[数据库驱动兼容性](ARCHITECTURE.md#已知问题)。

4. 在另一个终端启动 Streamlit，打开 [演示界面](http://127.0.0.1:8501)。

   ```powershell
   uv run --no-sync streamlit run streamlit_demo.py
   ```

   演示界面请求 `http://127.0.0.1:8000`，使用固定的 `streamlit_user`。后端地址和演示用户在 [streamlit_demo.py](../streamlit_demo.py) 中设置。

## 配置

默认值以 [pyproject.toml](../pyproject.toml) 和实际调用点为准。

| 配置段 | 当前行为 |
| --- | --- |
| `[tool.mongo]` | FastAPI 读取 `uri` 和 `database`。仓库预置的是 `db_name`，因此 API 使用回退库名 `rag_agent`。需要指定库名时，在该段增加 `database`。 |
| `[tool.chroma]` | 默认使用本地持久化目录 `data/chroma_db`。应用默认配置加载只读取 `persist_directory`。 |
| `[tool.dialog]` | 流式回答和会话标题默认使用 `bailian/qwen-plus`。 |
| `[tool.rag]` | 存储路径、上传上限和增强检索开关。文档路由、查询改写、重排及元数据提取默认使用 `bailian/qwen-plus`。`embedding_provider` 和 `embedding_model` 未接入实际向量调用。 |
| `[tool.rag.docling]` | 默认关闭 OCR 和图片描述，开启表格结构识别和单元格匹配。 |
| `[tool.memory]` | 默认向量召回，`top_k = 5`，摘要模型回退到 `deepseek/deepseek-chat`。相似度阈值配置尚未接入检索。 |

## 文档问答流程

在 Streamlit 的**文档管理**中上传有标题和正文的 Markdown 文件。等待解析完成后，在**知识库管理**中创建空知识库，选择 `hierarchical` 分块，再用添加文件操作关联已解析文档。回到**聊天**页，选择该知识库，提一个能从正文中核对答案的问题。

下面的 PowerShell 7 示例可直接通过 API 检查同一条流程。先在仓库根目录准备 `sample.md`，例如标题为 `# 会议安排`，正文为“项目会议在 B-204 室举行”。

**上传并确认解析状态**

```powershell
$api = 'http://127.0.0.1:8000/api/v1'
$doc = curl.exe --fail --silent --show-error -F 'file=@sample.md' "$api/document/upload" |
    ConvertFrom-Json

(Invoke-RestMethod "$api/document").documents |
    Where-Object { $_.id -eq $doc.id } |
    Select-Object -ExpandProperty metadata
```

上传返回 201 后，FastAPI 在后台执行解析。重复查询，等 `is_prased` 变为 `true` 再继续。该字段沿用接口里的拼写。若一直为 `false`，查看后端日志中的解析异常。

**创建知识库、添加文档并发起聊天**

```powershell
$kbBody = @{
    name = 'smoke-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    split_method = 'hierarchical'
    chunk_size = 300
    retriever_type = 'hybrid'
} | ConvertTo-Json
$kb = Invoke-RestMethod -Method Post -Uri "$api/knowledge-bases" `
    -ContentType 'application/json' -Body $kbBody

Invoke-RestMethod -Method Post -Uri "$api/knowledge-bases/$($kb.id)/files/$($doc.id)"

$session = Invoke-RestMethod -Method Post -Uri "$api/sessions" `
    -ContentType 'application/json' -Body '{"user_id":"smoke_user"}'

@{
    session_id = $session.session_id
    content = '项目会议在哪个房间举行？'
    knowledge_base_id = $kb.id
} | ConvertTo-Json -Compress |
    curl.exe --fail --silent --show-error --no-buffer `
        -H 'Content-Type: application/json' --data-binary '@-' "$api/chat-stream"

Invoke-RestMethod "$api/sessions/$($session.session_id)"
```

建库时省略 `record_ids`，添加文档时传上传接口返回的 `id`。显式指定 `hierarchical` 可避开当前默认 `recursive` 分块的参数错误。聊天可省略 `knowledge_base_id` 进入普通问答。完整消费流后，会话历史应包含本轮提问和回答。

## API 速查

以下路径均带 `/api/v1` 前缀。请求及响应字段见 [API 模型](../src/api/models.py)。

| 方法和路径 | 用途及当前行为 |
| --- | --- |
| `POST /sessions` | 创建会话，请求包含 `user_id` 和可选 `metadata`，返回 `session_id`。 |
| `GET /sessions/{session_id}` | 返回 `{"messages":[...]}`，每条记录包含 `role`、`content`。 |
| `GET /sessions/{session_id}/messages` | 接受 `offset`、`limit`，当前切片有边界错误。读取完整历史可用上一行接口。 |
| `GET /session-list?user_id=...` | 按用户查找会话，按创建时间升序返回，当前未应用 `offset`、`limit`。 |
| `POST /sessions/{session_id}/exit` | 将退出处理提交到后台。空会话删除，有消息的会话保留并尝试处理记忆和标题。 |
| `DELETE /sessions/{session_id}` | 将删除提交到后台，响应仅表示任务已安排。 |
| `POST /chat-stream` | 请求包含 `session_id`、`content`，可选 `knowledge_base_id`、`metadata`。返回 `text/plain` 增量正文。 |
| `POST /chat` | 已注册的非流式接口，服务实现目前抛出 `NotImplementedError`。 |
| `GET /document` | 返回 `total` 和 `documents`，含解析状态及元数据。 |
| `POST /document/upload` | 使用 `multipart/form-data` 的 `file` 字段上传，返回文件记录并安排后台解析。 |
| `DELETE /document/{record_id}` | 删除文档及关联的数据库记录，本地文件和索引清理见[已知问题](ARCHITECTURE.md#已知问题)。 |
| `POST /knowledge-bases` | 创建知识库。当前请提交空 `record_ids` 或省略它。 |
| `GET /knowledge-bases` | 接受 `skip`、`limit`。响应的 `total` 是本页条数。 |
| `GET /knowledge-bases/{kb_id}` | 获取知识库及关联文档 ID。 |
| `DELETE /knowledge-bases/{kb_id}` | 当前路由删除知识库记录，关联数据的清理见[已知问题](ARCHITECTURE.md#已知问题)。 |
| `GET /knowledge-bases/{kb_id}/files` | 列出知识库中仍存在的文档记录。 |
| `POST /knowledge-bases/{kb_id}/files/{file_id}` | 使用文档 ID 添加单个文件，请求等待切块和索引。 |
| `POST /knowledge-bases/{kb_id}/files` | 请求体是文档 ID 的 JSON 字符串数组，按顺序添加。 |
| `DELETE /knowledge-bases/{kb_id}/files/{file_id}` | 服务将路径参数解释为关联记录 ID，当前删除调用存在缺陷。 |

路由实现见 [聊天与会话](../src/api/routers/chat.py)、[文档](../src/api/routers/document.py)和[知识库](../src/api/routers/knowledge_base.py)。

## 模型支持

聊天工厂接入 `bailian` 和 `deepseek`。仓库也有 OpenAI 和 Anthropic 适配器文件，其中 `openai` 工厂分支明确抛出未实现异常，Anthropic 尚未注册。Embedding 工厂接入百炼，当前请求固定使用 `text-embedding-v4`。实现见 [聊天工厂](../src/llm/factory.py)和[向量工厂](../src/embedding/factory.py)。

项目作者 Kyleidoscopist。问题与改动可通过仓库的 GitHub Issue 和 Pull Request 提交。
