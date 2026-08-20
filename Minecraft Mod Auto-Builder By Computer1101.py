#!/usr/bin/env python3
"""
Minecraft Mod Auto-Builder with GUI and Aliyun Mirror.
Supports Forge, Fabric, Quilt or any Gradle-based mod project.
Provides real-time output, customizable Maven mirrors, and artifact extraction.
"""

import os
import sys
import subprocess
import threading
import queue
import tempfile
import platform
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# ---------- 默认阿里云 Maven 镜像 ----------
DEFAULT_ALIYUN_MIRRORS = [
    "https://maven.aliyun.com/repository/public",
    "https://maven.aliyun.com/repository/google",
    "https://maven.aliyun.com/repository/gradle-plugin"
]

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
        self.root.title("Minecraft Mod Auto-Builder")
        self.root.geometry("860x680")
        self.root.minsize(700, 550)

        # 构建进程和线程控制
        self.process = None
        self.build_thread = None
        self.stop_event = threading.Event()
        self.queue = queue.Queue()

        # 设置样式
        self.setup_styles()
        # 创建界面组件
        self.create_widgets()
        # 定期检查输出队列
        self.poll_queue()

    def setup_styles(self):
        style = ttk.Style()
        if HAS_SV_TTK:
            sv_ttk.set_theme("light")
        else:
            # 简单美化一下标准 ttk
            style.theme_use("clam")
            style.configure("TLabel", font=("微软雅黑", 10))
            style.configure("TButton", font=("微软雅黑", 10))
            style.configure("TEntry", font=("微软雅黑", 10))
            style.configure("Header.TLabel", font=("微软雅黑", 12, "bold"))

    def create_widgets(self):
        # 主框架，添加内边距
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---------- 项目目录 ----------
        dir_frame = ttk.Frame(main_frame)
        dir_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(dir_frame, text="项目目录：", width=12).pack(side=tk.LEFT)
        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(dir_frame, text="浏览...", command=self.browse_dir).pack(side=tk.RIGHT)

        # ---------- Gradle 任务 ----------
        task_frame = ttk.Frame(main_frame)
        task_frame.pack(fill=tk.X, pady=5)
        ttk.Label(task_frame, text="Gradle 任务：", width=12).pack(side=tk.LEFT)
        self.task_var = tk.StringVar(value="build")
        task_entry = ttk.Entry(task_frame, textvariable=self.task_var)
        task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # ---------- 输出目录 ----------
        out_frame = ttk.Frame(main_frame)
        out_frame.pack(fill=tk.X, pady=5)
        ttk.Label(out_frame, text="产物输出目录：", width=12).pack(side=tk.LEFT)
        self.out_var = tk.StringVar()
        out_entry = ttk.Entry(out_frame, textvariable=self.out_var)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(out_frame, text="浏览...", command=self.browse_out).pack(side=tk.RIGHT)
        ttk.Label(main_frame, text="（留空则不复制产物）", foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        # ---------- 自定义 Maven 镜像 ----------
        mirror_frame = ttk.LabelFrame(main_frame, text="Maven 镜像（每行一个 URL，默认阿里云）", padding="10")
        mirror_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.mirror_text = scrolledtext.ScrolledText(
            mirror_frame,
            height=5,
            font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.mirror_text.pack(fill=tk.BOTH, expand=True)
        # 填入默认镜像
        self.mirror_text.insert("1.0", "\n".join(DEFAULT_ALIYUN_MIRRORS))

        # ---------- 控制按钮 ----------
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 10))
        self.build_btn = ttk.Button(btn_frame, text="▶ 开始构建", command=self.start_build)
        self.build_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止构建", command=self.stop_build, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # ---------- 进度条 ----------
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 5))

        # ---------- 控制台输出 ----------
        console_frame = ttk.LabelFrame(main_frame, text="构建输出", padding="5")
        console_frame.pack(fill=tk.BOTH, expand=True)

        self.output_area = scrolledtext.ScrolledText(
            console_frame,
            height=15,
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.output_area.pack(fill=tk.BOTH, expand=True)

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
        """构建时禁用/启用控件"""
        state = tk.DISABLED if building else tk.NORMAL
        self.build_btn.config(state=state)
        self.stop_btn.config(state=tk.NORMAL if building else tk.DISABLED)

    def update_progress(self, running):
        if running:
            self.progress.start(10)
        else:
            self.progress.stop()

    def start_build(self):
        project_dir = self.dir_var.get().strip()
        if not project_dir:
            messagebox.showerror("错误", "请先选择项目目录")
            return

        # 读取镜像列表
        mirrors_raw = self.mirror_text.get("1.0", tk.END).strip()
        if mirrors_raw:
            mirrors = [line.strip() for line in mirrors_raw.splitlines() if line.strip()]
        else:
            mirrors = DEFAULT_ALIYUN_MIRRORS  # 用户清空时使用默认

        task = self.task_var.get().strip() or "build"
        output_dir = self.out_var.get().strip() or None

        # 清空输出区域
        self.output_area.config(state=tk.NORMAL)
        self.output_area.delete("1.0", tk.END)
        self.output_area.config(state=tk.DISABLED)

        # 更新界面状态
        self.set_buttons_state(building=True)
        self.update_progress(running=True)

        # 启动构建线程
        self.stop_event.clear()
        self.build_thread = threading.Thread(
            target=self.build_worker,
            args=(project_dir, task, output_dir, mirrors),
            daemon=True
        )
        self.build_thread.start()

    def build_worker(self, project_dir, task, output_dir, mirrors):
        """在子线程中执行实际构建"""
        try:
            # 1. 定位 gradlew
            wrapper_name = "gradlew.bat" if platform.system() == "Windows" else "gradlew"
            wrapper_path = os.path.join(project_dir, wrapper_name)
            if not os.path.isfile(wrapper_path):
                self.log("❌ 错误：找不到 Gradle Wrapper，请确认是 Gradle 项目。")
                return

            # 确保可执行权限
            if platform.system() != "Windows":
                os.chmod(wrapper_path, 0o755)

            # 2. 生成临时的 init.gradle
            init_content = generate_init_gradle(mirrors)
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.gradle', delete=False, encoding='utf-8'
            ) as f:
                f.write(init_content)
                init_script = f.name

            # 3. 构建命令
            cmd = [wrapper_path, "-I", init_script, task]
            self.log(f"🔧 执行命令：{' '.join(cmd)}")

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

            # 实时读取输出
            for line in self.process.stdout:
                if self.stop_event.is_set():
                    self.process.terminate()
                    self.log("⚠️ 构建已被用户终止。")
                    break
                self.log(line.rstrip())

            self.process.wait()
            returncode = self.process.returncode

            # 清理临时脚本
            try:
                os.unlink(init_script)
            except Exception:
                pass

            if returncode == 0:
                self.log("✅ 构建成功！")
                # 复制产物
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

        except Exception as e:
            self.log(f"💥 构建线程异常：{str(e)}")
        finally:
            # 通知主线程恢复界面
            self.queue.put(("finished", None))

    def stop_build(self):
        if self.process and self.process.poll() is None:
            self.stop_event.set()
            self.log("⏳ 正在停止构建进程...")

    def poll_queue(self):
        """定期处理队列中的消息"""
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
