# RAG Agent v2

RAG Agent v2 将上传的资料解析为 Markdown，按知识库建立检索索引，再将召回片段交给对话模型生成回答。React 工作台位于 [frontend/](../frontend/)，FastAPI 和 Python 服务位于 [backend/](../backend/)。

- [架构与源码分析](ARCHITECTURE.md)记录文档入库、检索、会话记忆、数据存储和已知问题。
- [旧版演示截图](images/)记录 Streamlit 界面。

## 本地启动

从根目录启动服务。后端默认读取 `backend/pyproject.toml`，MongoDB 地址为 `mongodb://localhost:27017`。启动、创建会话和读取历史可以在无模型密钥时运行。[本地启动步骤](../README.md#本地启动)

开发服务器把 `/api/` 请求转发到本机 FastAPI。端口变更时可按 [frontend/.env.example](../frontend/.env.example) 设置 `frontend/.env.local`。工作台默认使用 `streamlit_user`，因此可继续读取旧演示的会话。该标识用于本地单用户使用，多人部署需要后端鉴权和资源归属校验。

`npm --prefix frontend run build` 将前端打包到 `frontend/dist/`。可用 `npm --prefix frontend run preview` 在本地预览。静态部署时将 `/api/` 转发到 FastAPI，保持流式响应逐段抵达，并将前端会话路径回退到 `index.html`。

旧版 Streamlit 演示仍可从仓库根目录启动。

```powershell
uv run --project backend --no-sync streamlit run backend/streamlit_demo.py
```

## 配置

在工作台打开 **模型配置**，为对话回答和会话标题、记忆摘要、知识检索与文档处理分别选择 DeepSeek 或阿里云百炼并填写模型 ID。保存后，后续调用读取新设置。首次使用时，模型选择来自下表对应的 TOML 配置段。

文本模型使用页面保存的 API Key，移除后回退到 `DEEPSEEK_API_KEY` 或 `BAILIAN_API_KEY` 环境变量。配置与页面录入的密钥保存在本地 MongoDB 的 `model_settings` 集合中，密钥以明文存储，页面和查询接口只显示密钥来源。需要将密钥留在环境变量中时，页面的密钥输入框可留空。

向量模型从 `[tool.rag]` 读取，百炼向量调用通过 `BAILIAN_API_KEY` 取密钥。

默认值以 [pyproject.toml](../backend/pyproject.toml) 和实际调用点为准。

| 配置段 | 当前行为 |
| --- | --- |
| `[tool.mongo]` | 使用 PyMongo 异步客户端。默认库名为 `rag_agent`，优先读取 `database`，兼容旧配置项 `db_name`。 |
| `[tool.chroma]` | 默认使用本地持久化目录 `data/chroma_db`。应用默认配置加载只读取 `persist_directory`。 |
| `[tool.dialog]` | 流式回答和会话标题默认使用 `bailian/qwen-plus`。 |
| `[tool.rag]` | 存储路径、上传上限和增强检索开关。辅助模型默认使用 `bailian/qwen-plus`，向量模型读取 `embedding_provider` 和 `embedding_model`。切换向量模型时需要重建已有向量索引。 |
| `[tool.rag.docling]` | 默认关闭 OCR 和图片描述，开启表格结构识别和单元格匹配。 |
| `[tool.memory]` | 历史召回默认关闭。启用 `retrieve_enabled` 后，可用 `retrieve_timeout_seconds` 设置超时。摘要模型默认回退到 `deepseek/deepseek-chat`。 |

## 文档问答流程

打开**资料库 → 文档**，上传有标题和正文的 Markdown 文件。解析完成后进入**知识库**，创建一个知识库并添加已就绪文档。索引完成后选择**用此知识库提问**，输入一个能从正文核对答案的问题。

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

上传返回 201 后，FastAPI 在后台执行解析。重复查询，等 `metadata.status` 变为 `ready` 再继续。`metadata.is_prased` 是保留的兼容字段。解析失败时，列表显示 `failed`，可重新上传相同文件触发重试。

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

添加文档时传上传接口返回的 `id`。也可在创建知识库时通过 `record_ids` 指定已解析的文档。API 默认使用 `recursive` 分块，示例选择按 Markdown 标题切分。聊天可省略 `knowledge_base_id` 进入普通问答。完整消费流后，会话历史应包含本轮提问和回答。需要完整 JSON 响应时，可把同一请求体发送到 `POST /api/v1/chat`。

## API 速查

以下路径均带 `/api/v1` 前缀。请求及响应字段见 [API 模型](../backend/src/api/models.py)。

| 方法和路径 | 用途及当前行为 |
| --- | --- |
| `POST /sessions` | 创建会话，请求包含 `user_id` 和可选 `metadata`，返回 `session_id`。 |
| `GET /sessions/{session_id}` | 返回 `{"messages":[...]}`，每条记录包含 `role`、`content`。 |
| `GET /sessions/{session_id}/messages` | 接受 `offset`、`limit`，从最新消息向前分页，页内按时间顺序返回。 |
| `GET /session-list?user_id=...` | 按用户查找会话，支持 `offset`、`limit`。默认按创建时间升序，工作台使用 `order=desc` 从新到旧加载。 |
| `POST /sessions/{session_id}/exit` | 返回 202，后台退出空会话或为有历史的会话尝试处理记忆和标题。 |
| `DELETE /sessions/{session_id}` | 等待会话和对应向量记忆的清理后返回。 |
| `POST /chat-stream` | 请求包含 `session_id`、`content`，可选 `knowledge_base_id`、`metadata`。返回 `text/plain` 增量正文。 |
| `POST /chat` | 请求字段与流式接口相同。返回 `session_id`、`user_message` 和 `assistant_message`。 |
| `GET /model-settings` | 读取 `dialog`、`memory`、`rag` 的 `provider` 和 `model`，并返回各服务商的密钥来源。 |
| `PUT /model-settings` | 提交三种用途的模型选择。可选的 `api_keys` 按服务商更新密钥，省略对应字段会保留原值，`null` 会移除数据库中的密钥。 |
| `GET /document` | 返回 `total` 和 `documents`，含解析状态及元数据。 |
| `POST /document/upload` | 使用 `multipart/form-data` 的 `file` 字段上传，返回文件记录并安排后台解析。 |
| `DELETE /document/{record_id}` | 删除文档、各知识库中的关联索引、原文件和 Markdown。 |
| `POST /knowledge-bases` | 创建知识库。可通过 `record_ids` 添加已解析文档。 |
| `GET /knowledge-bases` | 接受 `skip`、`limit`。响应的 `total` 是本页条数。 |
| `GET /knowledge-bases/{kb_id}` | 获取知识库及关联文档 ID。 |
| `DELETE /knowledge-bases/{kb_id}` | 删除知识库及其关联和索引，保留原文档。 |
| `GET /knowledge-bases/{kb_id}/files` | 列出知识库中仍存在的文档记录。 |
| `POST /knowledge-bases/{kb_id}/files/{file_id}` | 使用文档 ID 添加单个文件，请求等待切块和索引。 |
| `POST /knowledge-bases/{kb_id}/files` | 请求体是文档 ID 的 JSON 字符串数组，按顺序添加。 |
| `DELETE /knowledge-bases/{kb_id}/files/{file_id}` | 清理该知识库中的关联和索引，接受文档 ID，也兼容旧的关联记录 ID。 |

路由实现见 [聊天与会话](../backend/src/api/routers/chat.py)、[文档](../backend/src/api/routers/document.py)和[知识库](../backend/src/api/routers/knowledge_base.py)。

## 模型支持

聊天工厂接入 `bailian` 和 `deepseek`。仓库也有 OpenAI 和 Anthropic 适配器文件，其中 `openai` 工厂分支明确抛出未实现异常，Anthropic 尚未注册。Embedding 工厂接入百炼，默认使用 `text-embedding-v4`。实现见 [聊天工厂](../backend/src/llm/factory.py)和[向量工厂](../backend/src/embedding/factory.py)。

## 回归测试

```powershell
uv run --directory backend --no-sync python -m unittest discover -s tests -v
npm --prefix frontend run build
```

设置 `RAG_TEST_MONGOD` 为本机 `mongod` 的路径，再运行同一命令，可额外测试真实 MongoDB 上的上传、入库、两种聊天接口、删除、模型配置持久化及密钥轮换。测试启动自己的回环地址实例，使用临时目录、独立 Chroma 和模拟模型。

项目作者 Kyleidoscopist。问题与改动可通过仓库的 GitHub Issue 和 Pull Request 提交。
