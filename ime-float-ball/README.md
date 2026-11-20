# 输入法桌面悬浮球（macOS / Windows）

一个常驻桌面的**圆形悬浮图标**，用来快速切换输入法。纯 Python + PyQt6 实现，输入法切换走系统原生接口（macOS: Carbon/TIS，Windows: Win32 键盘布局），**两边都不用任何第三方依赖**。

一份源码两个平台通用，后端按平台自动加载：

| 平台 | 后端文件 | 调用什么 |
| --- | --- | --- |
| macOS | `ime_mac.py` | Carbon / TIS（`TISCreateInputSourceList`、`TISSelectInputSource`） |
| Windows | `ime_win.py` | Win32 键盘布局（`GetKeyboardLayoutList` + `WM_INPUTLANGCHANGEREQUEST`） |

两个后端对外接口完全一致（`list_sources()` / `current_id()` / `select_id()`），所以 `ime_float.py` 里的界面、便签、设置逻辑一份代码两边跑。Windows 绿色版见文末“Windows”章节。

## 功能（对照需求）

- ✅ **圆形悬浮图标**：无边框、置顶、可拖到桌面任意位置
- ✅ **透明度 100 级可调**：右键「设置」中的滑块 1–100 级；鼠标滚轮也可 ±1 实时调节
- ✅ **自定义图标背景**：可选任意图片（自动裁剪为圆形），或用纯色背景
- ✅ **左键点击切换输入法**：在「设置」里勾选的输入法之间循环切换
- ✅ **右键设置**：弹出菜单（切换 / 图标大小 / 设置 / 便签 / 狗蛋书签 / 我的快捷 / 隐藏 / 退出）
- ✅ **狗蛋书签一键打开**：右键菜单（含托盘菜单）里的「狗蛋书签」会启动本地书签程序（`~/Desktop/狗蛋书签.app`，程序自身会按需拉起本地服务并打开浏览器）；程序路径 / 网页地址可在「设置」里改，未配置 .app 时直接用网址兜底
- ✅ **右键菜单自定义「我的快捷」**：在「设置」里可自行添加任意数量的菜单项，名字自己取、两类目标自己选：
  - **打开链接/程序**：网址会被浏览器打开；`.app` / 文件路径会被系统直接打开（macOS: `open -a` / `open`）
  - **模拟快捷键**：填组合键（如 `Cmd+Shift+4`、`Win+Shift+S`、`Ctrl+Shift+S`），点击即向系统真实发送该按键——例如把系统截图快捷键映射成菜单项，点一下就截图，不用再记组合键。定义快捷键像其他软件那样顺手：点一下「组合键」输入框，直接在键盘上按出组合键即可自动捕获（无需手敲、无需额外按钮），也仍可手填
  - 默认已带一个「截图」项（macOS `Cmd+Shift+4` / Windows `Win+Shift+S`），开箱即用。添加后出现在右键菜单和托盘菜单的「我的快捷」子菜单里
  - ⚠️ macOS 上「模拟快捷键」需授予本程序「辅助功能」权限（系统设置 → 隐私与安全性 → 辅助功能，勾选输入法悬浮球），否则系统会静默丢弃合成按键
- ✅ **图标大小可调**：40–160px 无级滑块（设置里），或右键「图标大小」快速选 小/标准/大/特大；**整颗球连同文字、高光、描边一起等比缩放**，缩放以圆心为中心并自动夹进屏幕
- ✅ **点图标下边缘打开便签**：圆的下 1/4 区域是便签热区（悬停时该区域会亮一条白弧）
- ✅ **便签**：7 种底色可选、自动保存、自动保留最近 3 个历史版本，透明度跟随悬浮球

额外：托盘图标（隐藏后从托盘恢复）、800ms 轮询同步（用快捷键切换后图标也会更新）、登录启动、记忆位置/透明度/大小/背景/启用项。

## 环境要求

- macOS 或 Windows 10/11
- Python 3.8+
- PyQt6

## 安装与运行（macOS）

方式一：命令行

```bash
pip install PyQt6          # 若尚未安装
python3 ime_float.py
```

方式二：双击运行

直接双击 `启动输入法悬浮球.command`，首次会自动安装 PyQt6（需联网）。

方式三：双击 `.app`（推荐日常使用）

`dist/输入法悬浮球.app`（或桌面上的副本）——已用 PyInstaller 把 Python 与 PyQt6 一起打进 bundle，**不依赖本机 Python 环境**，双击即可运行。自带图标，且 `LSUIElement=true`，作为后台代理运行、不占程序坞。

