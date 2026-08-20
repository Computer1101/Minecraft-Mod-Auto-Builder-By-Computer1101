#!/usr/bin/env python3
"""
Minecraft Mod Auto-Builder v3.0 (GUI)
Features:
  - Maven mirror injection (Aliyun, Tencent, Huawei, Central)
  - Gradle distribution mirror (modify gradle-wrapper.properties)
  - JDK path customization
  - GitHub project clone
  - gradle.properties editor
  - Real-time build output with heartbeat
  - Configuration save/load
  - Build history & GitHub Actions generator
  - One-click cache clean
"""

import os
import sys
import subprocess
import threading
import queue
import tempfile
import platform
import shutil
import time
import json
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# ---------- 默认阿里云 Maven 镜像 ----------
DEFAULT_ALIYUN_MIRRORS = [
    "https://maven.aliyun.com/repository/public",
    "https://maven.aliyun.com/repository/google",
    "https://maven.aliyun.com/repository/gradle-plugin"
]

MIRROR_PRESETS = {
    "阿里云": DEFAULT_ALIYUN_MIRRORS,
    "腾讯云": [
        "https://mirrors.cloud.tencent.com/nexus/repository/maven-public/",
        "https://mirrors.cloud.tencent.com/gradle/",
        "https://mirrors.cloud.tencent.com/google/"
    ],
    "华为云": [
        "https://repo.huaweicloud.com/repository/maven/",
        "https://repo.huaweicloud.com/repository/google/",
        "https://repo.huaweicloud.com/repository/gradle-plugins/"
    ],
    "Maven Central": [
        "https://repo1.maven.org/maven2/"
    ]
}

# Gradle 分发镜像预设（用于替换 distributionUrl 中的域名）
GRADLE_DIST_MIRRORS = {
    "默认（官方）": "https://services.gradle.org/distributions",
    "阿里云": "https://mirrors.aliyun.com/gradle",
    "腾讯云": "https://mirrors.cloud.tencent.com/gradle",
    "华为云": "https://mirrors.huaweicloud.com/gradle",
    "自定义": ""
}

CONFIG_FILE = "mc_builder_config.json"
HISTORY_FILE = "build_history.json"

try:
    import sv_ttk
    HAS_SV_TTK = True
except ImportError:
    HAS_SV_TTK = False


def generate_init_gradle(mirrors):
    repos_block = "\n".join(f"        maven {{ url '{url}' }}" for url in mirrors)
    return f"""\
allprojects {{
    buildscript {{
        repositories {{
{repos_block}
            mavenCentral()
            google()
        }}
    }}
    repositories {{
{repos_block}
        mavenCentral()
        google()
    }}
}}
"""


class ModBuilderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Mod Auto-Builder v3.0")
        self.root.geometry("960x780")
        self.root.minsize(800, 650)

        self.process = None
        self.build_thread = None
        self.stop_event = threading.Event()
        self.queue = queue.Queue()
        self.last_output_time = time.time()
        self.current_history = []

        self.setup_styles()
        self.create_widgets()
        self.poll_queue()
        self.load_history()

    def setup_styles(self):
        style = ttk.Style()
        if HAS_SV_TTK:
            sv_ttk.set_theme("light")
        else:
            style.theme_use("clam")
            style.configure("TLabel", font=("微软雅黑", 10))
            style.configure("TButton", font=("微软雅黑", 10))
            style.configure("TEntry", font=("微软雅黑", 10))

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 创建主 Notebook
        main_notebook = ttk.Notebook(main_frame)
        main_notebook.pack(fill=tk.BOTH, expand=True)

        # ----- Tab1: 项目设置与构建 -----
        build_tab = ttk.Frame(main_notebook, padding=10)
        main_notebook.add(build_tab, text="构建与镜像")

        # 项目设置区
        settings_frame = ttk.LabelFrame(build_tab, text="项目设置", padding=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # 项目目录 + 克隆按钮
        dir_frame = ttk.Frame(settings_frame)
        dir_frame.pack(fill=tk.X, pady=3)
        ttk.Label(dir_frame, text="项目目录：", width=12).pack(side=tk.LEFT)
        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(dir_frame, text="浏览...", command=self.browse_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(dir_frame, text="从 GitHub 克隆", command=self.clone_repo).pack(side=tk.LEFT, padx=2)

        # Gradle 任务
        task_frame = ttk.Frame(settings_frame)
        task_frame.pack(fill=tk.X, pady=3)
        ttk.Label(task_frame, text="Gradle 任务：", width=12).pack(side=tk.LEFT)
        self.task_var = tk.StringVar(value="build")
        task_entry = ttk.Entry(task_frame, textvariable=self.task_var)
        task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(task_frame, text="(空格分隔多任务)", foreground="gray").pack(side=tk.LEFT)

        # 产物输出目录
        out_frame = ttk.Frame(settings_frame)
        out_frame.pack(fill=tk.X, pady=3)
        ttk.Label(out_frame, text="产物输出：", width=12).pack(side=tk.LEFT)
        self.out_var = tk.StringVar()
        out_entry = ttk.Entry(out_frame, textvariable=self.out_var)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(out_frame, text="浏览...", command=self.browse_out).pack(side=tk.LEFT)

        # JDK 目录
        jdk_frame = ttk.Frame(settings_frame)
        jdk_frame.pack(fill=tk.X, pady=3)
        ttk.Label(jdk_frame, text="JDK 目录：", width=12).pack(side=tk.LEFT)
        self.jdk_var = tk.StringVar()
        jdk_entry = ttk.Entry(jdk_frame, textvariable=self.jdk_var)
        jdk_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(jdk_frame, text="自动检测", command=self.auto_detect_jdk).pack(side=tk.LEFT, padx=2)
        ttk.Button(jdk_frame, text="浏览...", command=self.browse_jdk).pack(side=tk.LEFT)

        # 构建选项
        options_frame = ttk.Frame(settings_frame)
        options_frame.pack(fill=tk.X, pady=5)
        ttk.Label(options_frame, text="构建选项：", width=12).pack(side=tk.LEFT)
        self.no_daemon_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="--no-daemon", variable=self.no_daemon_var).pack(side=tk.LEFT, padx=5)
        self.console_plain_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="--console=plain", variable=self.console_plain_var).pack(side=tk.LEFT, padx=5)

        # Maven 镜像区
        mirror_frame = ttk.LabelFrame(build_tab, text="Maven 仓库镜像", padding=10)
        mirror_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        preset_frame = ttk.Frame(mirror_frame)
        preset_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(preset_frame, text="预设：", width=12).pack(side=tk.LEFT)
        for name, urls in MIRROR_PRESETS.items():
            btn = ttk.Button(preset_frame, text=name, command=lambda u=urls: self.set_mirror_preset(u))
            btn.pack(side=tk.LEFT, padx=2)

        self.mirror_text = scrolledtext.ScrolledText(mirror_frame, height=4, font=("Consolas", 10), wrap=tk.WORD)
        self.mirror_text.pack(fill=tk.BOTH, expand=True)
        self.mirror_text.insert("1.0", "\n".join(DEFAULT_ALIYUN_MIRRORS))

        # Gradle 分发镜像区
        gradle_mirror_frame = ttk.LabelFrame(build_tab, text="Gradle 分发镜像（修改 gradle-wrapper.properties）", padding=10)
        gradle_mirror_frame.pack(fill=tk.X, pady=(0, 10))

        gradle_mirror_row = ttk.Frame(gradle_mirror_frame)
        gradle_mirror_row.pack(fill=tk.X, pady=2)
        ttk.Label(gradle_mirror_row, text="当前 URL：", width=12).pack(side=tk.LEFT)
        self.gradle_url_var = tk.StringVar(value="未检测")
        ttk.Entry(gradle_mirror_row, textvariable=self.gradle_url_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(gradle_mirror_row, text="刷新", command=self.refresh_gradle_url).pack(side=tk.LEFT, padx=2)

        gradle_preset_row = ttk.Frame(gradle_mirror_frame)
        gradle_preset_row.pack(fill=tk.X, pady=5)
        ttk.Label(gradle_preset_row, text="镜像选择：", width=12).pack(side=tk.LEFT)
        self.gradle_mirror_combo = ttk.Combobox(gradle_preset_row, values=list(GRADLE_DIST_MIRRORS.keys()), state="readonly")
        self.gradle_mirror_combo.set("默认（官方）")
        self.gradle_mirror_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(gradle_preset_row, text="应用镜像", command=self.apply_gradle_mirror).pack(side=tk.LEFT, padx=5)
        ttk.Button(gradle_preset_row, text="恢复默认", command=self.reset_gradle_mirror).pack(side=tk.LEFT, padx=5)

        # 控制按钮
        btn_frame = ttk.Frame(build_tab)
        btn_frame.pack(fill=tk.X, pady=(5, 5))
        self.build_btn = ttk.Button(btn_frame, text="▶ 开始构建", command=self.start_build)
        self.build_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止构建", command=self.stop_build, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # 进度条
        self.progress = ttk.Progressbar(build_tab, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 5))

        # ----- Tab2: 高级工具 -----
        tools_tab = ttk.Frame(main_notebook, padding=10)
        main_notebook.add(tools_tab, text="高级工具")

        # gradle.properties 编辑器
        prop_frame = ttk.LabelFrame(tools_tab, text="gradle.properties 编辑器", padding=10)
        prop_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        prop_btn_row = ttk.Frame(prop_frame)
        prop_btn_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(prop_btn_row, text="加载 properties", command=self.load_gradle_properties).pack(side=tk.LEFT, padx=5)
        ttk.Button(prop_btn_row, text="保存 properties", command=self.save_gradle_properties).pack(side=tk.LEFT, padx=5)
        ttk.Button(prop_btn_row, text="添加典型 JVM 参数", command=self.add_jvm_args).pack(side=tk.LEFT, padx=5)
        self.prop_text = scrolledtext.ScrolledText(prop_frame, height=10, font=("Consolas", 10), wrap=tk.WORD)
        self.prop_text.pack(fill=tk.BOTH, expand=True)

        # 清理缓存 / 配置管理
        util_frame = ttk.Frame(tools_tab)
        util_frame.pack(fill=tk.X, pady=10)
        ttk.Button(util_frame, text="🧹 清理 Gradle 缓存", command=self.clear_cache).pack(side=tk.LEFT, padx=5)
        ttk.Button(util_frame, text="💾 保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(util_frame, text="📂 加载配置", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(util_frame, text="📋 生成 Actions", command=self.generate_actions).pack(side=tk.LEFT, padx=5)

        # ----- Tab3: 输出与历史 -----
        output_tab = ttk.Frame(main_notebook, padding=10)
        main_notebook.add(output_tab, text="输出与历史")

        # 控制台输出
        console_frame = ttk.LabelFrame(output_tab, text="构建输出", padding=5)
        console_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.output_area = scrolledtext.ScrolledText(console_frame, font=("Consolas", 10), wrap=tk.WORD, state=tk.DISABLED)
        self.output_area.pack(fill=tk.BOTH, expand=True)

        # 构建历史
        history_frame = ttk.LabelFrame(output_tab, text="构建历史", padding=5)
        history_frame.pack(fill=tk.BOTH, expand=True)
        self.history_tree = ttk.Treeview(history_frame, columns=("time", "task", "result"), show="headings", height=6)
        self.history_tree.heading("time", text="时间")
        self.history_tree.heading("task", text="任务")
        self.history_tree.heading("result", text="结果")
        self.history_tree.column("time", width=160)
        self.history_tree.column("task", width=250)
        self.history_tree.column("result", width=100)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.configure(yscrollcommand=history_scroll.set)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

    # ---------- 新功能：Gradle 分发镜像管理 ----------
    def get_wrapper_props_path(self):
        """返回 gradle-wrapper.properties 的完整路径，若没有则返回 None"""
        project_dir = self.dir_var.get().strip()
        if project_dir:
            return os.path.join(project_dir, "gradle", "wrapper", "gradle-wrapper.properties")
        return None

    def read_wrapper_props(self):
        """读取 gradle-wrapper.properties 并返回所有属性字典"""
        path = self.get_wrapper_props_path()
        props = {}
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        props[key.strip()] = value.strip()
        return props

    def write_wrapper_props(self, props):
        """将属性字典写回 gradle-wrapper.properties"""
        path = self.get_wrapper_props_path()
        if not path:
            return False
        with open(path, "w", encoding="utf-8") as f:
            for key, value in props.items():
                f.write(f"{key}={value}\n")
        return True

    def refresh_gradle_url(self):
        """读取并显示当前的 distributionUrl"""
        props = self.read_wrapper_props()
        url = props.get("distributionUrl", "未检测")
        self.gradle_url_var.set(url)
        if url == "未检测":
            self.log("⚠️ 未找到 gradle-wrapper.properties，请先选择项目目录。")

    def apply_gradle_mirror(self):
        """根据选择的镜像替换 distributionUrl"""
        project_dir = self.dir_var.get().strip()
        if not project_dir:
            messagebox.showerror("错误", "请先选择项目目录")
            return

        props = self.read_wrapper_props()
        if "distributionUrl" not in props:
            messagebox.showerror("错误", "未找到 distributionUrl，请确认项目包含 gradle-wrapper.properties")
            return

        mirror_name = self.gradle_mirror_combo.get()
        mirror_base = GRADLE_DIST_MIRRORS.get(mirror_name)
        if not mirror_base or mirror_name == "默认（官方）":
            # 恢复原始 URL（需要保存一份原始值，这里简单提示）
            self.log("⚠️ 请使用“恢复默认”功能，或手动修改。")
            return

        if mirror_name == "自定义":
            custom_url = tk.simpledialog.askstring("自定义镜像", "请输入 Gradle 分发基础 URL（例如 https://example.com/gradle）")
            if custom_url:
                mirror_base = custom_url
            else:
                return

        # 提取版本文件名部分，替换基础 URL
        current_url = props["distributionUrl"]
        # 通常格式：https://services.gradle.org/distributions/gradle-8.14.2-bin.zip
        # 提取 gradle-xxx-bin.zip 部分
        file_part = current_url.split("/")[-1]  # gradle-8.14.2-bin.zip
        new_url = mirror_base.rstrip("/") + "/" + file_part
        props["distributionUrl"] = new_url

        if self.write_wrapper_props(props):
            self.gradle_url_var.set(new_url)
            self.log(f"✅ 已更新 distributionUrl 为镜像：{new_url}")
        else:
            messagebox.showerror("错误", "无法写入 gradle-wrapper.properties")

    def reset_gradle_mirror(self):
        """恢复 distributionUrl 为官方地址"""
        project_dir = self.dir_var.get().strip()
        if not project_dir:
            return
        props = self.read_wrapper_props()
        if "distributionUrl" not in props:
            return
        current_url = props["distributionUrl"]
        # 替换为官方地址
        official_base = "https://services.gradle.org/distributions"
        file_part = current_url.split("/")[-1]
        new_url = f"{official_base}/{file_part}"
        props["distributionUrl"] = new_url
        if self.write_wrapper_props(props):
            self.gradle_url_var.set(new_url)
            self.log("✅ 已恢复为官方 Gradle 分发地址。")
        else:
            messagebox.showerror("错误", "写入失败")

    # ---------- 新功能：JDK 管理 ----------
    def auto_detect_jdk(self):
        """自动检测 JAVA_HOME 或 where java"""
        java_home = os.environ.get("JAVA_HOME", "")
        if java_home and os.path.isdir(java_home):
            self.jdk_var.set(java_home)
            return
        # 尝试通过 where/which 获取路径
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["where", "java"], capture_output=True, text=True)
            else:
                result = subprocess.run(["which", "java"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                java_path = result.stdout.splitlines()[0].strip()
                # 去掉 /bin/java 部分
                jdk_dir = os.path.dirname(os.path.dirname(java_path))
                if os.path.isdir(jdk_dir):
                    self.jdk_var.set(jdk_dir)
                    return
        except Exception:
            pass
        messagebox.showinfo("提示", "无法自动检测 JDK，请手动选择。")

    def browse_jdk(self):
        path = filedialog.askdirectory(title="选择 JDK 根目录（例如 C:\\Program Files\\Java\\jdk-17）")
        if path:
            self.jdk_var.set(path)

    # ---------- 新功能：GitHub 克隆 ----------
    def clone_repo(self):
        repo_url = tk.simpledialog.askstring("克隆 GitHub 仓库", "请输入 GitHub 仓库地址（支持 https/ssh）：")
        if not repo_url:
            return
        target_dir = filedialog.askdirectory(title="选择存放目录")
        if not target_dir:
            return
        try:
            self.log(f"🔄 正在克隆 {repo_url} 到 {target_dir}...")
            result = subprocess.run(["git", "clone", repo_url], cwd=target_dir, capture_output=True, text=True)
            if result.returncode == 0:
                # 自动解析仓库名并设置项目目录
                repo_name = os.path.splitext(os.path.basename(repo_url.rstrip("/")))[0]
                cloned_path = os.path.join(target_dir, repo_name)
                if os.path.isdir(cloned_path):
                    self.dir_var.set(cloned_path)
                    self.log(f"✅ 克隆成功，项目目录已设置为：{cloned_path}")
                else:
                    self.log(f"✅ 克隆完成，但未自动定位到项目目录，请手动选择。")
            else:
                self.log(f"❌ 克隆失败：{result.stderr}")
        except Exception as e:
            self.log(f"💥 克隆异常：{str(e)}")

    # ---------- 新功能：gradle.properties 编辑器 ----------
    def load_gradle_properties(self):
        project_dir = self.dir_var.get().strip()
        if not project_dir:
            messagebox.showwarning("提示", "请先选择项目目录")
            return
        prop_path = os.path.join(project_dir, "gradle.properties")
        if os.path.exists(prop_path):
            with open(prop_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.prop_text.delete("1.0", tk.END)
            self.prop_text.insert("1.0", content)
        else:
            self.prop_text.delete("1.0", tk.END)
            self.prop_text.insert("1.0", "# 新建 gradle.properties\n")

    def save_gradle_properties(self):
        project_dir = self.dir_var.get().strip()
        if not project_dir:
            messagebox.showwarning("提示", "请先选择项目目录")
            return
        prop_path = os.path.join(project_dir, "gradle.properties")
        content = self.prop_text.get("1.0", tk.END)
        with open(prop_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.log("💾 gradle.properties 已保存")

    def add_jvm_args(self):
        """添加常用 JVM 参数（内存）"""
        current = self.prop_text.get("1.0", tk.END)
        if "org.gradle.jvmargs=" not in current:
            self.prop_text.insert(tk.END, "\norg.gradle.jvmargs=-Xmx4G -XX:+UseG1GC\n")
            self.log("📝 已添加典型 JVM 内存设置。")

    # ---------- 原有功能（部分展示，完整保留） ----------
    def browse_dir(self):
        path = filedialog.askdirectory(title="选择 Mod 项目根目录")
        if path:
            self.dir_var.set(path)
            self.refresh_gradle_url()

    def browse_out(self):
        path = filedialog.askdirectory(title="选择产物输出目录")
        if path:
            self.out_var.set(path)

    def log(self, text):
        self.queue.put(("log", text))

    def set_buttons_state(self, building):
        state = tk.DISABLED if building else tk.NORMAL
        self.build_btn.config(state=state)
        self.stop_btn.config(state=tk.NORMAL if building else tk.DISABLED)

    def update_progress(self, running):
        if running:
            self.progress.start(10)
        else:
            self.progress.stop()

    def set_status(self, text):
        self.queue.put(("status", text))

    def set_mirror_preset(self, urls):
        self.mirror_text.delete("1.0", tk.END)
        self.mirror_text.insert("1.0", "\n".join(urls))

    # 配置保存/加载（扩展了 JDK、Gradle 镜像）
    def save_config(self):
        config = {
            "project_dir": self.dir_var.get(),
            "task": self.task_var.get(),
            "output_dir": self.out_var.get(),
            "no_daemon": self.no_daemon_var.get(),
            "console_plain": self.console_plain_var.get(),
            "mirrors": self.mirror_text.get("1.0", tk.END).strip().splitlines(),
            "jdk_path": self.jdk_var.get(),
            "gradle_mirror": self.gradle_mirror_combo.get()
        }
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.log(f"💾 配置已保存到 {path}")

    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.dir_var.set(config.get("project_dir", ""))
            self.task_var.set(config.get("task", "build"))
            self.out_var.set(config.get("output_dir", ""))
            self.no_daemon_var.set(config.get("no_daemon", True))
            self.console_plain_var.set(config.get("console_plain", True))
            self.mirror_text.delete("1.0", tk.END)
            self.mirror_text.insert("1.0", "\n".join(config.get("mirrors", [])))
            self.jdk_var.set(config.get("jdk_path", ""))
            combo_val = config.get("gradle_mirror", "默认（官方）")
            if combo_val in GRADLE_DIST_MIRRORS:
                self.gradle_mirror_combo.set(combo_val)
            self.refresh_gradle_url()
            self.log(f"📂 配置已从 {path} 加载")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置失败：{str(e)}")

    def clear_cache(self):
        # 原逻辑保留
        result = messagebox.askyesno("清理 Gradle 缓存", "将删除用户缓存和项目缓存，确定吗？")
        if not result:
            return
        def clean():
            home_cache = os.path.expanduser("~/.gradle/caches")
            proj_cache = None
            if self.dir_var.get():
                proj_cache = os.path.join(self.dir_var.get(), ".gradle")
            for path, desc in [(home_cache, "用户缓存"), (proj_cache, "项目缓存")]:
                if path and os.path.exists(path):
                    try:
                        shutil.rmtree(path)
                        self.log(f"🧹 已删除 {desc}：{path}")
                    except Exception as e:
                        self.log(f"❌ 删除 {desc} 失败：{str(e)}")
            self.log("✅ 缓存清理完成")
        threading.Thread(target=clean, daemon=True).start()

    def generate_actions(self):
        # 原逻辑保留
        mirrors = self.mirror_text.get("1.0", tk.END).strip().splitlines()
        init_content = generate_init_gradle([m for m in mirrors if m.strip()])
        task = self.task_var.get().strip() or "build"
        yaml_template = f"""name: Build Mod with Custom Mirror
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: 17
          distribution: temurin
      - name: Create init.gradle
        run: |
          cat << 'EOF' > init.gradle
{init_content}
EOF
      - name: Build
        run: ./gradlew -I init.gradle {task} --no-daemon --console=plain
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: Mod JARs
          path: build/libs/*.jar
"""
        popup = tk.Toplevel(self.root)
        popup.title("GitHub Actions 工作流")
        popup.geometry("700x500")
        text_area = scrolledtext.ScrolledText(popup, font=("Consolas", 10))
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_area.insert("1.0", yaml_template)
        text_area.config(state=tk.DISABLED)
        ttk.Button(popup, text="复制到剪贴板", command=lambda: self.copy_to_clipboard(yaml_template)).pack(pady=5)

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log("📋 工作流已复制到剪贴板")

    def start_build(self):
        project_dir = self.dir_var.get().strip()
        if not project_dir:
            messagebox.showerror("错误", "请先选择项目目录")
            return

        mirrors_raw = self.mirror_text.get("1.0", tk.END).strip()
        if mirrors_raw:
            mirrors = [line.strip() for line in mirrors_raw.splitlines() if line.strip()]
        else:
            mirrors = DEFAULT_ALIYUN_MIRRORS

        task_raw = self.task_var.get().strip() or "build"
        tasks = task_raw.split()
        output_dir = self.out_var.get().strip() or None

        self.output_area.config(state=tk.NORMAL)
        self.output_area.delete("1.0", tk.END)
        self.output_area.config(state=tk.DISABLED)

        self.set_buttons_state(building=True)
        self.update_progress(running=True)
        self.set_status("正在构建...")
        self.stop_event.clear()

        self.build_thread = threading.Thread(
            target=self.build_worker,
            args=(project_dir, tasks, output_dir, mirrors),
            daemon=True
        )
        self.build_thread.start()

    def build_worker(self, project_dir, tasks, output_dir, mirrors):
        final_result = "成功"
        try:
            wrapper_name = "gradlew.bat" if platform.system() == "Windows" else "gradlew"
            wrapper_path = os.path.join(project_dir, wrapper_name)
            if not os.path.isfile(wrapper_path):
                self.log("❌ 错误：找不到 Gradle Wrapper")
                final_result = "失败"
                return

            if platform.system() != "Windows":
                os.chmod(wrapper_path, 0o755)

            init_content = generate_init_gradle(mirrors)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.gradle', delete=False, encoding='utf-8') as f:
                f.write(init_content)
                init_script = f.name

            cmd = [wrapper_path, "-I", init_script]
            if self.no_daemon_var.get():
                cmd.append("--no-daemon")
            if self.console_plain_var.get():
                cmd.append("--console=plain")
            cmd.extend(tasks)

            # 如果指定了 JDK 路径，设置环境变量
            env = os.environ.copy()
            jdk_path = self.jdk_var.get().strip()
            if jdk_path and os.path.isdir(jdk_path):
                env["JAVA_HOME"] = jdk_path
                # 更新 PATH
                if platform.system() == "Windows":
                    env["PATH"] = os.path.join(jdk_path, "bin") + os.pathsep + env.get("PATH", "")
                else:
                    env["PATH"] = os.path.join(jdk_path, "bin") + os.pathsep + env.get("PATH", "")
                self.log(f"☕ 使用 JDK：{jdk_path}")

            self.log(f"🔧 执行命令：{' '.join(cmd)}")
            self.last_output_time = time.time()

            self.process = subprocess.Popen(
                cmd,
                cwd=project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )

            for line in self.process.stdout:
                if self.stop_event.is_set():
                    self.process.terminate()
                    self.log("⚠️ 构建已被用户终止。")
                    final_result = "已停止"
                    break
                self.last_output_time = time.time()
                self.log(line.rstrip())

            while self.process and self.process.poll() is None:
                if self.stop_event.is_set():
                    self.process.terminate()
                    self.log("⚠️ 构建已被用户终止。")
                    final_result = "已停止"
                    break
                if time.time() - self.last_output_time > 30:
                    self.log("⏳ 仍在处理中，请耐心等待...")
                    self.last_output_time = time.time()
                time.sleep(0.5)

            if self.process:
                self.process.wait()
                returncode = self.process.returncode
            else:
                returncode = -1

            try:
                os.unlink(init_script)
            except Exception:
                pass

            if returncode == 0:
                self.log("✅ 构建成功！")
                final_result = "成功"
                if output_dir:
                    build_libs = os.path.join(project_dir, "build", "libs")
                    if os.path.isdir(build_libs):
                        os.makedirs(output_dir, exist_ok=True)
                        for file in os.listdir(build_libs):
                            if file.endswith(".jar"):
                                src = os.path.join(build_libs, file)
                                dst = os.path.join(output_dir, file)
                                shutil.copy2(src, dst)
                                self.log(f"📦 已复制产物：{file}")
                    else:
                        self.log("⚠️ 未找到 build/libs 目录。")
                # 成功弹窗
                self.queue.put(("build_done", "success"))
            else:
                self.log(f"❌ 构建失败，退出码：{returncode}")
                final_result = "失败"
                self.queue.put(("build_done", "failure"))

        except Exception as e:
            self.log(f"💥 构建线程异常：{str(e)}")
            final_result = "异常"
            self.queue.put(("build_done", "exception"))
        finally:
            self.queue.put(("finished", final_result))

    def stop_build(self):
        if self.process and self.process.poll() is None:
            self.stop_event.set()
            self.log("⏳ 正在停止构建进程...")

    def poll_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type == "log":
                    self.output_area.config(state=tk.NORMAL)
                    self.output_area.insert(tk.END, data + "\n")
                    self.output_area.see(tk.END)
                    self.output_area.config(state=tk.DISABLED)
                elif msg_type == "finished":
                    self.set_buttons_state(building=False)
                    self.update_progress(running=False)
                    self.process = None
                    self.set_status("就绪")
                    task_str = self.task_var.get()
                    self.add_history(task_str, data)
                elif msg_type == "status":
                    self.status_var.set(data)
                elif msg_type == "build_done":
                    if data == "success":
                        messagebox.showinfo("构建完成", "打包成功！🎉")
                    elif data == "failure":
                        messagebox.showwarning("构建完成", "构建失败，请检查输出日志。")
                    # 异常也提示
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_queue)

    def add_history(self, task, result):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.current_history.append({"time": timestamp, "task": task, "result": result})
        self.history_tree.insert("", 0, values=(timestamp, task, result))
        self.save_history()

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.current_history[-100:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_history(self):
        if not os.path.exists(HISTORY_FILE):
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                self.current_history = json.load(f)
            for item in reversed(self.current_history):
                self.history_tree.insert("", 0, values=(item["time"], item["task"], item["result"]))
        except Exception:
            self.current_history = []


def main():
    root = tk.Tk()
    app = ModBuilderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()