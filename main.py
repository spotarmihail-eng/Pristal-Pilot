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
APP_VERSION = "0.2.0"
GITHUB_RELEASE_API = "https://api.github.com/repos/spotarmihail-eng/Pristal-Pilot/releases/latest"
BG, PANEL, PANEL2 = "#0d1119", "#151d2a", "#1c2737"
FG, MUTED, BLUE, GREEN, RED = "#edf2fa", "#94a3b8", "#6488ff", "#35c58a"


class App:
    def __init__(self, root):
        self.root = root
        self.processes = {}
        self.queue = queue.Queue()
        self.selected = None
        self.metrics = {}
        try:
            self.items = json.loads(DB.read_text(encoding="utf-8"))
        except Exception:
            self.items = []
        self.root.title("Pristal-Pilot by MrSkrenh")
        self.root.geometry("1280x790")
        self.root.minsize(1050, 680)
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

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=22, pady=(18, 14))
        tk.Label(header, text="PRISTAL-PILOT", bg=BG, fg=FG,
                 font=("Segoe UI", 23, "bold")).pack(side="left")
        tk.Label(header, text="by MrSkrenh  /  MINECRAFT SERVER CONTROL",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=16, pady=11)
        tk.Button(header, text="↻  Проверить обновления", command=self.check_updates,
                  bg="#202e46", fg="#b9cbff", activebackground="#2b3d5b",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=12, pady=8).pack(side="right")
        tk.Label(header, text=f"v{APP_VERSION}", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="right", padx=10)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=22)

        # Left: server list
        left = tk.Frame(body, bg=PANEL, width=245)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="МОИ СЕРВЕРЫ", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(16, 10))
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<<TreeviewSelect>>", self.choose)
        tk.Button(left, text="+  Добавить сервер", command=self.add,
                  bg=BLUE, fg="white", activebackground="#5275e8",
                  relief="flat", font=("Segoe UI", 9, "bold"), pady=11).pack(fill="x", padx=10, pady=12)
        self.limit_label = tk.Label(left, text="Одновременно: 0 / 3",
                                    bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.limit_label.pack(anchor="w", padx=14, pady=(0, 12))

        # Center: controls and console
        center = tk.Frame(body, bg=BG)
        center.pack(side="left", fill="both", expand=True, padx=15)
        self.server_title = tk.Label(center, text="Выберите сервер", bg=BG, fg=FG,
                                     font=("Segoe UI", 20, "bold"))
        self.server_title.pack(anchor="w")
        self.server_info = tk.Label(center, text="Добавьте профиль, чтобы начать работу",
                                    bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.server_info.pack(anchor="w", pady=(5, 13))

        controls = tk.Frame(center, bg=BG)
        controls.pack(fill="x", pady=(0, 13))
        for label, color, action in [
            ("▶  Запустить", GREEN, self.start),
            ("■  Остановить", "#b94d60", self.stop),
            ("↻  Перезапустить", "#465a7b", self.restart),
            ("⚙  Настройки", "#303e53", self.edit),
        ]:
            tk.Button(controls, text=label, command=action, bg=color, fg="white",
                      activebackground=color, relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=11, pady=9).pack(side="left", padx=(0, 7))

        console_head = tk.Frame(center, bg=PANEL, padx=12, pady=9)
        console_head.pack(fill="x")
        tk.Label(console_head, text="КОНСОЛЬ СЕРВЕРА", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.status = tk.Label(console_head, text="● ОСТАНОВЛЕН", bg=PANEL, fg="#e3a4ad",
                               font=("Segoe UI", 8, "bold"))
        self.status.pack(side="right")
        self.output = tk.Text(center, bg="#080c12", fg="#c8d6e9",
                              insertbackground=FG, font=("Consolas", 9),
                              state="disabled", relief="flat", wrap="word")
        self.output.pack(fill="both", expand=True)
        command_row = tk.Frame(center, bg=BG)
        command_row.pack(fill="x", pady=10)
        self.command = tk.Entry(command_row, bg=PANEL, fg=FG, insertbackground=FG,
                                relief="flat", font=("Consolas", 10))
        self.command.pack(side="left", fill="x", expand=True, ipady=10)
        self.command.bind("<Return>", lambda _event: self.send())
        tk.Button(command_row, text="Отправить", command=self.send, bg=BLUE,
                  fg="white", relief="flat", padx=15, pady=8).pack(side="right", padx=(8, 0))

        # Right: live resource panel
        right = tk.Frame(body, bg=PANEL, width=205)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Label(right, text="МОНИТОРИНГ", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=13, pady=(16, 12))
        self.ram_card, self.ram_value = self.card(right, "RAM процесса")
        self.ram_card.pack(fill="x", padx=10, pady=5)
        self.cpu_card, self.cpu_value = self.card(right, "CPU процесса")
        self.cpu_card.pack(fill="x", padx=10, pady=5)
        self.tps_card, self.tps_value = self.card(right, "TPS")
        self.tps_card.pack(fill="x", padx=10, pady=5)
        self.players_card, self.players_value = self.card(right, "Игроки")
        self.players_card.pack(fill="x", padx=10, pady=5)
        tk.Label(right, text="TPS и игроки появятся\nпосле получения данных\nот сервера.",
                 bg=PANEL, fg=MUTED, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=13, pady=12)

        tk.Label(self.root,
                 text="Разработана MrSkrenh  •  Бесплатная программа  •  Данные серверов хранятся отдельно",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(pady=10)

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def refresh_servers(self):
        self.tree.delete(*self.tree.get_children())
        active = 0
        for i, profile in enumerate(self.items):
            is_running = self.running(profile)
            active += int(is_running)
            prefix = "●  " if is_running else "○  "
            self.tree.insert("", "end", iid=str(i), text=prefix + profile["name"])
        self.limit_label.config(text=f"Одновременно: {active} / 3")
        if self.selected is not None and self.selected < len(self.items):
            self.tree.selection_set(str(self.selected))

    def choose(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        self.selected = int(selected[0])
        profile = self.current()
        self.server_title.config(text=profile["name"])
        self.server_info.config(
            text=f'{profile["folder"]}   •   Java {profile["java"]}   •   RAM {profile["minimum"]}-{profile["ram"]} GB'
        )
        self.status.config(text="● РАБОТАЕТ" if self.running(profile) else "● ОСТАНОВЛЕН",
                           fg=GREEN if self.running(profile) else "#e3a4ad")
        self.log(f'Выбран сервер: {profile["name"]}')

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
        if self.running(profile):
            self.log("Этот сервер уже запущен.")
            return
        active = sum(1 for item in self.items if self.running(item))
        if active >= 3:
            messagebox.showwarning("Лимит серверов", "Можно одновременно запускать не более 3 серверов.")
            return
        jar = Path(profile["folder"]) / profile["jar"]
        if not jar.is_file():
            selected = filedialog.askopenfilename(
                initialdir=profile["folder"], filetypes=[("Java JAR", "*.jar")])
            if not selected:
                return
            profile["folder"], profile["jar"] = str(Path(selected).parent), Path(selected).name
            self.save()
        try:
            low, high = int(float(profile["minimum"])), int(float(profile["ram"]))
            if low <= 0 or high < low:
                raise ValueError("Некорректные значения RAM.")
            proc = subprocess.Popen(
                [profile["java"], f"-Xms{low}G", f"-Xmx{high}G",
                 "-jar", profile["jar"], "nogui"],
                cwd=profile["folder"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1
            )
            self.processes[profile["id"]] = proc
            self.metrics[profile["id"]] = {"tps": "—", "players": "—"}
            threading.Thread(target=self.reader, args=(profile["id"], proc), daemon=True).start()
            self.log("Запуск сервера…")
            self.refresh_servers()
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
                if self.current() and self.current()["id"] == profile_id:
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
        profile = self.current()
        if profile and self.running(profile):
            proc = self.processes[profile["id"]]
            if psutil:
                try:
                    process = psutil.Process(proc.pid)
                    memory = process.memory_info().rss / (1024 ** 3)
                    cpu = process.cpu_percent(interval=None)
                    self.ram_value.config(text=f"{memory:.2f} GB")
                    self.cpu_value.config(text=f"{cpu:.1f}%")
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
        self.root.after(1000, self.update_metrics)


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
