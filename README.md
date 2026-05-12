# 具身智读

一个本地网页服务，用 arXiv 抓取近期机器人、具身智能、VLA、操作、导航和运动控制相关论文，并用 Qwen 生成中文快速阅读摘要。

## 功能

- 每日/近 2 天/近 7 天机器人与具身智能论文速览
- Qwen 中文总览、主题提炼、单篇论文价值和局限总结
- 日报式速览，自动生成今日结论、必读论文、方向信号和阅读队列
- 一键复制 Markdown 速览，方便发到群、周报或笔记系统
- 从具身行业从业者视角抽取产业信号：真机、开源、具身数据、DAgger/RL、移动操作、灵巧操作、灵巧手、具身模型、Sim2Real 和评测
- 按产业相关度排序，并提供核心关注、重点跟踪、快速扫读、归档备查四档判断
- 搜索标题、作者、方法、摘要和个人笔记
- 收藏论文、设置分类、标记未读/在读/已读/跳过
- 给论文写本地笔记，刷新后保留
- 按收藏、核心关注、阅读状态、笔记和分类筛选

## 专业分类

默认分类围绕具身机器人工作流设置：

- 本体/硬件
- 预训练
- 后训练
- RL/DAgger
- 具身数据
- 具身推理
- 移动操作
- 灵巧操作
- 灵巧手
- 仿真/Sim2Real
- 评测/Benchmark
- 待复现

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

## 本地数据

运行缓存写入 `.cache/`，收藏、分类、阅读状态和笔记写入 `.data/library.json`。

这两个目录都已加入 `.gitignore`，不会提交到 GitHub。
