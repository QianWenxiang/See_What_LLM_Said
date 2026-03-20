# 🔍 See What LLM Said

一个极简而强大的 LLM 接口抓包与交互可视化看板。
它能作为中转代理，实时捕捉和分析您的 Agent 应用与大模型产生的所有通信。

![Dashboard Preview](https://via.placeholder.com/800x400?text=See+What+LLM+Said+Dashboard)

## ⚡ 极速起步 (只需 3 步)

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件，并填入你要实际调用的 LLM 地址和密钥：

```ini
LLM_API_URL="https://api.openai.com/v1"
LLM_API_KEY="sk-xxxxxxxxxxxxxxxxxxx"

```

### 3. 一键启动

```bash
python see_what_llm_said.py
```

---

## 🚀 如何使用它测试你的插件/Agent？

配置好后你的看板会运行在 `http://localhost:7654`。
此时这个端口**同时承担了 Web 面板和 API 代理的功能**。

只需在你的 LLM 应用或插件（如 VSCode 插件, AutoGPT, 任何代码助手等）中填入：

- **API Base URL**: `http://localhost:7654` (或 `http://localhost:7654/v1`)
- **API Key**: 随便填，或者不填都可以（它会自动使用 `.env` 中配置的真实密钥）

现在，你的插件发出的所有调用都会被实时呈现在看板上，并且完美支持中英文切换、响应耗时图表、Token 估算、和历史记录导出！


<img width="2534" height="1136" alt="image" src="https://github.com/user-attachments/assets/8a1e3d82-9da9-49fb-b10f-bd0f7c46f9da" />

