# IdeaSpark ✨

创意生成引擎：多类词库随机组合成「创意配方」，可选 **Google Gemini** 或 **OpenAI** 从市场潜力、技术可行性、创新突破点三个维度打分（1–10），并生成简短商业初稿。优秀配方（三项平均分 **大于 8**）可一键保存到本地 **Markdown** 或 **SQLite**。

## 功能

- **词库管理**：预设「技术 / 行业 / 人群 / 心理需求」四类，可在界面动态添加词汇并持久化到 `data/word_bank.json`。
- **随机配方**：从每类随机抽取一词并组合展示。
- **AI 评价**：集成 Gemini 与 OpenAI，支持侧边栏切换与密钥配置。
- **存档**：评价后可写入 `ideas_saved/*.md` 或 `data/ideas.db`。

## 环境要求

- Python 3.10+
- Gemini 或 OpenAI 的有效 API Key

## 安装与运行

```bash
cd IdeaSpark
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # 编辑 .env 填入密钥（Windows 用 copy，Linux/mac 用 cp）
streamlit run app.py
```

也可将密钥写入 `.streamlit/secrets.toml`（勿提交仓库），键名：`GOOGLE_API_KEY`、`OPENAI_API_KEY`、`AI_PROVIDER`。

## 项目结构

```
IdeaSpark/
  app.py                 # Streamlit 入口
  ideaspark/
    config.py            # 路径与环境
    word_bank.py         # 词库与 JSON 持久化
    combinator.py        # 随机组合
    ai_evaluator.py      # Gemini / OpenAI 与 JSON 解析
    storage.py           # SQLite 与 Markdown 存档
  data/                  # 运行时数据库与用户词库（默认忽略部分文件）
  ideas_saved/           # 导出的 Markdown
  requirements.txt
```

## 许可证

MIT
