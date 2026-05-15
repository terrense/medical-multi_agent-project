# Medical Multi-Agent Project

多智能体医疗助手项目，包含：

- **medix-agent-swarm** — 主应用：Swarm 协作、Redis / PostgreSQL / Mem0 记忆、Milvus 知识库、Web UI
- **MediX-R1** — 训练与评测相关代码

## 快速开始

1. 复制配置：`cp config.example.py config.py`（Windows 下手动复制并填写 API Key）
2. 进入 `medix-agent-swarm`，按 `docs/MEMORY_GUIDE.md` 启动 Docker 与依赖
3. 命令行：`python main.py`  
4. Web 界面：`python api/server.py` → http://127.0.0.1:8765

## 说明

`config.py` 含密钥，已在 `.gitignore` 中排除，不会提交到 GitHub。克隆后请自行创建该文件。
