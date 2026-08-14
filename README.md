# Daily Report

AI 驱动的个人日报记录与生成工具。用自然语言随手记录待办和已完成事项，它会自动识别意图、关联历史记录并联网检索，最后为你生成一份结构化的当日日报。

## 特性

- **自然语言输入**：无需记忆命令，直接输入「今天写完了周报」等描述，AI 会自动识别意图
- **待办与完成**：`/plan` 记录待办、`/done` 记录完成，自动把完成项关联到当日待办
- **智能对话**：`/chat` 结合本地历史与联网信息回答问题
- **日报生成**：`/report` 汇总当日记录，输出结构化的 Markdown 日报
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

3. 运行

   ```bash
   python main.py
   ```

   也可以安装后通过命令启动：

   ```bash
   pip install -e .
   dailyreport
   ```

## 命令说明

| 命令 | 说明 |
| --- | --- |
| `/plan` | 记录待办事项（多行输入，以单独的 `.` 结束） |
| `/done` | 记录已完成事项 |
| `/chat <内容>` | 自由对话，检索历史 + 联网信息 |
| `/report` | 生成本日完整日报 |
| `/status` | 查看今日概况 |
| `/help` | 显示帮助 |
| `/exit` | 退出 |

除命令外，也可以直接输入自然语言，AI 会自动识别意图并分发处理。

## 数据存储

- `data/YYYY-MM-DD.json`：当日记录（待办 / 已完成）
- `data/reports/YYYY-MM-DD.md`：生成的日报
- `data/plans/YYYY-MM-DD.md`：`/plan` 保存的建议
