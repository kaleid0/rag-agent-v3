# RAG Agent v2

面向本地使用的文档问答工作台。上传资料、建立知识库，然后在对话中选择检索范围并查看流式回答。

## 项目结构

```text
frontend/        React、TypeScript、Vite，包含对话、资料库和模型配置
backend/         FastAPI、RAG 业务代码、Python 配置和回归测试
docs/            使用指南、API 速查和架构说明
data/            本地运行生成的原文件、解析结果和检索索引
```

## 本地启动

需要 Python 3.11 或以上版本、uv、Node.js 20.19+（20.x）或 22.12+、npm 和运行中的 MongoDB。以下命令在仓库根目录执行。

后端终端

```powershell
uv sync --project backend --locked --no-install-project
uv run --project backend --no-sync uvicorn src.api.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

前端终端

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

打开 [RAG 工作台](http://127.0.0.1:5173) 或 [FastAPI 文档](http://127.0.0.1:8000/docs)。启动后端时保留仓库根目录作为工作目录，以便继续使用已有 `data/` 下的资料和索引。

在工作台顶部打开 **模型配置**，选择对话、记忆和知识检索使用的模型，并填写对应服务商的密钥。也可以在启动后端前设置 `BAILIAN_API_KEY` 和 `DEEPSEEK_API_KEY`。向量索引和检索使用的百炼密钥通过 `BAILIAN_API_KEY` 提供。

如果仓库根目录已有 Python `.venv`，可在后端终端先运行 `$env:UV_PROJECT_ENVIRONMENT = (Resolve-Path .venv).ProviderPath` 继续使用它。

- [使用指南、配置和 API 速查](docs/README.md)
- [架构与源码说明](docs/ARCHITECTURE.md)
