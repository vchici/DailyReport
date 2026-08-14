# Daily Report

> AI 驱动的个人日报记录与生成工具。用自然语言随手记录待办和已完成事项，它会自动识别意图、关联历史记录并联网检索，最后为你生成一份结构化的当日日报。

## 特性速览

- **自然语言优先**：无需记忆命令，直接说「今天写完了周报」也能被正确识别意图
- **待办 ↔ 完成自动关联**：记录完成事项时，自动匹配当日待办并建立「完成 → 待办」的对应关系
- **本地历史 + 联网双重检索**：回答问题、给建议、写日报时，同时参考你的历史记录和实时网络信息
- **结构化日报**：`/report` 输出「今日概要 / 工作详情 / 关联发现 / 明日计划」四段式日报
- **本地存储**：数据以 JSON / Markdown 形式保存在 `data/` 目录

## 快速开始

1. 安装依赖

   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量

   ```bash
   cp .env.example .env
   # 编辑 .env，填入 OPENAI_API_KEY 等信息
   ```

   `.env` 支持任意 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen 等），只需修改 `OPENAI_BASE_URL` 与 `MODEL_NAME`。

3. 运行

   ```bash
   python main.py
   ```

   也可以安装后通过命令启动：

   ```bash
   pip install -e .
   dailyreport
   ```

## 命令详解

### `/plan` 记录待办

把计划要做的事记下来。支持多行输入，以单独一行的 `.` 结束。

**巧思**：记录后不是简单存一条文本，而是先由 LLM 把计划解析成结构化事件（类型、标题、细节、优先级）和实体标签，再检索本地历史相关记录、联网搜索补充信息，最后给出 5–8 句「朋友式」建议——既结合你的过往，也附上外部资源链接。

### `/done` 记录完成

把已经做完的事记下来。支持多行输入，以单独一行的 `.` 结束。

**巧思**：记录完成后，系统会用实体标签自动匹配当日待办（概念级 2 倍权重 + 词级 1 倍权重打分），并把「完成 ↔ 待办」的对应关系写回数据。这样日报里就能明确标注「✅ 对应待办已完成」。

### `/chat` 自由对话

`/chat <内容>` 检索历史 + 联网信息后回答，也可以日常闲聊。

**巧思**：内部走「双路检索」——实体标签匹配 + 全文分词搜索，合并去重；同时带上联网搜索结果。多轮对话上下文只保留最近 8 轮，避免历史过长稀释模型对当前问题的注意力。

### `/report` 生成日报

汇总当天全部记录，输出结构化 Markdown 日报。

**巧思**：日报不只是罗列条目，而是把「已完成 / 待办」分组、把已匹配的「完成 ↔ 待办」对应关系注入提示词，并跨日期检索历史关联记录（排除当日），让模型在「关联发现」里发现今日事项与过往的关联（同一个人、同一个项目、相似话题等），同时把已完成对应的待办从「明日计划」中排除。

### `/status` 与自然语言

`/status` 查看今日概况。此外，任何不以 `/` 开头的输入都会走「自然语言自动识别」：由 LLM 判断意图并分发到对应的处理逻辑。

**巧思**：`auto_dispatch` 会把 LLM 解析出的意图、事件、实体一并传给后续处理函数，避免同一句话被 LLM 重复解析两次。

## 架构与设计

### 意图识别

[text_parser.py](src/perception/text_parser.py) 用一次 LLM 调用把任意输入解析为 JSON：`intent`（plan / done / chat / report）、`events`（type / title / detail / priority）、`entities`（实体标签）。解析时 `temperature=0.3`，保证意图判断和结构化输出的稳定。

### 检索系统

[retriever.py](src/retriever.py) 是核心，围绕「精准 + 快速」设计：

- **分词**：jieba 分词，过滤停用词、单字与标点，归一化为小写词表
- **两阶段加权**：概念级匹配（实体标签，2 倍权重）+ 表述级匹配（分词结果，1 倍权重），加权排序取 top-k
- **倒排索引**：`entity → 条目` 与 `token → 条目` 两套索引，检索时直接定位候选，避免全量扫描
- **缓存**：用文件 `mtime` 做进程内失效判断，数据未变则直接命中内存缓存；`_tokens` 会持久化到 JSON，避免重复分词

### 联网搜索

[web_search.py](src/web_search.py) 基于 DuckDuckGo（`ddgs`）。其同步阻塞 API 被放进 `ThreadPoolExecutor`，通过 `run_in_executor` 桥接成异步，保证不阻塞事件循环。

### 多轮对话记忆

[orchestrator.py](src/agent/orchestrator.py) 维护运行期内的 `chat_history`，user/assistant 交替追加，超出上限丢弃最旧，平衡上下文与注意力。

### 存储

[storage.py](src/storage.py) 按日期组织数据：每日记录存 `data/YYYY-MM-DD.json`，日报存 `data/reports/YYYY-MM-DD.md`，`/plan` 建议存 `data/plans/YYYY-MM-DD.md`。

## 数据存储

- `data/YYYY-MM-DD.json`：当日记录（待办 / 已完成，含结构化事件与实体标签）
- `data/reports/YYYY-MM-DD.md`：生成的日报
- `data/plans/YYYY-MM-DD.md`：`/plan` 保存的建议
