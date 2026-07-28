# 背单词：桌面端与 Chrome 划词扩展

一个面向 Windows 的本地背单词工具。它包含 CustomTkinter 桌面端和
Chrome Manifest V3 扩展：在网页中选中英文后，通过右键菜单翻译并加入
本地词库。扩展不保存 API Key，翻译请求只由本机 Native Messaging Host
发起。

## 功能

- 英文单词与短语录入、自动翻译、搜索、导入和导出
- 每轮每个单词只出现一次，完成后显示轮次总结
- “认识了 / 没记住”评分与复习统计
- 无边框置顶迷你模式和全局老板键 `Ctrl+Alt+W`
- Chrome 划词右键翻译，结果在选区附近显示
- 插件新增单词后，已打开的桌面端自动刷新词库
- GUI 与 Native Host 跨进程文件锁和原子写入

## 安全设计

- Chrome 扩展中没有 API Key，也不直接访问模型服务。
- Chrome 仅通过 `com.touchfish.beidanci` Native Messaging Host 与本机通信。
- Native Host 只接受白名单扩展 ID
  `ehgcdcbighbkmeegmkiplbglcabhjiia`。
- 输入限制为 1–64 个英文、数字、空格、连字符或撇号字符。
- Host 不监听本地端口，只向 `.env` 配置的 HTTPS 模型服务发起请求。
- `.env`、词库、统计数据、构建产物和私钥均被 Git 忽略。

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10+
- Google Chrome
- 一个支持 OpenAI Chat Completions 格式的模型服务

## 从源码运行

```powershell
git clone <your-repository-url>
cd learn_english

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env
python main.py
```

`.env` 示例：

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=replace-with-your-api-key
LLM_MODEL=gpt-4o-mini
LLM_DISABLE_THINKING=true
```

不要把真实 API Key 写进源码、扩展目录或提交记录。

## 构建 Windows 可执行文件

安装构建依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

执行：

```powershell
.\build.ps1
```

脚本会生成并复制两个被 Git 忽略的文件：

- `背单词.exe`：桌面 GUI
- `背单词-host.exe`：Chrome Native Messaging Host

## 安装 Chrome 扩展

先完成可执行文件构建，然后运行：

```powershell
.\install-chrome-extension.ps1
```

安装脚本会：

1. 将扩展源码复制到
   `%LOCALAPPDATA%\TouchFish\BeidanciChrome\chrome-extension`。
2. 生成 Native Host manifest。
3. 写入当前用户的 Chrome Native Messaging 注册表项。
4. 将 `.env` 权限收紧为当前用户只读。

随后打开 `chrome://extensions`：

1. 开启“开发者模式”。
2. 点击“加载已解压的扩展程序”。
3. 选择安装脚本输出的 `ExtensionPath`。

在网页中选中英文，右键选择“📥 发送到背单词并翻译”即可。

卸载 Native Host 注册与扩展副本：

```powershell
.\uninstall-chrome-extension.ps1
```

卸载脚本不会删除仓库中的 `.env`、`words.json` 或 `stats.json`。

## 数据文件

下列文件只保存在本机，不会进入 Git：

| 文件 | 用途 |
| --- | --- |
| `.env` | 模型地址、模型名称和 API Key |
| `words.json` | 用户词库 |
| `stats.json` | 复习统计 |
| `*.lock` | GUI 与 Native Host 的跨进程锁 |

建议定期使用桌面端“导出”功能备份词库。

## 测试

```powershell
python -m unittest -v `
  test_native_host.py `
  test_live_sync.py `
  test_review_round.py
```

测试覆盖 Native Messaging 帧协议、输入校验、限流、词库新增/更新、
桌面端实时同步和轮次内不重复抽词。

## 项目结构

```text
.
├── chrome-extension/              # Chrome MV3 扩展源码
├── main.py                        # 桌面 GUI
├── native_host.py                 # 无 GUI 的 Native Messaging Host
├── build.ps1                      # Windows 构建脚本
├── install-chrome-extension.ps1   # 扩展与 Host 注册
├── uninstall-chrome-extension.ps1
├── 背单词.spec
├── 背单词-host.spec
├── requirements.txt
└── test_*.py
```

## 贡献

欢迎提交 Issue 和 Pull Request。提交前请运行全部测试，并确认：

- 未提交 `.env`、API Key、用户词库或统计数据
- 扩展目录不含远程脚本、`eval` 或模型服务凭证
- Native Host 仍不监听任何本地端口

## 许可证

本项目使用 [MIT License](LICENSE)。
