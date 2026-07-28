# 背单词

一款适用于 Windows 的轻量本地背单词工具，并提供 Chrome 划词收词扩展。

阅读网页时选中英文，通过右键菜单即可翻译并加入本地词库；回到桌面端后，
新单词会自动出现，可直接进入分轮复习。模型配置、API Key、词库和学习统计
均保存在本机。

[项目主页](https://gitee.com/michaellitea/learn-english)

## 为什么做这个项目

很多划词翻译工具擅长“查词”，但查询结果很难自然进入后续复习流程。本项目
把网页划词、自动翻译、本地收词和桌面复习串在一起，同时保持数据结构简单、
可导出、无账号依赖。

## 主要功能

- **网页划词收词**：选中英文后，通过 Chrome 右键菜单翻译并保存。
- **就地显示结果**：翻译卡片显示在选区附近，无需切换窗口。
- **分轮复习**：每轮中的单词只出现一次，完成后显示本轮总结。
- **双向评分**：使用“认识了”和“没记住”记录复习结果。
- **迷你模式**：提供无边框置顶小窗，可在工作间隙复习。
- **本地词库**：支持搜索、导入、导出和实时刷新。
- **学习统计**：记录总复习次数、今日复习量和连续学习天数。
- **兼容模型接口**：支持 OpenAI Chat Completions 格式的模型服务。

## 使用流程

1. 在 Chrome 网页中选中一个英文单词或短语。
2. 右键选择“📥 发送到背单词并翻译”。
3. 在选区旁查看中文释义和入库状态。
4. 打开桌面端，在“背单词”页开始复习。
5. 完成全部单词后，可休息或开始下一轮。

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10+
- Google Chrome（使用划词扩展时需要）
- 一个支持 OpenAI Chat Completions 格式的模型服务

推荐使用来自 [python.org](https://www.python.org/downloads/windows/) 的
64 位 CPython。

## 快速开始

### 1. 获取源码

```powershell
git clone https://gitee.com/michaellitea/learn-english.git
cd learn-english
```

### 2. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. 配置模型

复制配置模板：

```powershell
Copy-Item .env.example .env
notepad .env
```

根据所使用的模型服务填写：

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=replace-with-your-api-key
LLM_MODEL=gpt-4o-mini
LLM_DISABLE_THINKING=true
```

`LLM_BASE_URL` 不需要包含 `/chat/completions`。程序会自动补全该路径。

### 4. 启动桌面端

```powershell
python main.py
```

录入或复习后，程序会在项目目录保存本地词库和统计文件。

## 安装 Chrome 划词扩展

Chrome 扩展通过 Native Messaging 与桌面端共享词库，因此需要先构建
Windows 可执行文件。

### 1. 安装构建依赖

```powershell
python -m pip install -r requirements-dev.txt
```

### 2. 构建

```powershell
.\build.ps1
```

构建完成后，项目目录中会生成：

- `背单词.exe`：桌面程序
- `背单词-host.exe`：Chrome Native Messaging Host

这些二进制文件属于本机构建产物，不会被 Git 跟踪。

### 3. 注册 Native Host

请先确认 `.env` 已配置正确，再执行：

```powershell
.\install-chrome-extension.ps1
```

脚本成功后会输出扩展目录 `ExtensionPath`。

### 4. 在 Chrome 中加载扩展

1. 打开 `chrome://extensions`。
2. 开启右上角“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择安装脚本输出的 `ExtensionPath`。

更新扩展源码后，重新运行安装脚本，并在扩展管理页点击一次“重新加载”。

卸载扩展注册：

```powershell
.\uninstall-chrome-extension.ps1
```

卸载操作不会删除词库和统计数据。

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Space` | 显示当前单词的中文释义 |
| `Enter` / `→` | 标记“认识了”并进入下一个单词 |
| `←` | 标记“没记住”并进入下一个单词 |
| `Esc` | 隐藏窗口 |
| `Ctrl+Alt+W` | 在全局范围显示或隐藏窗口 |
| `Ctrl+T` | 在录入页翻译当前英文 |

## 本地数据与隐私

| 文件 | 内容 |
| --- | --- |
| `.env` | 模型地址、模型名称和 API Key |
| `words.json` | 单词、释义和复习状态 |
| `stats.json` | 每日复习统计 |

这些文件均已加入 `.gitignore`。Chrome 扩展不会读取或保存 API Key，也不会
直接请求模型服务；翻译请求由本机 Native Messaging Host 发起。Host 不监听
HTTP 或 WebSocket 端口。

建议定期使用桌面端“导出”功能备份词库。

## 当前限制

- 目前仅支持 Windows。
- Chrome 扩展尚未发布到应用商店，需要通过开发者模式加载。
- 划词入口目前是右键菜单，不会在每次选词后自动弹出操作按钮。
- 翻译范围限制为 1–64 个字符的英文单词或短语。
- 暂不提供云同步、账号系统或移动端。

## 常见问题

### 扩展提示找不到 Native Host

确认已经执行 `.\build.ps1` 和 `.\install-chrome-extension.ps1`，然后在
`chrome://extensions` 中重新加载扩展。

### 桌面端提示未配置 `LLM_API_KEY`

确认 `.env` 与 `main.py` 位于同一目录；使用 exe 时，`.env` 应与
`背单词.exe` 位于同一目录。建议在运行安装脚本前完成配置。

### 插件添加单词后桌面端没有立即出现

请确认运行的是最新构建的桌面端。正常情况下，词库会在约一秒内自动刷新。

### PyInstaller 报告找不到 Tcl/Tk

优先使用 python.org 提供的官方 CPython，并确认安装时包含 Tcl/Tk 和
IDLE 组件。部分精简版或损坏的 Conda 环境可能缺少完整 Tcl/Tk 运行库。

## 开发与测试

运行全部自动测试：

```powershell
python -m unittest -v `
  test_native_host.py `
  test_live_sync.py `
  test_review_round.py
```

项目的主要组件：

```text
.
├── chrome-extension/              # Chrome Manifest V3 扩展
├── main.py                        # CustomTkinter 桌面端
├── native_host.py                 # Native Messaging Host
├── build.ps1                      # Windows 构建脚本
├── install-chrome-extension.ps1   # Host 注册与扩展安装
├── uninstall-chrome-extension.ps1
├── 背单词.spec
├── 背单词-host.spec
└── test_*.py
```

## 参与贡献

欢迎通过 Issue 报告问题或提交 Pull Request。提交代码前请：

1. 运行全部自动测试。
2. 确认没有提交 `.env`、API Key、词库或统计数据。
3. 保持扩展不包含远程脚本或模型服务凭证。
4. 保持 Native Host 不监听本地网络端口。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
