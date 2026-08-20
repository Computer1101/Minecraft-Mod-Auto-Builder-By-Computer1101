# 📘 Minecraft Mod Auto-Builder v3.0

> 一个基于 Python 和 Tkinter 的图形化工具，专为 Minecraft Mod 开发者设计。  
> 自动化 Gradle 构建流程，支持自定义 Maven 镜像与 Gradle 分发镜像，大幅提升国内网络环境下的构建速度。

---

## 📑 目录

- [功能特性](#-功能特性)
- [安装要求](#-安装要求)
- [快速开始](#-快速开始)
- [使用说明](#-使用说明)
  - [基本构建流程](#基本构建流程)
  - [高级功能](#高级功能)
- [镜像说明](#-镜像说明)
  - [Maven 镜像](#maven-镜像)
  - [Gradle 分发镜像](#gradle-分发镜像)
- [配置示例](#-配置示例)
  - [gradle.properties 代理配置](#gradleproperties-代理配置)
  - [保存/加载配置](#保存加载配置)
- [常见问题](#-常见问题)
- [界面截图](#-界面截图)
- [更新日志](#-更新日志)
- [许可证](#-许可证)

---

## ✨ 功能特性

- 🖥️ **图形化界面**：基于 Tkinter，标签页布局清晰，实时滚动显示构建输出。
- 🚀 **Maven 镜像注入**：通过生成临时 `init.gradle` 脚本，自动将 Maven 仓库替换为国内镜像（阿里云、腾讯云、华为云等），并保留中央仓库作为后备。
- 📦 **Gradle 分发镜像管理**：自动读取并修改 `gradle-wrapper.properties` 中的 `distributionUrl`，一键切换 Gradle 下载源，解决国内下载 Gradle 慢的问题。
- ☕ **JDK 环境配置**：支持手动指定 JDK 目录或自动检测系统 JDK，构建时独立注入 `JAVA_HOME` 和 `PATH`，不影响全局设置。
- 🧩 **一键克隆 GitHub 仓库**：输入仓库地址即可自动 `git clone`，并将克隆后的目录设置为当前项目目录。
- 📝 **gradle.properties 编辑器**：内置文本编辑器，可直接加载、修改并保存项目的 `gradle.properties`，方便配置 JVM 参数、代理等。
- 📚 **构建历史记录**：自动记录每次构建的时间、任务和结果，支持查看历史，便于追踪。
- 🧹 **一键清理缓存**：可删除用户级 `~/.gradle/caches` 和项目级 `.gradle` 缓存，解决依赖混乱问题。
- 📋 **生成 GitHub Actions 工作流**：根据当前镜像和任务配置生成完整的 `.yml` 内容，并可一键复制到剪贴板。
- 💾 **配置保存与加载**：可将所有设置（包括镜像、JDK、项目目录等）导出为 JSON 文件，便于复用和团队共享。
- 🌓 **可选主题**：安装 `sv-ttk` 后界面更现代，并支持亮色/暗色主题切换。

---

## 📦 安装要求

| 依赖 | 说明 |
|------|------|
| Python | 3.6+，推荐 3.9 或更高版本 |
| Git | 可选，用于从 GitHub 克隆项目 |
| Java JDK | 版本需与目标 Minecraft 版本匹配（如 JDK 17 / 21） |
| Gradle Wrapper | 项目目录需包含 `gradlew` 或 `gradlew.bat` |

> **提示**：若未安装 Git，仍可手动选择本地项目目录，不影响其他功能。

---

## 🚀 快速开始

1. **下载脚本**  
   将 `mc_mod_builder_v3.py` 保存到本地任意位置。

2. **（可选）安装美化主题**  
   ```bash
   pip install sv-ttk
   ```
   不安装也能正常运行，仅界面风格较朴素。

3. **运行工具**  
   ```bash
   python mc_mod_builder_v3.py
   ```
   弹出图形窗口后即可开始使用。

---

## 🧭 使用说明

### 基本构建流程

1. **选择项目目录**  
   在「构建与镜像」标签页点击「浏览...」选择 Mod 项目根目录（包含 `gradlew` 的文件夹），或点击「从 GitHub 克隆」输入仓库地址自动下载。

2. **设置 Gradle 任务**  
   默认 `build`，可输入多个任务（用空格分隔），如：`clean build`。

3. **选择 JDK**  
   点击「自动检测」让工具自动寻找 JDK，或点击「浏览...」手动指定 JDK 根目录（如 `C:\Program Files\Java\jdk-17`）。

4. **配置 Maven 镜像**  
   在「Maven 仓库镜像」区域选择预设按钮（阿里云、腾讯云等）或手动编辑镜像列表（每行一个 URL）。

5. **配置 Gradle 分发镜像**  
   点击「刷新」查看当前 `distributionUrl`，在「镜像选择」下拉框选择国内镜像（如腾讯云），点击「应用镜像」即可替换下载源。

6. **开始构建**  
   点击「▶ 开始构建」，在「输出与历史」标签页查看实时日志。进度条滚动表示正在执行，若 30 秒无输出会显示「⏳ 仍在处理中」提示。

7. **构建完成**  
   若配置了「产物输出目录」，JAR 文件会自动复制到指定位置。成功或失败均会弹出提示框。

### 高级功能

- **克隆 GitHub 仓库**  
  点击「从 GitHub 克隆」，输入仓库地址（如 `https://github.com/user/repo.git`），选择存放目录，工具自动完成克隆并设置项目目录。

- **编辑 gradle.properties**  
  切换到「高级工具」标签页，点击「加载 properties」读取项目中的 `gradle.properties`，修改后点击「保存 properties」。点击「添加典型 JVM 参数」可快速插入内存设置。

- **保存/加载配置**  
  点击「保存配置」将当前所有设置（项目目录、镜像、JDK 等）导出为 JSON。点击「加载配置」可恢复之前状态，便于切换项目或分享给他人。

- **生成 GitHub Actions 工作流**  
  点击「生成 Actions」，工具根据当前 Maven 镜像和任务生成完整 YAML 内容，并弹出窗口供复制。可直接粘贴到 `.github/workflows/build.yml` 使用。

- **清理 Gradle 缓存**  
  点击「🧹 清理 Gradle 缓存」可删除用户级 `~/.gradle/caches` 和项目级 `.gradle` 目录。建议在依赖混乱或构建失败时使用，注意清理后需要重新下载依赖。

---

## 📡 镜像说明

### Maven 镜像

Maven 镜像用于加速依赖包下载。工具通过临时 `init.gradle` 脚本向所有项目注入镜像仓库，原仓库保留作为后备。

**预设镜像列表：**

| 镜像名称 | 地址 |
|----------|------|
| 阿里云 | `https://maven.aliyun.com/repository/public`、`https://maven.aliyun.com/repository/google`、`https://maven.aliyun.com/repository/gradle-plugin` |
| 腾讯云 | `https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`、`https://mirrors.cloud.tencent.com/gradle/`、`https://mirrors.cloud.tencent.com/google/` |
| 华为云 | `https://repo.huaweicloud.com/repository/maven/`、`https://repo.huaweicloud.com/repository/google/`、`https://repo.huaweicloud.com/repository/gradle-plugins/` |
| Maven Central | `https://repo1.maven.org/maven2/` |

> 如需添加其他镜像，直接在文本框内增加一行 URL 即可。

### Gradle 分发镜像

Gradle 分发镜像用于加速 Gradle 自身（`distributionUrl`）的下载。工具会修改 `gradle-wrapper.properties` 中的 `distributionUrl` 基础路径。

**支持的基础镜像：**

| 镜像名称 | 基础 URL |
|----------|----------|
| 官方（默认） | `https://services.gradle.org/distributions` |
| 阿里云 | `https://mirrors.aliyun.com/gradle` |
| 腾讯云 | `https://mirrors.cloud.tencent.com/gradle` |
| 华为云 | `https://mirrors.huaweicloud.com/gradle` |

**注意**：部分镜像可能未缓存特定版本的 Gradle，若应用后下载失败（404），请尝试切换其他镜像，或点击「恢复默认」使用官方源。

---

## 🔧 配置示例

### gradle.properties 代理配置

当构建需要访问海外专用仓库（如 NeoForged、Fabric）时，推荐在 `gradle.properties` 中配置代理。在「高级工具」标签页加载并编辑，添加以下内容（根据实际代理端口修改）：

```properties
systemProp.http.proxyHost=127.0.0.1
systemProp.http.proxyPort=7890
systemProp.https.proxyHost=127.0.0.1
systemProp.https.proxyPort=7890
```

若代理使用 SOCKS5，可改为：

```properties
systemProp.socksProxyHost=127.0.0.1
systemProp.socksProxyPort=1080
```

### 保存/加载配置

配置文件为 JSON 格式，包含以下字段：

```json
{
  "project_dir": "E:/monstergirl-1.19.2-master",
  "task": "build",
  "output_dir": "D:/ModJars",
  "no_daemon": true,
  "console_plain": true,
  "mirrors": [
    "https://maven.aliyun.com/repository/public",
    "https://maven.aliyun.com/repository/google",
    "https://maven.aliyun.com/repository/gradle-plugin"
  ],
  "jdk_path": "C:/Program Files/Microsoft/jdk-21.0.10.7-hotspot",
  "gradle_mirror": "腾讯云"
}
```

---

## ❓ 常见问题

### Q: 构建时提示“找不到 gradlew”
A: 请确认选择的目录是 Gradle 项目的根目录，且包含 `gradlew` 或 `gradlew.bat`。如果项目没有 wrapper，请先在命令行运行 `gradle wrapper` 生成。

### Q: 应用 Gradle 镜像后下载失败（404）
A: 部分国内镜像未缓存特定 Gradle 版本，尝试更换镜像（如腾讯云、华为云），或点击「恢复默认」使用官方源。

### Q: 构建时出现 `Connection reset` 或无法解析 `maven.neoforged.net`
A: 这是因为项目依赖了 NeoForged/Fabric 等海外专用 Maven 仓库，国内直连不稳定。推荐在 `gradle.properties` 中配置代理，或使用 VPN 后重新构建。

### Q: 如何配置代理？
A: 参见 [配置示例 - gradle.properties 代理配置](#gradleproperties-代理配置)，根据实际代理端口修改后保存。

### Q: 构建历史保存在哪里？
A: 工具会在运行目录生成 `build_history.json` 文件，记录最近 100 条构建记录。该文件可随时删除，不影响功能。

### Q: 工具能在 Linux/macOS 上使用吗？
A: 可以。代码使用了跨平台库和路径处理，在 Linux/macOS 上同样可用（需确保安装了 Python 和 Tkinter）。

### Q: 如何查看当前 Gradle 版本？
A: 在「Gradle 分发镜像」区域点击「刷新」，当前 `distributionUrl` 会显示在输入框中。

---

## 🖼️ 界面截图

> 由于是纯文本 README，无法直接嵌入图片。你可以将截图保存到仓库的 `screenshots/` 目录，并在下方以 Markdown 格式插入。

例如：

```markdown
![主界面](screenshots/main.png)
![镜像设置](screenshots/mirror.png)
![构建输出](screenshots/build.png)
```

---

## 📅 更新日志

### v3.0 (最新)

- 新增 Gradle 分发镜像管理，支持自动修改 `distributionUrl`
- 新增 JDK 环境配置，支持自动检测和手动指定
- 新增 GitHub 项目克隆功能
- 新增 `gradle.properties` 编辑器
- 新增构建完成弹窗提醒
- 配置保存/加载扩展至 JDK、Gradle 镜像等字段
- 优化界面布局，采用标签页分类
- 增强错误处理和心跳提示

### v2.0

- 新增实时构建输出，强制 `--console=plain`
- 新增 Maven 镜像预设
- 新增配置保存/加载
- 新增构建历史记录
- 新增生成 GitHub Actions 工作流
- 新增多任务构建支持
- 新增一键清理缓存

### v1.0

- 基础图形界面
- 支持选择项目、任务、输出目录
- 通过临时 `init.gradle` 注入镜像
- 自动复制 JAR 产物

---

## 📜 许可证

本项目采用 **MIT License**，可自由使用、修改和分发。  
详见仓库中的 `LICENSE` 文件（如已包含）。
