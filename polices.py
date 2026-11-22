"""
Gestionnaire de polices — petit logiciel Windows pour voir, trier,
installer et désinstaller ses polices d'écriture.

Lancer :  python polices.py      (ou double-clic sur Lancer.bat)
Dépendances : pip install pillow rarfile
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageTk

IS_WIN = sys.platform == "win32"
FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")
ARCHIVE_EXT = (".zip", ".rar", ".7z")

if IS_WIN:
    import winreg
    SYS_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    USER_FONTS = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts")
    CONFIG = os.path.join(os.environ["APPDATA"], "GestionnairePolices.json")
else:  # pour tester sous Linux/Mac
    SYS_FONTS = "/usr/share/fonts"
    USER_FONTS = os.path.expanduser("~/.local/share/fonts")
    CONFIG = os.path.expanduser("~/.gestionnaire_polices.json")

REG_PATH = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
ROW_H = 64
BG, FG, ACC, SEL = "#ffffff", "#1e1e1e", "#2f6fde", "#dce8ff"


# ---------------------------------------------------------------- polices
class FontInfo:
    __slots__ = ("path", "family", "style", "user", "ext")

    def __init__(self, path, family, style, user):
        self.path, self.family, self.style, self.user = path, family, style, user
        self.ext = os.path.splitext(path)[1].lower()

    @property
    def name(self):
        return self.family if self.style in ("Regular", "Normal", "") else f"{self.family} {self.style}"


def read_font(path, user):
    try:
        f = ImageFont.truetype(path, 12)
        fam, sty = f.getname()
        return FontInfo(path, fam or os.path.basename(path), sty or "", user)
    except Exception:
        return None


def scan_fonts():
    fonts, seen = [], set()
    for folder, user in ((USER_FONTS, True), (SYS_FONTS, False)):
        if not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith(FONT_EXT):
                    p = os.path.join(root, fn)
                    key = os.path.normcase(p)
                    if key in seen:
                        continue
                    seen.add(key)
                    fi = read_font(p, user)
                    if fi:
                        fonts.append(fi)
    return fonts


def notify_font_change():
    if IS_WIN:
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)


def install_font(src):
    """Installe pour l'utilisateur courant (pas besoin d'être admin)."""
    os.makedirs(USER_FONTS, exist_ok=True)
    dest = os.path.join(USER_FONTS, os.path.basename(src))
    base, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(dest):
        dest = f"{base}_{n}{ext}"
        n += 1
    shutil.copy2(src, dest)
    fi = read_font(dest, True)
    if IS_WIN:
        kind = "OpenType" if ext.lower() in (".otf", ".otc") else "TrueType"
        label = f"{fi.name if fi else os.path.basename(dest)} ({kind})"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
            winreg.SetValueEx(k, label, 0, winreg.REG_SZ, dest)
        ctypes.windll.gdi32.AddFontResourceW(dest)
    return fi


def uninstall_font(fi):
    if IS_WIN:
        ctypes.windll.gdi32.RemoveFontResourceW(fi.path)
        hive = winreg.HKEY_CURRENT_USER if fi.user else winreg.HKEY_LOCAL_MACHINE
        try:
            with winreg.OpenKey(hive, REG_PATH, 0, winreg.KEY_ALL_ACCESS) as k:
                i, todel = 0, []
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    full = val if os.path.isabs(val) else os.path.join(SYS_FONTS, val)
                    if os.path.normcase(full) == os.path.normcase(fi.path):
                        todel.append(name)
                    i += 1
                for name in todel:
                    winreg.DeleteValue(k, name)
        except PermissionError:
            raise PermissionError("Police système : relancez le logiciel en administrateur.")
    os.remove(fi.path)


def find_7z():
    for p in (shutil.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if p and os.path.exists(p):
            return p
    return None


def extract_archive(path, out):
    low = path.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            z.extractall(out)
        return
    sevenzip = find_7z()
    if sevenzip:
        subprocess.run([sevenzip, "x", "-y", f"-o{out}", path], check=True,
                       capture_output=True, creationflags=0x08000000 if IS_WIN else 0)
        return
    if low.endswith(".rar"):
        try:
            import rarfile
            with rarfile.RarFile(path) as r:
                r.extractall(out)
            return
        except Exception as e:
            raise RuntimeError(f"Impossible d'ouvrir le RAR ({e}).\nInstallez 7-Zip (gratuit) : https://www.7-zip.org")
    raise RuntimeError("Installez 7-Zip (https://www.7-zip.org) pour ouvrir ce type d'archive.")


def collect_fonts(paths, tmp):
    """Renvoie la liste des fichiers police contenus dans des fichiers/archives/dossiers."""
    found = []
    for p in paths:
        if os.path.isdir(p):
            for r, _, fs in os.walk(p):
                found += [os.path.join(r, f) for f in fs if f.lower().endswith(FONT_EXT)]
        elif p.lower().endswith(FONT_EXT):
            found.append(p)
        elif p.lower().endswith(ARCHIVE_EXT):
            out = tempfile.mkdtemp(dir=tmp)
            extract_archive(p, out)
            found += collect_fonts([out], tmp)
    # ignore les fichiers parasites de macOS
    return [f for f in found if "__MACOSX" not in f and not os.path.basename(f).startswith("._")]


# ---------------------------------------------------------------- interface
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestionnaire de polices")
        self.geometry("1150x720")
        self.minsize(800, 500)
        self.configure(bg=BG)
        self.cfg = self.load_cfg()
        self.fonts, self.view = [], []
        self.cache = {}
        self.sel = set()
        self.anchor = None

        self.sample = tk.StringVar(value=self.cfg.get("sample", "Portez ce vieux whisky au juge blond qui fume"))
        self.size = tk.IntVar(value=self.cfg.get("size", 28))
        self.search = tk.StringVar()
        self.filter = tk.StringVar(value="Toutes")
        self.sort = tk.StringVar(value="Nom")

        self.build_ui()
        for v in (self.sample, self.size):
            v.trace_add("write", lambda *_: self.after_idle(self.refresh_previews))
        for v in (self.search, self.filter, self.sort):
            v.trace_add("write", lambda *_: self.apply_filter())
        self.reload()

    # -- config
    def load_cfg(self):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                c = json.load(f)
        except Exception:
            c = {}
        c.setdefault("favorites", [])
        c.setdefault("tags", {})
        return c

    def save_cfg(self):
        self.cfg["sample"], self.cfg["size"] = self.sample.get(), self.size.get()
        try:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def is_fav(self, fi):
        return fi.path in self.cfg["favorites"]

    # -- construction
    def build_ui(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("TButton", padding=(10, 5))
        st.configure("Accent.TButton", background=ACC, foreground="white")
        st.map("Accent.TButton", background=[("active", "#1f56b8")])

        top = tk.Frame(self, bg=BG, padx=10, pady=8)
        top.pack(fill="x")
        ttk.Button(top, text="➕ Installer des polices…", style="Accent.TButton",
                   command=self.ask_install).pack(side="left")
        ttk.Button(top, text="⭐ Favori", command=self.toggle_fav).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="🗑 Désinstaller", command=self.uninstall_sel).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="📂 Ouvrir le dossier", command=self.open_folder).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="⟳", width=3, command=self.reload).pack(side="left", padx=(8, 0))
        self.count = tk.Label(top, bg=BG, fg="#666")
        self.count.pack(side="right")

        bar = tk.Frame(self, bg="#f3f4f6", padx=10, pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text="Texte :", bg="#f3f4f6").pack(side="left")
        ttk.Entry(bar, textvariable=self.sample, width=40).pack(side="left", padx=(4, 12))
        tk.Label(bar, text="Taille :", bg="#f3f4f6").pack(side="left")
        ttk.Scale(bar, from_=10, to=72, variable=self.size, length=120,
                  command=lambda v: self.size.set(int(float(v)))).pack(side="left", padx=4)
        tk.Label(bar, textvariable=self.size, bg="#f3f4f6", width=3).pack(side="left", padx=(0, 12))
        tk.Label(bar, text="🔍", bg="#f3f4f6").pack(side="left")
        ttk.Entry(bar, textvariable=self.search, width=18).pack(side="left", padx=(2, 12))
        ttk.Combobox(bar, textvariable=self.filter, state="readonly", width=16,
                     values=["Toutes", "Favoris", "Installées par moi", "Système"]).pack(side="left")
        tk.Label(bar, text=" Tri :", bg="#f3f4f6").pack(side="left")
        ttk.Combobox(bar, textvariable=self.sort, state="readonly", width=10,
                     values=["Nom", "Type", "Fichier", "Taille"]).pack(side="left", padx=4)

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=5, bg="#ddd")
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG)
        self.canvas = tk.Canvas(left, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        body.add(left, stretch="always", minsize=400)

        right = tk.Frame(body, bg=BG, padx=14, pady=10)
        self.d_title = tk.Label(right, bg=BG, fg=FG, font=("Segoe UI", 14, "bold"), anchor="w", wraplength=330, justify="left")
        self.d_title.pack(fill="x")
        self.d_info = tk.Label(right, bg=BG, fg="#666", anchor="w", justify="left", wraplength=330)
        self.d_info.pack(fill="x", pady=(2, 8))
        self.d_img = tk.Label(right, bg=BG, anchor="nw")
        self.d_img.pack(fill="both", expand=True)
        body.add(right, minsize=300, width=380)

        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<MouseWheel>", lambda e: self.scroll(-e.delta // 40))
        self.canvas.bind("<Button-4>", lambda e: self.scroll(-3))
        self.canvas.bind("<Button-5>", lambda e: self.scroll(3))
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Double-Button-1>", lambda e: self.toggle_fav())
        self.bind("<Up>", lambda e: self.move(-1))
        self.bind("<Down>", lambda e: self.move(1))
        self.bind("<Prior>", lambda e: self.move(-8))
        self.bind("<Next>", lambda e: self.move(8))
        self.bind("<Delete>", lambda e: self.uninstall_sel() if self.focus_get() == self.canvas or not isinstance(self.focus_get(), ttk.Entry) else None)
        self.bind("<f>", lambda e: None if isinstance(self.focus_get(), ttk.Entry) else self.toggle_fav())
        self.protocol("WM_DELETE_WINDOW", lambda: (self.save_cfg(), self.destroy()))

    # -- données
    def reload(self):
        self.count.config(text="Chargement des polices…")
        def work():
            fonts = scan_fonts()
            self.after(0, lambda: self.loaded(fonts))
        threading.Thread(target=work, daemon=True).start()

    def loaded(self, fonts):
        self.fonts = fonts
        self.cache.clear()
        self.sel.clear()
        self.apply_filter()

    def apply_filter(self):
        q = self.search.get().lower().strip()
        f = self.filter.get()
        v = [x for x in self.fonts if (not q or q in x.name.lower() or q in os.path.basename(x.path).lower())]
        if f == "Favoris":
            v = [x for x in v if self.is_fav(x)]
        elif f == "Installées par moi":
            v = [x for x in v if x.user]
        elif f == "Système":
            v = [x for x in v if not x.user]
        key = {"Nom": lambda x: x.name.lower(),
               "Type": lambda x: (x.ext, x.name.lower()),
               "Fichier": lambda x: os.path.basename(x.path).lower(),
               "Taille": lambda x: -os.path.getsize(x.path) if os.path.exists(x.path) else 0}[self.sort.get()]
        v.sort(key=key)
        self.view = v
        self.sel &= {x.path for x in v}
        self.count.config(text=f"{len(v)} / {len(self.fonts)} polices")
        self.canvas.yview_moveto(0)
        self.draw()
        self.show_detail()

    # -- rendu
    def render(self, fi, text, size, width):
        key = (fi.path, text, size, width)
        img = self.cache.get(key)
        if img is None:
            if len(self.cache) > 400:
                self.cache.clear()
            try:
                font = ImageFont.truetype(fi.path, size)
                im = Image.new("RGB", (width, int(size * 1.5)), BG)
                ImageDraw.Draw(im).text((0, size * 0.15), text, font=font, fill=FG)
            except Exception:
                im = Image.new("RGB", (width, 20), BG)
                ImageDraw.Draw(im).text((0, 3), "(aperçu impossible)", fill="#a00")
            img = self.cache[key] = ImageTk.PhotoImage(im)
        return img

    def refresh_previews(self):
        self.draw()
        self.show_detail()

    def row_h(self):
        return max(ROW_H, int(self.size.get() * 1.5) + 26)

    def yview(self, *args):
        self.canvas.yview(*args)
        self.draw()

    def scroll(self, n):
        self.canvas.yview_scroll(n, "units")
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h, rh = max(c.winfo_width(), 300), c.winfo_height(), self.row_h()
        total = len(self.view) * rh
        c.configure(scrollregion=(0, 0, w, max(total, h)), yscrollincrement=rh // 3)
        top = c.canvasy(0)
        first, last = int(top // rh), int((top + h) // rh) + 1
        text, size = self.sample.get() or "Aa", self.size.get()
        for i in range(max(0, first), min(len(self.view), last + 1)):
            fi, y = self.view[i], i * rh
            if fi.path in self.sel:
                c.create_rectangle(0, y, w, y + rh, fill=SEL, width=0)
            c.create_line(0, y + rh - 1, w, y + rh - 1, fill="#eee")
            star = "⭐ " if self.is_fav(fi) else ""
            tag = "" if fi.user else "  · système"
            c.create_text(12, y + 6, anchor="nw", text=f"{star}{fi.name}{tag}",
                          fill="#666", font=("Segoe UI", 9))
            c.create_image(12, y + 22, anchor="nw", image=self.render(fi, text, size, w - 24))
        if not self.view:
            c.create_text(w // 2, 60, text="Aucune police", fill="#888", font=("Segoe UI", 12))

    def show_detail(self):
        fi = next((x for x in self.view if x.path == self.anchor), None)
        if not fi:
            self.d_title.config(text="Sélectionnez une police")
            self.d_info.config(text="Clic = sélection · Ctrl/Maj+clic = multi-sélection\n"
                                    "Double-clic ou F = favori · Suppr = désinstaller")
            self.d_img.config(image="")
            return
        try:
            kb = os.path.getsize(fi.path) // 1024
        except OSError:
            kb = "?"
        self.d_title.config(text=fi.name)
        self.d_info.config(text=f"{os.path.basename(fi.path)} · {kb} Ko · {fi.ext[1:].upper()}\n"
                                f"{'Installée pour vous' if fi.user else 'Police système'}\n{fi.path}")
        W = 360
        im = Image.new("RGB", (W, 900), BG)
        d = ImageDraw.Draw(im)
        y = 0
        try:
            sample = self.sample.get() or "Aa"
            for s in (64, 40, 24, 16, 12):
                f = ImageFont.truetype(fi.path, s)
                d.text((0, y), "Aa Bb Cc" if s == 64 else sample, font=f, fill=FG)
                y += int(s * 1.45)
            f = ImageFont.truetype(fi.path, 20)
            for line in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz",
                         "0123456789 àéèêçùôœ", "&@€$%?!«»()[]{}#*+-=/"):
                y += 6
                d.text((0, y), line, font=f, fill=FG)
                y += 28
        except Exception as e:
            d.text((0, y), f"Erreur : {e}", fill="#a00")
        self._detail = ImageTk.PhotoImage(im.crop((0, 0, W, y + 10)))
        self.d_img.config(image=self._detail)

    # -- sélection
    def on_click(self, e):
        self.canvas.focus_set()
        i = int(self.canvas.canvasy(e.y) // self.row_h())
        if not 0 <= i < len(self.view):
            return
        p = self.view[i].path
        if e.state & 0x0004:  # Ctrl
            self.sel ^= {p}
        elif e.state & 0x0001 and self.anchor:  # Maj
            idx = [x.path for x in self.view]
            a = idx.index(self.anchor) if self.anchor in idx else i
            self.sel = set(idx[min(a, i):max(a, i) + 1])
        else:
            self.sel = {p}
        if not e.state & 0x0001:
            self.anchor = p
        self.draw()
        self.show_detail()

    def move(self, d):
        if isinstance(self.focus_get(), ttk.Entry) or not self.view:
            return
        idx = [x.path for x in self.view]
        i = idx.index(self.anchor) + d if self.anchor in idx else 0
        i = max(0, min(len(idx) - 1, i))
        self.anchor, self.sel = idx[i], {idx[i]}
        rh, h = self.row_h(), self.canvas.winfo_height()
        top = self.canvas.canvasy(0)
        if i * rh < top or (i + 1) * rh > top + h:
            self.canvas.yview_moveto(max(0, i * rh - h / 3) / max(1, len(idx) * rh))
        self.draw()
        self.show_detail()

    def selected(self):
        return [x for x in self.view if x.path in self.sel]

    # -- actions
    def toggle_fav(self):
        sel = self.selected()
        if not sel:
            return
        favs = set(self.cfg["favorites"])
        add = not all(x.path in favs for x in sel)
        for x in sel:
            (favs.add if add else favs.discard)(x.path)
        self.cfg["favorites"] = sorted(favs)
        self.save_cfg()
        self.draw()

    def uninstall_sel(self):
        sel = self.selected()
        if not sel:
            return
        names = "\n".join("• " + x.name for x in sel[:15]) + ("\n…" if len(sel) > 15 else "")
        nsys = sum(not x.user for x in sel)
        warn = f"\n\n⚠ {nsys} police(s) système : droits administrateur nécessaires." if nsys else ""
        if not messagebox.askyesno("Désinstaller", f"Désinstaller {len(sel)} police(s) ?\n\n{names}{warn}"):
            return
        errs = []
        for x in sel:
            try:
                uninstall_font(x)
                self.fonts.remove(x)
            except Exception as e:
                errs.append(f"{x.name} : {e}")
        notify_font_change()
        self.sel.clear()
        self.cache.clear()
        self.apply_filter()
        if errs:
            messagebox.showwarning("Certaines polices n'ont pas été supprimées",
                                   "\n".join(errs[:10]) + "\n\n(Une police en cours d'utilisation peut nécessiter "
                                   "de fermer les logiciels ou de redémarrer.)")

    def ask_install(self):
        paths = filedialog.askopenfilenames(
            title="Choisir des polices ou des archives",
            filetypes=[("Polices et archives", "*.ttf *.otf *.ttc *.otc *.zip *.rar *.7z"),
                       ("Tous les fichiers", "*.*")])
        if paths:
            self.install_paths(list(paths))

    def install_paths(self, paths):
        tmp = tempfile.mkdtemp(prefix="polices_")
        try:
            try:
                files = collect_fonts(paths, tmp)
            except Exception as e:
                messagebox.showerror("Erreur", str(e))
                return
            if not files:
                messagebox.showinfo("Rien à installer", "Aucun fichier .ttf / .otf trouvé.")
                return
            infos = [(f, read_font(f, True)) for f in files]
            infos = [(f, i) for f, i in infos if i]
            installed = {(x.family, x.style) for x in self.fonts}
            new = [(f, i) for f, i in infos if (i.family, i.style) not in installed]
            dup = len(infos) - len(new)
            if not InstallDialog(self, new, dup).ok:
                return
            done = []
            for f, _ in new:
                try:
                    fi = install_font(f)
                    if fi:
                        done.append(fi)
                except Exception as e:
                    messagebox.showerror("Erreur", f"{os.path.basename(f)} : {e}")
            notify_font_change()
            self.fonts += done
            self.apply_filter()
            messagebox.showinfo("Terminé", f"{len(done)} police(s) installée(s).")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def open_folder(self):
        sel = self.selected()
        target = sel[0].path if sel else USER_FONTS
        if IS_WIN:
            if sel:
                subprocess.Popen(["explorer", "/select,", target])
            else:
                os.makedirs(USER_FONTS, exist_ok=True)
                os.startfile(USER_FONTS)


class InstallDialog(tk.Toplevel):
    """Aperçu des polices avant installation."""

    def __init__(self, app, items, dup):
        super().__init__(app)
        self.ok = False
        self.title("Installer des polices")
        self.geometry("620x520")
        self.configure(bg=BG)
        self.transient(app)
        msg = f"{len(items)} nouvelle(s) police(s) à installer."
        if dup:
            msg += f"  ({dup} déjà installée(s), ignorée(s))"
        tk.Label(self, text=msg, bg=BG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=10)
        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True, padx=12)
        cv = tk.Canvas(frame, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(frame, command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(fill="both", expand=True)
        self.imgs = []
        y = 0
        for f, fi in items:
            cv.create_text(0, y, anchor="nw", text=fi.name, fill="#666", font=("Segoe UI", 9))
            try:
                font = ImageFont.truetype(f, 26)
                im = Image.new("RGB", (560, 40), BG)
                ImageDraw.Draw(im).text((0, 2), app.sample.get() or fi.name, font=font, fill=FG)
                self.imgs.append(ImageTk.PhotoImage(im))
                cv.create_image(0, y + 16, anchor="nw", image=self.imgs[-1])
            except Exception:
                pass
            y += 62
        cv.configure(scrollregion=(0, 0, 560, y))
        cv.bind("<MouseWheel>", lambda e: cv.yview_scroll(-e.delta // 120, "units"))
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=12, pady=10)
        ttk.Button(btns, text="Annuler", command=self.destroy).pack(side="right")
        b = ttk.Button(btns, text="Installer", style="Accent.TButton", command=self.accept)
        b.pack(side="right", padx=8)
        if not items:
            b.state(["disabled"])
        self.grab_set()
        self.wait_window()

    def accept(self):
        self.ok = True
        self.destroy()


if __name__ == "__main__":
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = App()
    # fichiers passés en argument (glisser-déposer sur Lancer.bat / l'icône)
    if len(sys.argv) > 1:
        app.after(800, lambda: app.install_paths(sys.argv[1:]))
    app.mainloop()