## 打包成 .app

```bash
python3 -m pip install pyinstaller
# 仓库里已有 InputMethodFloatBall.spec，直接用它最省事：
python3 -m PyInstaller --noconfirm InputMethodFloatBall.spec

# 或者等价的一次性命令：
python3 -m PyInstaller --noconfirm --windowed \
  --name InputMethodFloatBall --icon app.icns \
  --osx-bundle-identifier com.imefloat.app ime_float.py
# 之后在 Info.plist 里设置 LSUIElement=true（隐藏程序坞图标），
# 把 .app 改名并把 CFBundleDisplayName 设为「输入法悬浮球」，最后 ad-hoc 重签：
codesign --force --deep --sign - "输入法悬浮球.app"
```

注意：`.app` 与脚本方式共用同一份配置目录 `~/Library/Application Support/输入法悬浮球/`，两者数据互通；单实例保护会让后启动者接管（不会出现多个图标）。

## 使用方法

| 操作 | 效果 |
| --- | --- |
| 左键单击图标（中上部） | 切换到下一个启用的输入法 |
| 左键单击图标**下边缘** | 打开便签窗口 |
| 右键图标 | 打开菜单：切换 / 图标大小 / 设置 / 便签 / 隐藏 / 退出 |
| 右键 → 图标大小 | 快速选 小 56 / 标准 84 / 大 108 / 特大 132（立即生效并记住）；「更多…」进设置用滑块微调 |
| 鼠标滚轮 | 实时 ±1 级调节整体透明度 |
| 拖拽图标 | 移动位置（松手自动记忆，且会被限制在屏幕可见范围内） |
| 托盘图标 | 单击/右键弹出菜单（显示悬浮球 / 设置 / 便签 / 退出） |

### 便签

- 关闭按钮已加大（46×34），不容易点空
- 底部有 7 个色板可换底色，选「更多…」可用系统取色器
- 透明度不再单独设置，**跟随悬浮球**（滚轮调球体透明度时便签一起变）
- 内容实时写盘（`note.txt`），每次保存前把上一版滚入 `note_history.json`，最多保留 3 个历史版本，便签右下角可一键回滚

### 设置项（右键 → 设置）

- **整体透明度（100 级）**：滑块 1–100，即时预览
- **图标大小（直径 40–160px）**：滑块无级调节 + 4 个快捷档位按钮；所有装饰（文字、高光弧、底部阴影、描边、圆角内缩）都以 84px 为基准等比缩放，小到 40px 也不会出现线条消失或文字溢出
- **图标背景**：选择图片（圆形裁剪）/ 清除图片（改回纯色）/ 背景颜色
- **循环切换的输入法**：勾选要参与左键循环的输入法，顺序即循环顺序（默认排除表情符号/听写/长按等辅助项）
- **登录时自动启动**：勾选后写入 LaunchAgent

> 设置里对透明度和大小都是**实时预览**：点「确定」才写盘，点「取消」会还原到打开对话框时的状态。

## 配置文件

`~/Library/Application Support/输入法悬浮球/config.json`

记录：透明度、图标直径（`icon_size`）、背景图片路径、背景色、位置、启用的输入法 ID、是否登录启动、便签位置与纸色。

`icon_size` 缺失或非法时会自动回落到 84 并被夹到 40–160 之间（`clamp_icon_size()`），所以手改配置文件也不会把窗口撑坏。

## 权限说明

输入法切换一般可直接生效。若点击切换没有反应，请到
**系统设置 → 隐私与安全性 → 辅助功能 / 输入监控** 中，把运行本程序的终端或 Python 加入允许列表。

## 已知事项（含踩坑记录，改代码前务必先看）

- 表情符号面板、听写、长按等非打字输入源默认不参与循环，但可在设置中手动勾选。
- 同名输入法（如微信输入法的两个条目）在图标上均显示首字，属正常。
- **不要用 `tray.setContextMenu()`（macOS）**：Qt 6.11 的 `QCocoaSystemTrayIcon` 在设置菜单时会注册
  `NSMenuDidBeginTrackingNotification` 观察者（`qcocoasystemtrayicon.mm: statusItemMenuBeganTracking:`），
  其中直接读 `-[NSEvent clickCount]`；macOS 14+ 菜单栏图标的菜单已改为**跨进程跟踪**，此刻
  `NSApp.currentEvent` 不是鼠标事件 → NSAssertion 断言 → `abort()`（SIGABRT）。
  **点一次菜单栏图标就崩一次**，Qt 6.12 才修复。现在的做法：不设上下文菜单，点击时自己
  `QMenu.popup()`，并延迟 150ms 等 mouseUp（状态栏按钮的动作是在 mouseDown 时发出的）。
