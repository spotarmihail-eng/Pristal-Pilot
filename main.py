import json, os, queue, subprocess, threading, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
DATA=Path(os.getenv("APPDATA",str(Path.home())))/"Pristal-Pilot"; DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"servers.json"; BG="#11151d"; PANEL="#1b2330"; FG="#edf1f7"; BLUE="#718fff"
class App:
 def __init__(self,r):
  self.r=r; self.ps={}; self.q=queue.Queue(); self.sel=None
  try:self.items=json.loads(DB.read_text(encoding="utf8"))
  except Exception:self.items=[]
  r.title("Pristal-Pilot by MrSkrenh"); r.geometry("1050x680"); r.configure(bg=BG)
  self.ui(); self.refresh(); r.after(100,self.poll); r.protocol("WM_DELETE_WINDOW",self.close)
 def save(self):DB.write_text(json.dumps(self.items,ensure_ascii=False,indent=2),encoding="utf8")
 def cur(self):return self.items[self.sel] if self.sel is not None and self.sel<len(self.items) else None
 def running(self,p):return bool(self.ps.get(p["id"]) and self.ps[p["id"]].poll() is None)
 def ui(self):
  st=ttk.Style(); st.theme_use("clam"); st.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=FG,rowheight=34)
  h=tk.Frame(self.r,bg=BG);h.pack(fill="x",padx=22,pady=18)
  tk.Label(h,text="PRISTAL-PILOT",bg=BG,fg=FG,font=("Segoe UI",22,"bold")).pack(side="left")
  tk.Label(h,text="by MrSkrenh  •  Minecraft server manager",bg=BG,fg="#99a5b8").pack(side="left",padx=14,pady=9)
  b=tk.Frame(self.r,bg=BG);b.pack(fill="both",expand=True,padx=22)
  s=tk.Frame(b,bg=PANEL,width=245);s.pack(side="left",fill="y");s.pack_propagate(False)
  tk.Label(s,text="МОИ СЕРВЕРЫ",bg=PANEL,fg="#99a5b8").pack(anchor="w",padx=14,pady=12)
  self.tree=ttk.Treeview(s,show="tree");self.tree.pack(fill="both",expand=True,padx=8);self.tree.bind("<<TreeviewSelect>>",self.choose)
  tk.Button(s,text="+ Добавить сервер",command=self.add,bg=BLUE,fg="white",relief="flat",pady=10).pack(fill="x",padx=10,pady=10)
  m=tk.Frame(b,bg=BG);m.pack(side="left",fill="both",expand=True,padx=(16,0))
  self.title=tk.Label(m,text="Выберите сервер",bg=BG,fg=FG,font=("Segoe UI",19,"bold"));self.title.pack(anchor="w")
  self.info=tk.Label(m,text="Создайте профиль для начала",bg=BG,fg="#99a5b8");self.info.pack(anchor="w",pady=8)
  bar=tk.Frame(m,bg=BG);bar.pack(fill="x",pady=8)
  for t,c,f in [("▶ Запустить","#28865f",self.start),("■ Остановить","#a84858",self.stop),("⚙ Настройки","#303c50",self.edit)]:tk.Button(bar,text=t,command=f,bg=c,fg="white",relief="flat",padx=14,pady=9).pack(side="left",padx=(0,7))
  tk.Label(m,text="КОНСОЛЬ СЕРВЕРА",bg=PANEL,fg="#99a5b8",anchor="w",padx=12,pady=9).pack(fill="x")
  self.out=tk.Text(m,bg="#090d13",fg="#c9d8ec",font=("Consolas",10),state="disabled",relief="flat");self.out.pack(fill="both",expand=True)
  row=tk.Frame(m,bg=BG);row.pack(fill="x",pady=9)
  self.cmd=tk.Entry(row,bg=PANEL,fg=FG,insertbackground=FG,relief="flat");self.cmd.pack(side="left",fill="x",expand=True,ipady=9);self.cmd.bind("<Return>",lambda e:self.send())
  tk.Button(row,text="Отправить",command=self.send,bg=BLUE,fg="white",relief="flat",padx=14,pady=7).pack(side="right",padx=7)
  tk.Label(self.r,text="Разработана MrSkrenh  •  Бесплатная программа  •  Данные серверов отдельно от приложения",bg=BG,fg="#99a5b8",font=("Segoe UI",8)).pack(pady=10)
 def log(self,x):self.out.configure(state="normal");self.out.insert("end",x+"\n");self.out.see("end");self.out.configure(state="disabled")
 def refresh(self):
  self.tree.delete(*self.tree.get_children())
  for i,p in enumerate(self.items):self.tree.insert("","end",iid=str(i),text=("● " if self.running(p) else "○ ")+p["name"])
  if self.sel is not None and self.sel<len(self.items):self.tree.selection_set(str(self.sel))
 def choose(self,e=None):
  a=self.tree.selection()
  if a:self.sel=int(a[0]);p=self.cur();self.title.config(text=p["name"]);self.info.config(text=f'{p["folder"]} | Java: {p["java"]} | RAM: {p["ram"]} GB')
 def add(self):
  n=simpledialog.askstring("Новый сервер","Название:")
  if not n:return
  d=filedialog.askdirectory(title="Папка сервера")
  if not d:return
  self.items.append(dict(id=os.urandom(8).hex(),name=n,folder=d,jar="server.jar",java="java",ram="4",minimum="1"));self.sel=len(self.items)-1;self.save();self.refresh();self.choose();self.log("Профиль создан. Укажите JAR в настройках.")
 def edit(self):
  p=self.cur()
  if not p:messagebox.showinfo("Pristal-Pilot","Выберите сервер.");return
  if self.running(p):messagebox.showwarning("Сервер запущен","Сначала остановите сервер.");return
  w=tk.Toplevel(self.r);w.title("Настройки");w.configure(bg=PANEL);fields={}
  for i,(label,key) in enumerate([("Название","name"),("Папка","folder"),("JAR-файл","jar"),("Java / java.exe","java"),("ОЗУ GB","ram"),("Минимум GB","minimum")]):
   tk.Label(w,text=label,bg=PANEL,fg=FG).grid(row=i,column=0,padx=10,pady=7,sticky="w")
   e=tk.Entry(w,width=38,bg=BG,fg=FG,insertbackground=FG);e.insert(0,p.get(key,""));e.grid(row=i,column=1,padx=10,pady=7);fields[key]=e
  def save():
   try:
    if float(fields["minimum"].get())<=0 or float(fields["ram"].get())<float(fields["minimum"].get()):raise ValueError()
   except ValueError:messagebox.showerror("Ошибка","Проверьте объём памяти.");return
   for k,e in fields.items():p[k]=e.get().strip()
   self.save();self.refresh();self.choose();w.destroy()
  tk.Button(w,text="Сохранить",command=save,bg=BLUE,fg="white").grid(row=6,column=1,pady=10)
 def start(self):
  p=self.cur()
  if not p:messagebox.showinfo("Pristal-Pilot","Выберите сервер.");return
  if self.running(p):self.log("Уже запущен.");return
  j=Path(p["folder"])/p["jar"]
  if not j.is_file():
   f=filedialog.askopenfilename(initialdir=p["folder"],filetypes=[("Java JAR","*.jar")])
   if not f:return
   p["folder"],p["jar"]=str(Path(f).parent),Path(f).name;self.save()
  try:
   lo,hi=int(float(p["minimum"])),int(float(p["ram"]))
   if lo<=0 or hi<lo:raise ValueError("Некорректная RAM")
   proc=subprocess.Popen([p["java"],f"-Xms{lo}G",f"-Xmx{hi}G","-jar",p["jar"],"nogui"],cwd=p["folder"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf8",errors="replace",bufsize=1)
   self.ps[p["id"]]=proc;threading.Thread(target=self.reader,args=(p["id"],proc),daemon=True).start();self.log("Сервер запускается…");self.refresh()
  except (OSError,ValueError) as e:messagebox.showerror("Ошибка запуска",str(e))
 def reader(self,pid,proc):
  for line in proc.stdout:self.q.put((pid,line.rstrip()))
  self.q.put((pid,"[Pristal-Pilot] Процесс завершён."))
 def poll(self):
  try:
   while True:
    pid,line=self.q.get_nowait()
    if self.cur() and self.cur()["id"]==pid:self.log(line)
    self.refresh()
  except queue.Empty:pass
  self.r.after(120,self.poll)
 def send(self):
  p=self.cur();c=self.cmd.get().strip()
  if not p or not self.running(p):self.log("Нет запущенного сервера.");return
  if c:
   try:self.ps[p["id"]].stdin.write(c+"\n");self.ps[p["id"]].stdin.flush();self.cmd.delete(0,"end")
   except OSError as e:self.log(str(e))
 def stop(self):
  p=self.cur()
  if not p or not self.running(p):self.log("Сервер не запущен.");return
  try:self.ps[p["id"]].stdin.write("stop\n");self.ps[p["id"]].stdin.flush();self.log("Отправлена команда stop.")
  except OSError as e:self.log(str(e))
 def close(self):
  active=[p["name"] for p in self.items if self.running(p)]
  if active and not messagebox.askyesno("Работающие серверы","Активны: "+", ".join(active)+". Закрытие панели не остановит Java. Выйти?"):return
  self.r.destroy()
if __name__=="__main__":
 r=tk.Tk();App(r);r.mainloop()
