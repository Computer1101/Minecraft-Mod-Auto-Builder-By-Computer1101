#!/usr/bin/env python3
"""
Minecraft Mod Auto-Builder v2.0 (GUI)
Added features:
  - Real-time output with --console=plain and --no-daemon option
  - Heartbeat prompt when no output for 30s
  - One-click mirror presets (Aliyun, Tencent, Huawei, Central)
  - Save/Load configuration to JSON
  - Gradle cache cleaner
  - Build history (time, task, result)
  - Generate GitHub Actions workflow snippet
  - Multi-task support (space separated)
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
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# ---------- 默认阿里云 Maven 镜像 ----------
DEFAULT_ALIYUN_MIRRORS = [
    "https://maven.aliyun.com/repository/public",
    "https://maven.aliyun.com/repository/google",
    "https://maven.aliyun.com/repository/gradle-plugin"
]

# 其他常用镜像预设
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

# 配置文件名
CONFIG_FILE = "mc_builder_config.json"

# 构建历史文件
HISTORY_FILE = "build_history.json"

# 尝试加载主题，让界面更精美（可选依赖）
try:
    import sv_ttk
    HAS_SV_TTK = True
except ImportError:
    HAS_SV_TTK = False


def generate_init_gradle(mirrors):
    """根据镜像列表生成用于 Gradle 的 init 脚本内容"""
    repos_block = "\n".join(f"        maven {{ url '{url}' }}" for url in mirrors)
    # 保留中央仓库作为后备
    init_content = f"""\
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
    return init_content


class ModBuilderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Mod Auto-Builder v2.0")
        self.root.geometry("880x720")
        self.root.minsize(750, 600)

        # 构建进程和线程控制
        self.process = None
        self.build_thread = None
        self.stop_event = threading.Event()
        self.queue = queue.Queue()
        self.last_output_time = time.time()
        self.current_history = []

        # 设置样式
        self.setup_styles()
        # 创建界面组件
        self.create_widgets()
        # 定期检查输出队列
        self.poll_queue()
        # 加载历史记录
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
            style.configure("Header.TLabel", font=("微软雅黑", 12, "bold"))

    def create_widgets(self):
        # 主框架，添加内边距
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ========== 项目设置区 ==========
        settings_frame = ttk.LabelFrame(main_frame, text="项目设置", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # 项目目录
        dir_frame = ttk.Frame(settings_frame)
        dir_frame.pack(fill=tk.X, pady=3)
        ttk.Label(dir_frame, text="项目目录：", width=12).pack(side=tk.LEFT)
        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(dir_frame, text="浏览...", command=self.browse_dir).pack(side=tk.RIGHT)

        # Gradle 任务（支持多任务，用空格分隔）
        task_frame = ttk.Frame(settings_frame)
        task_frame.pack(fill=tk.X, pady=3)
        ttk.Label(task_frame, text="Gradle 任务：", width=12).pack(side=tk.LEFT)
        self.task_var = tk.StringVar(value="build")
        task_entry = ttk.Entry(task_frame, textvariable=self.task_var)
        task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(task_frame, text="(多个任务用空格分隔，如 clean build)", foreground="gray").pack(side=tk.LEFT)

        # 产物输出目录
        out_frame = ttk.Frame(settings_frame)
        out_frame.pack(fill=tk.X, pady=3)
        ttk.Label(out_frame, text="产物输出目录：", width=12).pack(side=tk.LEFT)
        self.out_var = tk.StringVar()
        out_entry = ttk.Entry(out_frame, textvariable=self.out_var)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(out_frame, text="浏览...", command=self.browse_out).pack(side=tk.RIGHT)

        # 构建选项
        options_frame = ttk.Frame(settings_frame)
        options_frame.pack(fill=tk.X, pady=5)
        ttk.Label(options_frame, text="构建选项：", width=12).pack(side=tk.LEFT)
        self.no_daemon_var = tk.BooleanVar(value=True)
        self.no_daemon_cb = ttk.Checkbutton(options_frame, text="不使用守护进程 (--no-daemon)", variable=self.no_daemon_var)
        self.no_daemon_cb.pack(side=tk.LEFT, padx=5)
        self.console_plain_var = tk.BooleanVar(value=True)
        self.console_plain_cb = ttk.Checkbutton(options_frame, text="详细输出 (--console=plain)", variable=self.console_plain_var)
        self.console_plain_cb.pack(side=tk.LEFT, padx=5)

        # ========== Maven 镜像设置区 ==========
        mirror_frame = ttk.LabelFrame(main_frame, text="Maven 镜像管理", padding="10")
        mirror_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 镜像预设按钮
        preset_frame = ttk.Frame(mirror_frame)
        preset_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(preset_frame, text="一键预设：", width=12).pack(side=tk.LEFT)
        for name, urls in MIRROR_PRESETS.items():
            btn = ttk.Button(preset_frame, text=name, command=lambda u=urls: self.set_mirror_preset(u))
            btn.pack(side=tk.LEFT, padx=2)

        # 镜像编辑区域
        self.mirror_text = scrolledtext.ScrolledText(
            mirror_frame,
            height=5,
            font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.mirror_text.pack(fill=tk.BOTH, expand=True)
        # 填入默认镜像
        self.mirror_text.insert("1.0", "\n".join(DEFAULT_ALIYUN_MIRRORS))

        # ========== 控制按钮 ==========
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 10))

        self.build_btn = ttk.Button(btn_frame, text="▶ 开始构建", command=self.start_build)
        self.build_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止构建", command=self.stop_build, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Button(btn_frame, text="💾 保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📂 加载配置", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🧹 清理缓存", command=self.clear_cache).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📋 生成 Actions", command=self.generate_actions).pack(side=tk.LEFT, padx=5)

        # ========== 进度条 ==========
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 5))

        # ========== 多标签页：输出、历史 ==========
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # 控制台输出
        console_frame = ttk.Frame(notebook)
        notebook.add(console_frame, text="控制台输出")
        self.output_area = scrolledtext.ScrolledText(
            console_frame,
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.output_area.pack(fill=tk.BOTH, expand=True)

        # 构建历史
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="构建历史")
        self.history_tree = ttk.Treeview(
            history_frame,
            columns=("time", "task", "result"),
            show="headings",
            height=8
        )
        self.history_tree.heading("time", text="时间")
        self.history_tree.heading("task", text="任务")
        self.history_tree.heading("result", text="结果")
        self.history_tree.column("time", width=180)
        self.history_tree.column("task", width=200)
        self.history_tree.column("result", width=100)
        self.history_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        # ========== 状态栏 ==========
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

    # ---------- 界面辅助方法 ----------
    def browse_dir(self):
        path = filedialog.askdirectory(title="选择 Mod 项目根目录")
        if path:
            self.dir_var.set(path)

    def browse_out(self):
        path = filedialog.askdirectory(title="选择产物输出目录")
        if path:
            self.out_var.set(path)

    def log(self, text):
        """线程安全地将文本添加到输出区域"""
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

    # ---------- 配置保存/加载 ----------
    def save_config(self):
        config = {
            "project_dir": self.dir_var.get(),
            "task": self.task_var.get(),
            "output_dir": self.out_var.get(),
            "no_daemon": self.no_daemon_var.get(),
            "console_plain": self.console_plain_var.get(),
            "mirrors": self.mirror_text.get("1.0", tk.END).strip().splitlines()
        }
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=CONFIG_FILE
        )
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
            self.log(f"📂 配置已从 {path} 加载")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置失败：{str(e)}")

    # ---------- 构建历史 ----------
    def add_history(self, task, result):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.current_history.append({
            "time": timestamp,
            "task": task,
            "result": result
        })
        self.history_tree.insert("", 0, values=(timestamp, task, result))
        self.save_history()

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.current_history[-100:], f, indent=2, ensure_ascii=False)  # 最多保留100条
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

    # ---------- 缓存清理 ----------
    def clear_cache(self):
        result = messagebox.askyesno(
            "清理 Gradle 缓存",
            "将删除以下目录：\n"
            "1. 用户主目录下的 .gradle/caches\n"
            "2. 项目目录下的 .gradle（如果已选择项目）\n"
            "确定继续吗？此操作不可撤销！"
        )
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
            self.log("✅ 缓存清理完成，下次构建将重新下载依赖。")

        threading.Thread(target=clean, daemon=True).start()

    # ---------- 生成 GitHub Actions 工作流 ----------
    def generate_actions(self):
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

      - name: Create init.gradle with custom mirrors
        run: |
          cat << 'EOF' > init.gradle
{init_content}
EOF

      - name: Grant execute permission for gradlew
        run: chmod +x gradlew

      - name: Build with Gradle
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

    # ---------- 构建核心逻辑 ----------
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
        tasks = task_raw.split()  # 支持多任务
        output_dir = self.out_var.get().strip() or None

        # 清空输出区域
        self.output_area.config(state=tk.NORMAL)
        self.output_area.delete("1.0", tk.END)
        self.output_area.config(state=tk.DISABLED)

        # 更新界面状态
        self.set_buttons_state(building=True)
        self.update_progress(running=True)
        self.set_status("正在构建...")

        # 启动构建线程
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
                self.log("❌ 错误：找不到 Gradle Wrapper，请确认是 Gradle 项目。")
                final_result = "失败"
                return

            if platform.system() != "Windows":
                os.chmod(wrapper_path, 0o755)

            init_content = generate_init_gradle(mirrors)
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.gradle', delete=False, encoding='utf-8'
            ) as f:
                f.write(init_content)
                init_script = f.name

            # 构建完整命令，添加选项
            cmd = [wrapper_path, "-I", init_script]
            if self.no_daemon_var.get():
                cmd.append("--no-daemon")
            if self.console_plain_var.get():
                cmd.append("--console=plain")
            cmd.extend(tasks)

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
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )

            # 实时读取输出，加入心跳检测
            for line in self.process.stdout:
                if self.stop_event.is_set():
                    self.process.terminate()
                    self.log("⚠️ 构建已被用户终止。")
                    final_result = "已停止"
                    break
                self.last_output_time = time.time()
                self.log(line.rstrip())

            # 如果进程还在运行，检查心跳
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

            # 等待进程彻底结束
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
                        self.log("⚠️ 未找到 build/libs 目录，无法复制产物。")
            else:
                self.log(f"❌ 构建失败，退出码：{returncode}")
                final_result = "失败"

        except Exception as e:
            self.log(f"💥 构建线程异常：{str(e)}")
            final_result = "异常"
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
                    # 记录历史
                    task_str = self.task_var.get()
                    self.add_history(task_str, data)  # data 是结果字符串
                elif msg_type == "status":
                    self.status_var.set(data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_queue)


def main():
    root = tk.Tk()
    app = ModBuilderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
