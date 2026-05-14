# 本地 arXiv 论文工作台

一个本地 Web 应用，用于按日期抓取 arXiv 论文、按机器人/VLA/具身智能相关子页浏览，并把 Qwen 总结缓存到本地。后端是 Python 标准库 HTTP 服务，前端是 Vue 3 + Vite。

## 运行

```bash
npm install
python3 app.py
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

也可以构建后由 Python 单独服务：

```bash
npm run build
python3 app.py
```

构建后打开 `http://127.0.0.1:8787`。

如果 8787 被占用：

```bash
PORT=8789 python3 app.py
```

## Qwen 配置

总结功能使用 OpenAI-compatible Chat Completions 接口。推荐直接在页面顶部的 **Qwen API / 前台接入、检测和锁定** 面板中填写：

- API Key
- 模型名，例如 `qwen-plus`
- Base URL，例如 `https://dashscope.aliyuncs.com/compatible-mode/v1`

点击“检测并锁定”后，配置会保存到 `.data/qwen.json`。前端不会回显完整 key，只显示尾号。

也可以继续使用环境变量。环境变量优先级更高，且前台不能覆盖：

```bash
export DASHSCOPE_API_KEY="你的 key"
export QWEN_MODEL="qwen-plus"
python3 app.py
```

可选：

```bash
export QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

## 本地文件

- `.cache/arxiv_pool/<keyword-signature>.json`：同一关键词签名下的 arXiv 聚合池。
- `.cache/date_papers/<YYYY-MM-DD>/<keyword-signature>.json`：日期论文池。
- `.cache/qwen_summaries/<YYYY-MM-DD>/<keyword-signature>/...`：Qwen 总结缓存。
- `.data/library.json`：收藏、分类、阅读状态和笔记。
- `.data/settings.json`：前端维护的检索关键词和抓取数量。
- `.data/qwen.json`：前台检测并锁定后的本地 Qwen 配置。

关键词签名由规范化后的关键词集合计算，同一天不同关键词不会串缓存。