- **不要开 `setMouseTracking(True)`**：macOS 上 cocoa 插件处理追踪事件会走同一类断言路径；
  下边缘悬停提示改用 200ms `QTimer` 轮询 `QCursor.pos()`。
- **窗口位置必须做屏幕内钳制**：一旦被拖到（或从配置恢复到）屏幕外，下次启动就"看不见球"，
  表现和"程序打不开"完全一样。`_clamp_pos()` 负责纠正并写回配置。
- **PyInstaller 重打包**：在已有 `dist/` 上重跑（或加 `--clean`）会触发批量删除保护而被中断；
  先把旧产物 `mv` 到别处再打包。
- 便签作为悬浮球的子窗口时 `setWindowOpacity` 会被父窗口压制而失效，所以 `NoteWindow` 必须
  `parent=None`。

---

# Windows 绿色版

## 一句话

同一份源码，在 Windows 上跑 `build_win.bat` 就能得到一个**免安装绿色版**：程序目录 + `data\` 配置，不写注册表、不装服务，整个文件夹拷到任何 Windows 电脑都能双击直接用。

## 为什么不能在这里直接给你 .exe

Python 与 PyInstaller **都不能交叉编译**：macOS 上打不出 Windows 的 exe（要 Wine + Windows 版 Python + Windows 版 PyQt6，极不可靠）。所以交付的是「源码 + 一键打包脚本」，在任意一台装了 Python 的 Windows 上双击 `build_win.bat`，1~3 分钟就得到 `绿色版\输入法悬浮球.exe`。

## 在 Windows 上怎么做

1. 装 Python 3.9+（安装时勾选 **Add python.exe to PATH**）
2. 把整个项目文件夹拷到 Windows
3. 双击 **`build_win.bat`** —— 自动装 PyQt6/PyInstaller 并打包
4. 产物在 **`绿色版\输入法悬浮球.exe`**，双击即用

不想打包？装好 `pip install PyQt6` 后直接双击 **`启动-无控制台.vbs`**（不会弹黑框）。

## Windows 侧和 macOS 的差异（有意为之）

| 项目 | macOS | Windows |
| --- | --- | --- |
| 输入法枚举/切换 | Carbon/TIS，能拿到父级/模式两条 | Win32 键盘布局（HKL），与 **Win+Space 的列表完全一致** |
| 配置存放 | `~/Library/Application Support/输入法悬浮球` | **程序目录下 `data\config.json`**（不可写时退到 `%APPDATA%\输入法悬浮球`） |
| 开机自启 | LaunchAgent plist | 「启动」文件夹里的 `.lnk`（不写注册表） |
| 托盘菜单 | 不设 `setContextMenu`，自己 popup（规避 Qt 崩溃） | 用原生 `setContextMenu` |
| 悬浮窗标志 | `FramelessHint \| StaysOnTop` | 再加 `Tool`（不在任务栏占位） |
| 环境变量覆盖配置目录 | `IMEFLOAT_DATA` | `IMEFLOAT_DATA` |

## Windows 已知限制

- 切换走 `WM_INPUTLANGCHANGEREQUEST`，**对以管理员权限运行的窗口无效**（Windows UIPI 会拦截普通权限进程的消息）——需要时以管理员身份运行本程序。
- 全屏独占的游戏一般会拦截该消息，属正常。
- `--onefile` 单文件版每次启动要解压到临时目录，首次约 1~2 秒；想更快可把 `build_win.bat` 里的 `--onefile` 换成 `--onedir`。
- PyInstaller 打的 exe 常被杀软启发式误报，加白名单即可（源码全在目录里可查）。

## 文件清单

| 文件 | 作用 |
| --- | --- |
| `ime_float.py` | 主程序（界面/便签/设置，两平台共用） |
| `ime_mac.py` | macOS 输入法后端 |
| `ime_win.py` | Windows 输入法后端 |
| `app.ico` | Windows 图标（16/24/32/48/64/128/256 七个尺寸） |
| `build_win.bat` | 一键打包（GBK 编码，中文窗口不乱码） |
| `启动-无控制台.vbs` | 源码方式启动，不弹命令行 |
| `说明-Windows绿色版.txt` | 给最终用户看的使用说明（UTF-8 BOM） |
