import json
import os
import queue
import hashlib
import urllib.request
import tempfile
import re
import subprocess
import threading
import sys
import time
import socket
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import psutil
except ImportError:
    psutil = None

DATA = Path(os.getenv("APPDATA", str(Path.home()))) / "Pristal-Pilot"
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "servers.json"
APP_VERSION = "0.7.0"
GITHUB_RELEASE_API = "https://api.github.com/repos/spotarmihail-eng/Pristal-Pilot/releases/latest"
BG, PANEL, PANEL2 = "#0d1119", "#151d2a", "#1c2737"
FG, MUTED, BLUE, GREEN, RED = "#edf2fa", "#94a3b8", "#6488ff", "#35c58a", "#b94d60"


class App:
    def __init__(self, root):
        self.root = root
        self.processes = {}
        self.queue = queue.Queue()
        self.selected = None
        self.metrics = {}
        self.adaptive_state = {}
        try:
            self.items = json.loads(DB.read_text(encoding="utf-8"))
        except Exception:
            self.items = []
        self.root.title("Pristal-Pilot by MrSkrenh")
        self.root.geometry("1440x850")
        self.root.minsize(1180, 700)
        self.root.configure(bg=BG)
        self.build_ui()
        self.refresh_servers()
        self.root.after(150, self.poll)
        self.root.after(1000, self.update_metrics)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def save(self):
        DB.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")

    def current(self):
        if self.selected is None or self.selected >= len(self.items):
            return None
        return self.items[self.selected]

    def running(self, profile):
        proc = self.processes.get(profile["id"])
        return bool(proc and proc.poll() is None)

    def card(self, parent, title, value="—", color=FG):
        frame = tk.Frame(parent, bg=PANEL2, padx=13, pady=12)
        tk.Label(frame, text=title.upper(), bg=PANEL2, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        val = tk.Label(frame, text=value, bg=PANEL2, fg=color,
                       font=("Segoe UI", 17, "bold"))
        val.pack(anchor="w", pady=(5, 0))
        return frame, val

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=38, borderwidth=0)
        style.map("Treeview", background=[("selected", "#2b3d5b")],
                  foreground=[("selected", FG)])
        self.root.configure(bg=BG)

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        # Постоянная левая навигация: на главном экране — разделы приложения,
        # внутри сервера — навигация по разделам выбранного сервера.
        self.sidebar = tk.Frame(shell, bg=PANEL, width=218)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.nav_header = tk.Frame(self.sidebar, bg=PANEL)
        self.nav_header.pack(fill="x", padx=14, pady=(18, 22))
        tk.Label(self.nav_header, text="PRISTAL", bg=PANEL, fg=FG,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(self.nav_header, text="PILOT  •  by MrSkrenh", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")

        self.nav_area = tk.Frame(self.sidebar, bg=PANEL)
        self.nav_area.pack(fill="both", expand=True, padx=9)
        self.sidebar_footer = tk.Frame(self.sidebar, bg=PANEL)
        self.sidebar_footer.pack(fill="x", padx=12, pady=12)

        self.workspace = tk.Frame(shell, bg=BG)
        self.workspace.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.workspace, bg=BG)
        self.content.pack(fill="both", expand=True, padx=20, pady=18)

        self.monitor = tk.Frame(shell, bg=PANEL, width=218)
        self.monitor.pack(side="right", fill="y")
        self.monitor.pack_propagate(False)
        tk.Label(self.monitor, text="МОНИТОРИНГ", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(20, 14))
        self.ram_card, self.ram_value = self.card(self.monitor, "RAM процесса")
        self.ram_card.pack(fill="x", padx=10, pady=5)
        self.cpu_card, self.cpu_value = self.card(self.monitor, "CPU · % одного ядра")
        self.cpu_card.pack(fill="x", padx=10, pady=5)
        self.disk_card, self.disk_value = self.card(self.monitor, "Диск сервера")
        self.disk_card.pack(fill="x", padx=10, pady=5)
        self.tps_card, self.tps_value = self.card(self.monitor, "TPS")
        self.tps_card.pack(fill="x", padx=10, pady=5)
        self.players_card, self.players_value = self.card(self.monitor, "Игроки")
        self.players_card.pack(fill="x", padx=10, pady=5)
        self.adaptive_label = tk.Label(self.monitor, text="АВТОРЕЖИМ: ожидание",
                                       bg=PANEL, fg=MUTED,
                                       font=("Segoe UI", 8, "bold"))
        self.adaptive_label.pack(anchor="w", padx=13, pady=(12, 2))
        tk.Label(self.monitor,
                 text="CPU — доля одного логического ядра. При высокой нагрузке ПК приоритет Java автоматически снижается.",
                 bg=PANEL, fg=MUTED, justify="left", wraplength=185,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=13, pady=12)

        self.tree = None
        self.server_title = None
        self.server_info = None
        self.status = None
        self.output = None
        self.command = None
        self.limit_label = None
        self.current_section = "home"
        self.show_home()

    def clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def nav_button(self, label, command, active=False):
        return tk.Button(
            self.nav_area, text=label, command=command, anchor="w",
            bg="#263754" if active else PANEL, fg=FG if active else MUTED,
            activebackground="#263754", activeforeground=FG,
            relief="flat", bd=0, padx=13, pady=12,
            font=("Segoe UI", 10, "bold")
        )

    def show_home(self):
        self.selected = None
        self.current_section = "home"
        for child in self.nav_area.winfo_children():
            child.destroy()
        self.nav_button("▦  Сервера", self.show_home, True).pack(fill="x", pady=3)
        self.nav_button("ⓘ  О нас", self.show_about).pack(fill="x", pady=3)
        for child in self.sidebar_footer.winfo_children():
            child.destroy()
        tk.Label(self.sidebar_footer, text=f"Версия {APP_VERSION}",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        self.monitor.pack_forget()
        self.monitor.pack(side="right", fill="y")
        self.clear_content()

        header = tk.Frame(self.content, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        tk.Label(header, text="Мои сервера", bg=BG, fg=FG,
                 font=("Segoe UI", 23, "bold")).pack(side="left")
        tk.Button(header, text="↻ Проверить обновления",
                  command=self.check_updates, bg="#202e46", fg="#b9cbff",
                  relief="flat", padx=12, pady=9).pack(side="right")
        tk.Label(self.content,
                 text="Все созданные и добавленные серверы находятся здесь.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))

        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill="x", pady=(0, 12))
        tk.Button(actions, text="+  Создать сервер",
                  command=self.create_server_wizard, bg=BLUE, fg="white",
                  relief="flat", padx=18, pady=11,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Добавить существующий",
                  command=self.add, bg="#263754", fg=FG,
                  relief="flat", padx=16, pady=11).pack(side="left")
        self.limit_label = tk.Label(actions, text="Одновременно: 0 / 3",
                                    bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.limit_label.pack(side="right")

        list_card = tk.Frame(self.content, bg=PANEL, padx=10, pady=10)
        list_card.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_card, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.choose)
        self.refresh_servers()

    def show_about(self):
        self.current_section = "about"
        self.clear_content()
        card = tk.Frame(self.content, bg=PANEL, padx=30, pady=28)
        card.pack(fill="both", expand=True)
        tk.Label(card, text="PRISTAL-PILOT", bg=PANEL, fg=FG,
                 font=("Segoe UI", 25, "bold")).pack(anchor="w")
        tk.Label(card, text="Разработано MrSkrenh", bg=PANEL, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(22, 6))
        tk.Label(card, text="Программа бесплатная.", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 22))
        import webbrowser
        for label, url in [
            ("Discord", "https://discord.gg/vywgQxyJt"),
            ("Twitch", "https://www.twitch.tv/skrenhtv"),
            ("YouTube", "https://www.youtube.com/@skrenh"),
            ("Поддержать автора", "https://new.donatepay.ru/donate/1530153")
        ]:
            tk.Button(card, text=label,
                      command=lambda link=url: webbrowser.open(link),
                      bg=BLUE if label != "Поддержать автора" else GREEN,
                      fg="white", relief="flat", padx=18, pady=10,
                      anchor="w").pack(fill="x", pady=4)

    def show_server_page(self, section="console"):
        profile = self.current()
        if not profile:
            self.show_home()
            return
        self.current_section = section
        self.refresh_disk_usage(profile)
        for child in self.nav_area.winfo_children():
            child.destroy()
        self.nav_button("←  Назад к серверам", self.show_home).pack(fill="x", pady=(0, 12))
        tk.Label(self.nav_area, text=profile["name"], bg=PANEL, fg=FG,
                 font=("Segoe UI", 11, "bold"), wraplength=185,
                 justify="left").pack(anchor="w", padx=10, pady=(5, 12))
        core = str(profile.get("core", "")).lower()
        modded = any(x in core for x in ("fabric", "forge", "neoforge", "quilt"))
        entries = [
            ("▤  Консоль", "console"),
            ("▧  Файлы", "files"),
            ("◇  Моды" if modded else "◇  Плагины", "mods" if modded else "plugins"),
            ("⚙  Настройки", "settings"),
            ("♙  Игроки", "players"),
            ("▶  Запуск", "startup")
        ]
        for label, key in entries:
            self.nav_button(label, lambda s=key: self.show_server_page(s),
                            section == key).pack(fill="x", pady=2)
        for child in self.sidebar_footer.winfo_children():
            child.destroy()
        tk.Label(self.sidebar_footer, text=f"Одновременно: {sum(1 for p in self.items if self.running(p))} / 3",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")

        self.clear_content()
        header = tk.Frame(self.content, bg=BG)
        header.pack(fill="x", pady=(0, 14))
        self.server_title = tk.Label(header, text=profile["name"], bg=BG, fg=FG,
                                     font=("Segoe UI", 21, "bold"))
        self.server_title.pack(side="left")
        self.status = tk.Label(header,
                               text="● РАБОТАЕТ" if self.running(profile) else "● ОСТАНОВЛЕН",
                               bg=BG, fg=GREEN if self.running(profile) else "#e3a4ad",
                               font=("Segoe UI", 9, "bold"))
        self.status.pack(side="right")
        self.server_info = tk.Label(self.content,
            text=f'{profile["folder"]}  •  {profile.get("core", "Не указано")}  •  Minecraft {profile.get("version", "—")}',
            bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.server_info.pack(anchor="w", pady=(0, 12))

        if section == "console":
            self.render_console()
        elif section == "files":
            self.render_files()
        elif section == "settings":
            self.render_settings_entry()
        elif section == "players":
            self.render_players_entry()
        elif section == "startup":
            self.render_startup_entry()
        elif section in ("plugins", "mods"):
            self.render_catalog_entry(section)

    def refresh_disk_usage(self, profile):
        self.disk_value.config(text="Считаем…")
        folder = profile.get("folder", "")
        profile_id = profile.get("id")

        def measure():
            total = 0
            try:
                for root, _dirs, files in os.walk(folder):
                    for filename in files:
                        try:
                            total += os.path.getsize(os.path.join(root, filename))
                        except OSError:
                            continue
                value = f"{total / (1024 ** 3):.2f} GiB"
            except OSError:
                value = "—"

            def update():
                current = self.current()
                if current and current.get("id") == profile_id and self.disk_value.winfo_exists():
                    self.disk_value.config(text=value)
            self.root.after(0, update)

        threading.Thread(target=measure, daemon=True).start()

    def render_console(self):
        profile = self.current()
        controls = tk.Frame(self.content, bg=BG)
        controls.pack(fill="x", pady=(0, 12))
        for label, color, action in [
            ("▶ Включить", GREEN, self.start),
            ("↻ Перезапустить", "#465a7b", self.restart),
            ("■ Выключить", RED, self.stop)
        ]:
            tk.Button(controls, text=label, command=action, bg=color,
                      fg="white", relief="flat", padx=13, pady=9,
                      font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 7))
        console_head = tk.Frame(self.content, bg=PANEL, padx=12, pady=9)
        console_head.pack(fill="x")
        tk.Label(console_head, text="КОНСОЛЬ СЕРВЕРА", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.output = tk.Text(self.content, bg="#080c12", fg="#c8d6e9",
                              insertbackground=FG, font=("Consolas", 9),
                              state="disabled", relief="flat", wrap="word")
        self.output.pack(fill="both", expand=True, pady=(0, 8))
        command_row = tk.Frame(self.content, bg=BG)
        command_row.pack(fill="x")
        self.command = tk.Entry(command_row, bg=PANEL, fg=FG,
                                insertbackground=FG, relief="flat",
                                font=("Consolas", 10))
        self.command.pack(side="left", fill="x", expand=True, ipady=10)
        self.command.bind("<Return>", lambda _event: self.send())
        tk.Button(command_row, text="Отправить", command=self.send,
                  bg=BLUE, fg="white", relief="flat", padx=15, pady=8).pack(side="right", padx=(8, 0))
        # Показываем последние строки выбранного сервера при возврате к консоли.
        for line in self.metrics.get(profile["id"], {}).get("recent", []):
            self.log(line)

    def render_files(self):
        profile = self.current()
        card = tk.Frame(self.content, bg=PANEL, padx=22, pady=22)
        card.pack(fill="both", expand=True)
        tk.Label(card, text="ФАЙЛЫ СЕРВЕРА", bg=PANEL, fg=FG,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(card, text="Открой папку этого сервера в Проводнике. Внутри будут миры, конфигурации, плагины и моды.",
                 bg=PANEL, fg=MUTED, wraplength=620, justify="left").pack(anchor="w", pady=12)
        tk.Button(card, text="Открыть папку сервера",
                  command=self.open_server_files, bg=BLUE, fg="white",
                  relief="flat", padx=18, pady=11).pack(anchor="w")
        tk.Label(card, text=profile["folder"], bg=PANEL, fg=MUTED,
                 wraplength=650).pack(anchor="w", pady=(16, 0))

    def render_settings_entry(self):
        card = tk.Frame(self.content, bg=PANEL, padx=22, pady=22)
        card.pack(fill="both", expand=True)
        tk.Label(card, text="Настройки сервера", bg=PANEL, fg=FG,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(card, text="Открыть редактор основных параметров профиля. Редактор server.properties и поиск по настройкам будут добавлены следующим этапом.",
                 bg=PANEL, fg=MUTED, wraplength=620, justify="left").pack(anchor="w", pady=12)
        tk.Button(card, text="Изменить параметры профиля", command=self.edit,
                  bg=BLUE, fg="white", relief="flat", padx=16, pady=10).pack(anchor="w")

    def render_players_entry(self):
        card = tk.Frame(self.content, bg=PANEL, padx=22, pady=22)
        card.pack(fill="both", expand=True)
        tk.Label(card, text="Управление игроками", bg=PANEL, fg=FG,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(card, text="Команды доступны через консоль сервера: op, deop, kick, ban, pardon, ban-ip и pardon-ip.",
                 bg=PANEL, fg=MUTED, wraplength=620, justify="left").pack(anchor="w", pady=12)
        tk.Button(card, text="Открыть консоль", command=lambda: self.show_server_page("console"),
                  bg=BLUE, fg="white", relief="flat", padx=16, pady=10).pack(anchor="w")

    def render_startup_entry(self):
        profile = self.current()
        card = tk.Frame(self.content, bg=PANEL, padx=22, pady=22)
        card.pack(fill="both", expand=True)
        tk.Label(card, text="Параметры запуска", bg=PANEL, fg=FG,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        summary = f'Java: {profile.get("java", "java")}\nRAM: {profile.get("minimum", "1")}–{profile.get("ram", "4")} GiB\nJAR: {profile.get("jar", "server.jar")}'
        tk.Label(card, text=summary, bg=PANEL, fg=MUTED,
                 justify="left", font=("Consolas", 10)).pack(anchor="w", pady=12)
        tk.Button(card, text="Изменить параметры запуска",
                  command=self.edit, bg=BLUE, fg="white",
                  relief="flat", padx=16, pady=10).pack(anchor="w")

    def render_catalog_entry(self, section):
        card = tk.Frame(self.content, bg=PANEL, padx=22, pady=22)
        card.pack(fill="both", expand=True)
        title = "Каталог модов" if section == "mods" else "Каталог плагинов"
        tk.Label(card, text=title, bg=PANEL, fg=FG,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(card, text="Поиск и установка проектов из Modrinth будут подключены следующим этапом. Совместимость будет проверяться по ядру и версии Minecraft.",
                 bg=PANEL, fg=MUTED, wraplength=620, justify="left").pack(anchor="w", pady=12)

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def refresh_servers(self):
        try:
            if not self.tree or not self.tree.winfo_exists():
                return
            self.tree.delete(*self.tree.get_children())
        except tk.TclError:
            return
        active = 0
        for i, profile in enumerate(self.items):
            is_running = self.running(profile)
            active += int(is_running)
            prefix = "●  " if is_running else "○  "
            self.tree.insert("", "end", iid=str(i), text=prefix + profile["name"])
        self.limit_label.config(text=f"Одновременно: {active} / 3")
        if self.tree and self.selected is not None and self.selected < len(self.items):
            self.tree.selection_set(str(self.selected))

    def choose(self, _event=None):
        try:
            if not self.tree or not self.tree.winfo_exists():
                return
            selected = self.tree.selection()
        except tk.TclError:
            return
        if not selected:
            return
        self.selected = int(selected[0])
        self.show_server_page("console")

    def open_server_files(self):
        profile = self.current()
        if not profile:
            messagebox.showinfo("Файлы сервера", "Сначала выберите сервер.")
            return
        try:
            folder = Path(profile["folder"]).expanduser().resolve(strict=True)
            if not folder.is_dir():
                raise RuntimeError("Папка сервера не найдена.")
            app_root = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                        else Path(__file__).resolve().parent)
            protected_roots = [app_root, DATA.resolve()]
            for protected in protected_roots:
                if folder == protected or protected in folder.parents or folder in protected.parents:
                    raise RuntimeError("Эта папка относится к программе или её служебным данным. Открывать её через вкладку «Файлы» нельзя.")
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as error:
            messagebox.showerror("Файлы сервера", str(error))

    def show_eula_dialog(self, profile):
        window = tk.Toplevel(self.root)
        window.title("Лицензионное соглашение Minecraft")
        window.configure(bg=PANEL)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()

        tk.Label(window, text="ПЕРЕД ПЕРВЫМ ЗАПУСКОМ", bg=PANEL, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=22, pady=(20, 10))
        tk.Label(window,
                 text="Для запуска сервера необходимо ознакомиться с лицензионным соглашением Minecraft (EULA).",
                 bg=PANEL, fg=MUTED, wraplength=460, justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(0, 8))

        def open_eula():
            import webbrowser
            webbrowser.open("https://www.minecraft.net/eula")

        tk.Button(window, text="Открыть правила EULA на сайте Minecraft",
                  command=open_eula, bg="#303e53", fg=FG, relief="flat",
                  padx=12, pady=8).pack(anchor="w", padx=22, pady=(0, 14))

        accepted = tk.BooleanVar(value=False)
        tk.Checkbutton(window, text="Я согласен с правилами EULA",
                       variable=accepted, bg=PANEL, fg=FG, selectcolor=BG,
                       activebackground=PANEL, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=8)

        def confirm():
            if not accepted.get():
                return
            try:
                eula_path = Path(profile["folder"]) / "eula.txt"
                eula_path.write_text("# Minecraft EULA accepted in Pristal-Pilot\neula=true\n",
                                     encoding="utf-8")
                profile["eula_accepted"] = True
                self.save()
                window.grab_release()
                window.destroy()
                self.log("EULA принята для сервера " + profile["name"] + ".")
            except OSError as error:
                messagebox.showerror("EULA", f"Не удалось сохранить принятие EULA:\n{error}", parent=window)

        buttons = tk.Frame(window, bg=PANEL)
        buttons.pack(fill="x", padx=22, pady=(12, 20))
        ok_button = tk.Button(buttons, text="ОК", command=confirm,
                              state="disabled", bg=BLUE, fg="white",
                              disabledforeground="#77839a", relief="flat",
                              padx=24, pady=9)
        ok_button.pack(side="right")
        tk.Label(buttons, text="Без согласия сервер нельзя запустить",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        accepted.trace_add("write", lambda *_: ok_button.config(
            state="normal" if accepted.get() else "disabled"))
        window.protocol("WM_DELETE_WINDOW", window.destroy)

    def add(self):
        name = simpledialog.askstring("Новый сервер", "Название сервера:")
        if not name:
            return
        folder = filedialog.askdirectory(title="Выберите папку сервера")
        if not folder:
            return
        self.items.append({
            "id": os.urandom(8).hex(), "name": name.strip(), "folder": folder,
            "jar": "server.jar", "java": "java", "ram": "4", "minimum": "1"
        })
        self.selected = len(self.items) - 1
        self.save()
        self.refresh_servers()
        self.choose()
        self.log("Профиль создан. Выберите JAR-файл в настройках или при запуске.")

    def edit(self):
        profile = self.current()
        if not profile:
            messagebox.showinfo("Pristal-Pilot", "Сначала выберите сервер.")
            return
        if self.running(profile):
            messagebox.showwarning("Сервер запущен", "Перед изменением настроек остановите сервер.")
            return
        window = tk.Toplevel(self.root)
        window.title("Настройки сервера")
        window.configure(bg=PANEL)
        fields = {}
        rows = [("Название", "name"), ("Папка сервера", "folder"),
                ("Имя JAR-файла", "jar"), ("Путь к Java", "java"),
                ("Максимум RAM, GB", "ram"), ("Минимум RAM, GB", "minimum")]
        for row, (label, key) in enumerate(rows):
            tk.Label(window, text=label, bg=PANEL, fg=FG).grid(
                row=row, column=0, padx=12, pady=8, sticky="w")
            entry = tk.Entry(window, width=38, bg=BG, fg=FG, insertbackground=FG)
            entry.insert(0, profile.get(key, ""))
            entry.grid(row=row, column=1, padx=12, pady=8)
            fields[key] = entry

        def save_settings():
            try:
                low, high = float(fields["minimum"].get()), float(fields["ram"].get())
                if low <= 0 or high < low:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Проверьте значения RAM: минимум > 0, максимум не меньше минимума.")
                return
            for key, entry in fields.items():
                profile[key] = entry.get().strip()
            self.save()
            self.refresh_servers()
            self.choose()
            window.destroy()

        tk.Button(window, text="Сохранить", command=save_settings,
                  bg=BLUE, fg="white", relief="flat", padx=16, pady=8).grid(
                      row=len(rows), column=1, pady=12)

    def start(self):
        profile = self.current()
        if not profile:
            messagebox.showinfo("Pristal-Pilot", "Выберите сервер.")
            return
        eula_path = Path(profile["folder"]) / "eula.txt"
        try:
            eula_text = eula_path.read_text(encoding="utf-8", errors="replace") if eula_path.is_file() else ""
        except OSError:
            eula_text = ""
        if not re.search(r"(?im)^\s*eula\s*=\s*true\s*$", eula_text):
            profile["eula_accepted"] = False
            self.show_eula_dialog(profile)
            return
        profile["eula_accepted"] = True
        if self.running(profile):
            self.log("Этот сервер уже запущен.")
            return
        active = sum(1 for item in self.items if self.running(item))
        if active >= 3:
            messagebox.showwarning("Лимит серверов", "Можно одновременно запускать не более 3 серверов.")
            return
        jar = Path(profile["folder"]) / profile.get("jar", "server.jar")
        if not profile.get("launch_args") and not jar.is_file():
            selected = filedialog.askopenfilename(
                initialdir=profile["folder"], filetypes=[("Java JAR", "*.jar")])
            if not selected:
                return
            profile["folder"], profile["jar"] = str(Path(selected).parent), Path(selected).name
            self.save()
        if profile.get("launch_args") and not (Path(profile["folder"]) / profile["launch_args"].lstrip("@")).is_file():
            messagebox.showerror("Файлы ядра", "Не найден файл аргументов запуска Forge/NeoForge. Попробуйте создать сервер заново.")
            return
        try:
            low, high = int(float(profile["minimum"])), int(float(profile["ram"]))
            if low <= 0 or high < low:
                raise ValueError("Некорректные значения RAM.")
            command = [profile["java"], f"-Xms{low}G", f"-Xmx{high}G"]
            if profile.get("launch_args"):
                command.extend([profile["launch_args"], "nogui"])
            else:
                command.extend(["-jar", profile["jar"], "nogui"])
            proc = subprocess.Popen(
                command,
                cwd=profile["folder"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1
            )
            self.processes[profile["id"]] = proc
            self.metrics[profile["id"]] = {"tps": "—", "players": "—"}
            threading.Thread(target=self.reader, args=(profile["id"], proc), daemon=True).start()
            self.log("Запуск сервера…")
            self.refresh_servers()
            if self.status and self.status.winfo_exists():
                self.status.config(text="● РАБОТАЕТ", fg=GREEN)
        except (OSError, ValueError) as error:
            messagebox.showerror("Ошибка запуска", str(error))

    def reader(self, profile_id, proc):
        for line in proc.stdout:
            self.queue.put((profile_id, line.rstrip()))
        self.queue.put((profile_id, "[Pristal-Pilot] Процесс завершён."))

    def poll(self):
        try:
            while True:
                profile_id, line = self.queue.get_nowait()
                stats = self.metrics.setdefault(profile_id, {"tps": "—", "players": "—"})
                tps_match = re.search(r"(?i)(?:TPS|тпс)[^0-9]*([0-9]+(?:\.[0-9]+)?)", line)
                player_match = re.search(r"(?i)(?:There are|Онлайн:?)\s*(\d+)", line)
                if tps_match:
                    stats["tps"] = tps_match.group(1)
                if player_match:
                    stats["players"] = player_match.group(1)
                stats.setdefault("recent", []).append(line)
                stats["recent"] = stats["recent"][-300:]
                if self.current() and self.current()["id"] == profile_id:
                    if self.output and self.output.winfo_exists():
                        self.log(line)
                    self.tps_value.config(text=stats["tps"])
                    self.players_value.config(text=stats["players"])
                self.refresh_servers()
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def send(self):
        profile = self.current()
        command = self.command.get().strip()
        if not profile or not self.running(profile):
            self.log("Нет запущенного сервера.")
            return
        if command:
            try:
                proc = self.processes[profile["id"]]
                proc.stdin.write(command + "\n")
                proc.stdin.flush()
                self.command.delete(0, "end")
                if command.lower() == "tps":
                    self.log("Запрошены показатели TPS…")
            except OSError as error:
                self.log(str(error))

    def stop(self):
        profile = self.current()
        if not profile or not self.running(profile):
            self.log("Сервер не запущен.")
            return
        try:
            proc = self.processes[profile["id"]]
            proc.stdin.write("stop\n")
            proc.stdin.flush()
            self.log("Отправлена команда stop. Ожидаем корректного завершения…")
        except OSError as error:
            self.log(str(error))

    def restart(self):
        profile = self.current()
        if not profile:
            messagebox.showinfo("Pristal-Pilot", "Выберите сервер.")
            return
        if not self.running(profile):
            self.start()
            return
        try:
            self.processes[profile["id"]].stdin.write("stop\n")
            self.processes[profile["id"]].stdin.flush()
            self.log("Сервер остановится и будет запущен повторно.")
            self.root.after(4000, lambda: self._restart_when_stopped(profile["id"]))
        except OSError as error:
            self.log(str(error))

    def _restart_when_stopped(self, profile_id):
        profile = next((p for p in self.items if p["id"] == profile_id), None)
        if not profile:
            return
        if self.running(profile):
            self.root.after(1000, lambda: self._restart_when_stopped(profile_id))
            return
        self.selected = self.items.index(profile)
        self.start()

    def update_metrics(self):
        host_load = psutil.cpu_percent(interval=None) if psutil else 0.0
        if psutil:
            for item in self.items:
                if not self.running(item):
                    continue
                try:
                    process = psutil.Process(self.processes[item["id"]].pid)
                    state = self.adaptive_state.get(item["id"], "normal")
                    if host_load >= 85 and state != "reduced":
                        process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
                        self.adaptive_state[item["id"]] = "reduced"
                        if self.current() and self.current()["id"] == item["id"]:
                            self.log("Высокая нагрузка ПК: приоритет Java снижен.")
                    elif host_load <= 70 and state == "reduced":
                        process.nice(psutil.NORMAL_PRIORITY_CLASS if os.name == "nt" else 0)
                        self.adaptive_state[item["id"]] = "normal"
                        if self.current() and self.current()["id"] == item["id"]:
                            self.log("Нагрузка ПК снизилась: приоритет Java восстановлен.")
                except (psutil.Error, OSError):
                    pass

        profile = self.current()
        if profile and self.running(profile):
            proc = self.processes[profile["id"]]
            if psutil:
                try:
                    process = psutil.Process(proc.pid)
                    memory = process.memory_info().rss / (1024 ** 3)
                    cpu = process.cpu_percent(interval=None)
                    self.ram_value.config(text=f"{memory:.2f} GB")
                    self.cpu_value.config(text=f"{cpu:.1f}% ядра")
                    if self.adaptive_state.get(profile["id"]) == "reduced":
                        self.adaptive_label.config(text=f"ЩАДЯЩИЙ РЕЖИМ: ПК {host_load:.0f}%", fg="#e3b66b")
                    else:
                        self.adaptive_label.config(text=f"АВТОРЕЖИМ: обычный · ПК {host_load:.0f}%", fg=GREEN)
                except (psutil.Error, OSError):
                    self.ram_value.config(text="—")
                    self.cpu_value.config(text="—")
            else:
                self.ram_value.config(text="—")
                self.cpu_value.config(text="Установите psutil")
            stats = self.metrics.get(profile["id"], {})
            self.tps_value.config(text=stats.get("tps", "—"))
            self.players_value.config(text=stats.get("players", "—"))
        else:
            self.ram_value.config(text="—")
            self.cpu_value.config(text="—")
            self.tps_value.config(text="—")
            self.players_value.config(text="—")
            self.adaptive_label.config(text="АВТОРЕЖИМ: ожидание", fg=MUTED)
        self.root.after(1000, self.update_metrics)

    def create_server_wizard(self):
        win = tk.Toplevel(self.root)
        win.title("Создать Minecraft-сервер")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        fields = {}
        rows = [("Название", "name", "Мой сервер"), ("Ядро", "core", "Paper"),
                ("Версия Minecraft", "version", "1.21.4"), ("Java (java / java17 / java21 / путь)", "java", "java"),
                ("RAM максимум, GB", "ram", "4"), ("RAM минимум, GB", "minimum", "1"),
                ("Порт", "port", "25565")]
        tk.Label(win, text="СОЗДАНИЕ СЕРВЕРА", bg=PANEL, fg=FG,
                 font=("Segoe UI", 15, "bold")).grid(row=0, column=0, columnspan=2, padx=18, pady=14, sticky="w")
        for row, (label, key, default) in enumerate(rows, start=1):
            tk.Label(win, text=label, bg=PANEL, fg=MUTED).grid(row=row, column=0, padx=18, pady=7, sticky="w")
            if key == "core":
                widget = ttk.Combobox(win, values=["Paper", "Purpur", "Vanilla", "Fabric", "Forge", "NeoForge"], state="readonly", width=28)
                widget.set(default)
            elif key == "java":
                widget = ttk.Combobox(win, values=["java", "java17", "java21", "java8"], width=28)
                widget.set(default)
            else:
                widget = tk.Entry(win, width=31, bg=BG, fg=FG, insertbackground=FG, relief="flat")
                widget.insert(0, default)
            widget.grid(row=row, column=1, padx=18, pady=7, ipady=5)
            fields[key] = widget
        folder_var = tk.StringVar(value=str(Path.home() / "Pristal-Pilot-Servers" / "my-server"))
        tk.Label(win, text="Папка", bg=PANEL, fg=MUTED).grid(row=8, column=0, padx=18, pady=7, sticky="w")
        tk.Entry(win, textvariable=folder_var, width=31, bg=BG, fg=FG, insertbackground=FG, relief="flat").grid(row=8, column=1, padx=18, pady=7, ipady=5)
        def browse():
            chosen = filedialog.askdirectory()
            if chosen:
                folder_var.set(chosen)
        tk.Button(win, text="Выбрать папку…", command=browse, bg="#303e53", fg=FG, relief="flat").grid(row=9, column=1, padx=18, pady=5, sticky="e")
        tk.Label(win, text="Доступны Paper, Purpur, Vanilla, Fabric, Forge и NeoForge. Для модов дополнительно установите совместимые файлы в mods.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).grid(row=10, column=0, columnspan=2, padx=18, pady=8, sticky="w")
        def submit():
            try:
                name, core, version = fields["name"].get().strip(), fields["core"].get(), fields["version"].get().strip()
                java = fields["java"].get().strip() or "java"
                low, high, port = float(fields["minimum"].get()), float(fields["ram"].get()), int(fields["port"].get())
                folder = Path(folder_var.get()).expanduser()
                if not name or not version or low <= 0 or high < low or not 1 <= port <= 65535:
                    raise ValueError
                if folder.exists() and any(folder.iterdir()):
                    messagebox.showerror("Папка занята", "Выберите пустую папку, чтобы не затронуть существующие файлы.", parent=win)
                    return
            except Exception:
                messagebox.showerror("Параметры", "Проверьте название, версию, RAM и порт (1–65535).", parent=win)
                return
            win.destroy()
            threading.Thread(target=self._download_new_server, args=(name, core, version, java, str(folder), str(low), str(high), port), daemon=True).start()
            self.log("Загружаем ядро и создаём сервер…")
        tk.Button(win, text="Скачать ядро и создать", command=submit, bg=BLUE, fg="white",
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=15, pady=10).grid(row=11, column=0, columnspan=2, padx=18, pady=16, sticky="ew")

    def _download_new_server(self, name, core, version, java, folder, minimum, ram, port):
        try:
            import shutil
            import urllib.parse
            target = Path(folder)
            target.mkdir(parents=True, exist_ok=True)
            headers = {"User-Agent": "Pristal-Pilot"}
            launch_args = None
            if core == "Paper":
                api = f"https://api.papermc.io/v2/projects/paper/versions/{urllib.parse.quote(version)}/builds"
                with urllib.request.urlopen(urllib.request.Request(api, headers=headers), timeout=30) as response:
                    builds = json.loads(response.read().decode("utf-8")).get("builds", [])
                if not builds:
                    raise RuntimeError("Paper: сборки для этой версии не найдены.")
                build = builds[-1]
                jar = build["downloads"]["application"]["name"]
                url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{build['build']}/downloads/{jar}"
            elif core == "Purpur":
                url = f"https://api.purpurmc.org/v2/purpur/{urllib.parse.quote(version)}/latest/download"
            elif core == "Fabric":
                def get_json(api_url):
                    with urllib.request.urlopen(urllib.request.Request(api_url, headers=headers), timeout=30) as response:
                        return json.loads(response.read().decode("utf-8"))
                loaders = get_json(f"https://meta.fabricmc.net/v2/versions/loader/{urllib.parse.quote(version)}")
                installers = get_json("https://meta.fabricmc.net/v2/versions/installer")
                if not loaders or not installers:
                    raise RuntimeError("Fabric не поддерживает указанную версию Minecraft.")
                loader_version = loaders[0]["loader"]["version"]
                installer_version = installers[0]["version"]
                url = (f"https://meta.fabricmc.net/v2/versions/loader/{urllib.parse.quote(version)}/"
                       f"{urllib.parse.quote(loader_version)}/{urllib.parse.quote(installer_version)}/server/jar")
            elif core in ("Forge", "NeoForge"):
                import xml.etree.ElementTree as ET
                if core == "Forge":
                    with urllib.request.urlopen(urllib.request.Request("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", headers=headers), timeout=30) as response:
                        promotions = json.loads(response.read().decode("utf-8"))
                    builds = promotions.get("promos", {})
                    forge_version = builds.get(version + "-recommended") or builds.get(version + "-latest")
                    if not forge_version:
                        raise RuntimeError(f"Forge: нет рекомендуемой сборки для Minecraft {version}.")
                    installer_version = f"{version}-{forge_version}"
                    installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{installer_version}/forge-{installer_version}-installer.jar"
                else:
                    metadata_url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
                    with urllib.request.urlopen(urllib.request.Request(metadata_url, headers=headers), timeout=30) as response:
                        xml_root = ET.fromstring(response.read())
                    # NeoForge uses MC-style prefixes without the leading "1." (e.g. 21.1 for MC 1.21.1).
                    neoforge_mc_prefix = version[2:] if version.startswith("1.") else version
                    candidates = [node.text for node in xml_root.findall(".//version")
                                  if node.text and node.text.startswith(neoforge_mc_prefix + ".")]
                    if not candidates:
                        raise RuntimeError(f"NeoForge: не найдена сборка для Minecraft {version}.")
                    def version_key(value):
                        return tuple(int(part) if part.isdigit() else part for part in re.findall(r"\d+|[A-Za-z]+", value))
                    installer_version = sorted(candidates, key=version_key)[-1]
                    installer_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{installer_version}/neoforge-{installer_version}-installer.jar"
                installer_path = target / "modloader-installer.jar"
                with urllib.request.urlopen(urllib.request.Request(installer_url, headers=headers), timeout=180) as response, installer_path.open("wb") as output:
                    shutil.copyfileobj(response, output)
                install = subprocess.run([java, "-jar", str(installer_path), "--installServer"],
                                         cwd=str(target), capture_output=True, text=True, timeout=900)
                if install.returncode != 0:
                    details = (install.stderr or install.stdout or "Нет подробностей")[-2500:]
                    raise RuntimeError(f"{core}: установка завершилась с ошибкой. Проверьте Java и версию.\n{details}")
                installer_path.unlink(missing_ok=True)
                if core == "Forge":
                    args_files = list((target / "libraries").glob("net/minecraftforge/forge/*/win_args.txt")) or list((target / "libraries").glob("net/minecraftforge/forge/*/unix_args.txt"))
                else:
                    args_files = list((target / "libraries").glob("net/neoforged/neoforge/*/win_args.txt")) or list((target / "libraries").glob("net/neoforged/neoforge/*/unix_args.txt"))
                if not args_files:
                    raise RuntimeError(f"{core}: установщик не создал unix_args.txt; проверьте журнал установщика.")
                launch_args = "@" + str(args_files[-1].relative_to(target)).replace("\\", "/")
            else:
                with urllib.request.urlopen("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", timeout=30) as response:
                    manifest = json.loads(response.read().decode("utf-8"))
                item = next((entry for entry in manifest["versions"] if entry["id"] == version), None)
                if not item:
                    raise RuntimeError("Версия Vanilla не найдена в официальном списке Mojang.")
                with urllib.request.urlopen(item["url"], timeout=30) as response:
                    metadata = json.loads(response.read().decode("utf-8"))
                url = metadata["downloads"]["server"]["url"]
            if core not in ("Forge", "NeoForge"):
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=180) as response, (target / "server.jar").open("wb") as output:
                    shutil.copyfileobj(response, output)
            (target / "eula.txt").write_text("eula=false\n", encoding="utf-8")
            (target / "server.properties").write_text(f"server-port={port}\n", encoding="utf-8")
            profile = {"id": os.urandom(8).hex(), "name": name, "folder": str(target),
                       "jar": "server.jar", "launch_args": launch_args,
                       "java": java, "ram": ram, "minimum": minimum, "port": str(port),
                       "core": core, "version": version, "eula_accepted": False}
            def done():
                self.items.append(profile)
                self.selected = len(self.items) - 1
                self.save()
                self.refresh_servers()
                self.choose()
                self.log(f"{core} {version} создан. Ожидается подтверждение EULA.")
                self.show_eula_dialog(profile)
            self.root.after(0, done)
        except Exception as error:
            self.root.after(0, lambda err=str(error): messagebox.showerror("Ошибка создания сервера", err))

    def show_network_info(self):
        profile = self.current()
        if not profile:
            messagebox.showinfo("IP сервера", "Сначала выберите профиль сервера.")
            return
        port = int(profile.get("port", 25565))
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            local_ip = "не определён"
        win = tk.Toplevel(self.root)
        win.title("IP и внешний доступ")
        win.configure(bg=PANEL)
        tk.Label(win, text=f"Сервер: {profile['name']}", bg=PANEL, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=22, pady=(20, 8))
        local_address = f"{local_ip}:{port}"
        local_row = tk.Frame(win, bg=PANEL)
        local_row.pack(fill="x", padx=22, pady=8)
        tk.Label(local_row, text=f"Локальный адрес: {local_address}", bg=PANEL, fg=FG).pack(side="left")
        def copy_address(value, label):
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["clip"],
                        input=value + "\\n",
                        text=True,
                        check=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                else:
                    win.clipboard_clear()
                    win.clipboard_append(value)
                    win.update()
                messagebox.showinfo("IP скопирован", f"{label} скопирован в буфер обмена.", parent=win)
            except Exception as exc:
                messagebox.showerror(
                    "Не удалось скопировать IP",
                    f"Не получилось записать адрес в буфер обмена.\n\nАдрес: {value}\nОшибка: {exc}",
                    parent=win
                )
        tk.Button(local_row, text="Копировать", command=lambda: copy_address(local_address, "Локальный адрес"),
                  bg="#303e53", fg=FG, relief="flat", padx=10, pady=5).pack(side="right")
        public_row = tk.Frame(win, bg=PANEL)
        public_row.pack(fill="x", padx=22, pady=8)
        public = tk.Label(public_row, text="Внешний IP: определяем…", bg=PANEL, fg=FG)
        public.pack(side="left")
        public_value = {"address": None}
        public_copy = tk.Button(public_row, text="Копировать", state="disabled",
                                bg="#303e53", fg=FG, relief="flat", padx=10, pady=5)
        public_copy.pack(side="right")
        tk.Label(win, text="Для подключения из интернета настройте проброс TCP-порта на роутере либо используйте туннель (например, Playit) или VPS. Показ внешнего IP не означает, что порт открыт.",
                 bg=PANEL, fg=MUTED, wraplength=440, justify="left").pack(anchor="w", padx=22, pady=12)
        def fetch():
            try:
                request = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "Pristal-Pilot"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    address = response.read().decode("ascii").strip()
                full_address = f"{address}:{port}"
                def show_public_address():
                    public_value["address"] = full_address
                    public.config(text=f"Внешний IP: {full_address}")
                    public_copy.config(state="normal", command=lambda: copy_address(full_address, "Внешний адрес"))
                self.root.after(0, show_public_address)
            except Exception:
                self.root.after(0, lambda: public.config(text="Внешний IP: не удалось определить"))
        threading.Thread(target=fetch, daemon=True).start()

    def check_updates(self):
        self.log("Проверяем обновления на GitHub…")
        button_thread = threading.Thread(target=self._check_updates_worker, daemon=True)
        button_thread.start()

    def _check_updates_worker(self):
        try:
            request = urllib.request.Request(
                GITHUB_RELEASE_API,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "Pristal-Pilot-Updater"}
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                release = json.loads(response.read().decode("utf-8"))
            latest = release.get("tag_name", "").lstrip("v")
            current_parts = tuple(int(x) for x in APP_VERSION.split("."))
            latest_parts = tuple(int(x) for x in latest.split("."))
            if latest_parts <= current_parts:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Обновления", f"У вас актуальная версия Pristal-Pilot ({APP_VERSION})."))
                return
            asset = next((a for a in release.get("assets", [])
                          if a.get("name") == "Pristal-Pilot-Setup.exe"), None)
            if not asset:
                raise RuntimeError("В последнем релизе не найден Pristal-Pilot-Setup.exe.")
            notes = release.get("body") or "Список изменений не опубликован."
            self.root.after(0, lambda: self._offer_update(latest, asset, notes))
        except Exception as error:
            self.root.after(0, lambda err=str(error): messagebox.showerror(
                "Проверка обновлений", f"Не удалось проверить обновления:\n{err}"))

    def _offer_update(self, version, asset, notes):
        if not messagebox.askyesno(
            "Доступно обновление",
            f"Доступна версия {version} (установлена {APP_VERSION}).\n\n"
            f"{notes[:1800]}\n\nСкачать и установить обновление сейчас?"
        ):
            return
        threading.Thread(target=self._download_and_install, args=(asset,), daemon=True).start()

    def _download_and_install(self, asset):
        try:
            url = asset.get("browser_download_url")
            if not url or not url.startswith("https://github.com/"):
                raise RuntimeError("Ссылка на установщик недействительна.")
            self.root.after(0, lambda: self.log("Скачиваем обновление…"))
            target = Path(tempfile.gettempdir()) / "Pristal-Pilot-Update.exe"
            request = urllib.request.Request(url, headers={"User-Agent": "Pristal-Pilot-Updater"})
            digest = hashlib.sha256()
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
            expected = asset.get("digest")
            if expected and expected.startswith("sha256:"):
                if digest.hexdigest().lower() != expected.split(":", 1)[1].lower():
                    target.unlink(missing_ok=True)
                    raise RuntimeError("Контрольная сумма установщика не совпала. Обновление отменено.")
            self.root.after(0, lambda: self.log("Загрузка завершена. Подготавливаем установку…"))
            # A detached helper waits for this process to exit, installs silently, then relaunches the app.
            helper = Path(tempfile.gettempdir()) / "pristal_pilot_update.cmd"
            pid = os.getpid()
            exe = str(Path(sys.executable))
            helper.write_text(
                "@echo off\r\n"
                f":waitloop\r\ntasklist /FI \"PID eq {pid}\" 2>NUL | find \"{pid}\" >NUL\r\n"
                "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto waitloop)\r\n"
                f"start /wait \"\" \"{target}\" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART\r\n"
                f"if exist \"{exe}\" start \"\" \"{exe}\"\r\n"
                "del \"%~f0\"\r\n",
                encoding="utf-8"
            )
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(["cmd.exe", "/c", str(helper)], creationflags=creationflags,
                             close_fds=True)
            self.root.after(0, self.root.destroy)
        except Exception as error:
            self.root.after(0, lambda err=str(error): messagebox.showerror(
                "Ошибка обновления", f"Не удалось установить обновление:\n{err}"))

    def close(self):
        active = [p["name"] for p in self.items if self.running(p)]
        if active and not messagebox.askyesno(
            "Работающие серверы",
            "Активны: " + ", ".join(active) +
            ". Закрытие панели не остановит Java-процессы. Выйти?"
        ):
            return
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
