# Qwen 具身论文雷达

一个本地网页服务，用 arXiv 抓取近期机器人、具身智能、VLA、操作、导航和运动控制相关论文，并用 Qwen 生成中文快速阅读摘要。

## 启动

```bash
python3 server.py
```

打开：

```text
http://127.0.0.1:8787
```

## 启用 Qwen

服务优先读取 `DASHSCOPE_API_KEY`，也兼容 `QWEN_API_KEY`。

```bash
export DASHSCOPE_API_KEY="你的 DashScope API Key"
export QWEN_MODEL="qwen3.6-max-preview"
export QWEN_ENABLE_THINKING="1"
python3 server.py
```

默认调用 DashScope OpenAI 兼容接口：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

如果你有自建兼容服务，可以设置：

```bash
export QWEN_BASE_URL="https://your-host/v1/chat/completions"
```

## API

- `GET /api/health`：服务和 Qwen key 状态
- `GET /api/settings`：筛选类别和关键词
- `GET /api/papers?days=2&limit=18&qwen=1`：论文列表、主题、每日总览

缺少 API key 时，服务会降级为基于摘要和关键词的规则梳理，页面仍可使用。
