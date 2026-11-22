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
from tkinter import ttk, filedialog, messagebox, colorchooser

try:  # glisser-déposer (optionnel)
    from tkinterdnd2 import TkinterDnD, DND_FILES
    BaseTk = TkinterDnD.Tk
except Exception:
    TkinterDnD = None
    BaseTk = tk.Tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

IS_WIN = sys.platform == "win32"
FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")
ARCHIVE_EXT = (".zip", ".rar", ".7z")

if IS_WIN:
    import winreg
    SYS_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    USER_FONTS = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts")
    CONFIG = os.path.join(os.environ["APPDATA"], "GestionnairePolices.json")
    TRASH = os.path.join(os.environ["APPDATA"], "GestionnairePolices", "Corbeille")
else:  # pour tester sous Linux/Mac
    SYS_FONTS = "/usr/share/fonts"
    USER_FONTS = os.path.expanduser("~/.local/share/fonts")
    CONFIG = os.path.expanduser("~/.gestionnaire_polices.json")
    TRASH = os.path.expanduser("~/.gestionnaire_polices_corbeille")

# polices dont Windows a besoin : on refuse de les supprimer
PROTECTED = ("segoe", "arial", "times new roman", "courier new", "calibri", "cambria", "candara",
             "consolas", "constantia", "corbel", "tahoma", "verdana", "georgia", "trebuchet",
             "marlett", "symbol", "webdings", "wingdings", "microsoft sans serif", "ms sans serif",
             "ms serif", "lucida console", "lucida sans", "malgun", "microsoft yahei", "microsoft jhenghei",
             "yu gothic", "ms gothic", "ms mincho", "simsun", "nsimsun", "gadugi", "ebrima", "nirmala",
             "leelawadee", "myanmar text", "javanese text", "sylfaen", "mongolian baiti", "mv boli",
             "small fonts", "modern", "roman", "script", "courier", "system", "terminal", "fixedsys",
             "sitka", "bahnschrift", "ink free", "holomdl2", "sans serif collection")
STYLES = ["Serif", "Sans", "Script", "Déco", "Mono", "Symbole", "Gras", "Italique"]
REG_PATH = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
ROW_H = 64
VERSION = "dev"  # remplacé par le build GitHub (ex. 1.12)
REPO = "Pierro0871/FontManager"
THEMES = {
    "clair": dict(BG="#ffffff", FG="#1e1e1e", ACC="#2f6fde", SEL="#dce8ff", BAR="#f3f4f6", MUTED="#666666", LINE="#e6e6e6", FIELD="#ffffff"),
    "sombre": dict(BG="#1e1f22", FG="#e6e6e6", ACC="#4c8dff", SEL="#2d3f63", BAR="#2b2d31", MUTED="#9a9a9a", LINE="#3a3c41", FIELD="#383a40"),
}
BG = FG = ACC = SEL = BAR = MUTED = LINE = FIELD = ""


def set_theme(name):
    globals().update(THEMES.get(name, THEMES["clair"]))


set_theme("clair")


def parse_version(v):
    """'1.12' -> (1, 12) ; 'v1.12' accepté ; 'dev' -> None."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return None


def latest_release():
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "GestionnairePolices"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.load(r)
    url = next((a["browser_download_url"] for a in d.get("assets", []) if a["name"].endswith(".exe")), None)
    return d.get("tag_name", ""), url


def find_duplicates(fonts):
    """Polices présentes en plusieurs fichiers (même famille + style)."""
    count = {}
    for f in fonts:
        count[(f.family.lower(), f.style.lower())] = count.get((f.family.lower(), f.style.lower()), 0) + 1
    return {f.path for f in fonts if count[(f.family.lower(), f.style.lower())] > 1}


def is_protected(family, user):
    return not user and family.lower().startswith(PROTECTED)


def classify(family, style, panose_family=0, panose_serif=0, fixed=False, weight=400):
    """Devine les styles d'une police (pas toujours juste)."""
    n, tags = f"{family} {style}".lower(), set()
    if fixed or any(k in n for k in ("mono", "code", "console", "courier", "typewriter")):
        tags.add("Mono")
    if panose_family == 5 or any(k in n for k in ("symbol", "dings", "icon", "emoji", "marlett")):
        tags.add("Symbole")
    elif panose_family == 3 or any(k in n for k in ("script", "hand", "brush", "signature", "calligra", "pen ")):
        tags.add("Script")
    elif panose_family == 4 or any(k in n for k in ("display", "deco", "stencil", "grunge", "comic")):
        tags.add("Déco")
    elif "sans" in n or 11 <= panose_serif <= 15:
        tags.add("Sans")
    elif "serif" in n or 2 <= panose_serif <= 10:
        tags.add("Serif")
    if weight >= 600 or any(k in n for k in ("bold", "black", "heavy", "gras")):
        tags.add("Gras")
    if any(k in n for k in ("italic", "oblique", "italique")):
        tags.add("Italique")
    return tags


def commercial_status(text):
    t = text.lower()
    if any(k in t for k in ("personal use", "non-commercial", "noncommercial", "non commercial", "demo",
                            "usage personnel", "for personal", "not for commercial")):
        return "⚠ Usage personnel seulement (à vérifier)"
    if any(k in t for k in ("open font license", "ofl", "apache license", "public domain", "cc0",
                            "ubuntu font licence", "mit license", "free for commercial")):
        return "✅ Libre — usage commercial permis"
    return "❓ Inconnu — vérifier la licence"


def font_tables(path):
    from fontTools.ttLib import TTFont
    return TTFont(path, fontNumber=0, lazy=True)


def font_style_tags(path, family, style):
    try:
        f = font_tables(path)
        os2 = f["OS/2"] if "OS/2" in f else None
        pan = os2.panose if os2 else None
        return classify(family, style, pan.bFamilyType if pan else 0, pan.bSerifStyle if pan else 0,
                        bool(f["post"].isFixedPitch) if "post" in f else False,
                        os2.usWeightClass if os2 else 400)
    except Exception:
        return classify(family, style)


def font_license(path):
    """Auteur, licence et droits d'intégration lus dans la police."""
    try:
        f = font_tables(path)
        name = f["name"]
        get = lambda i: str(name.getDebugName(i) or "").strip()
        fs = f["OS/2"].fsType if "OS/2" in f else 0
    except Exception as e:
        return {"Erreur": str(e)}
    if fs & 0x2 and not fs & 0xC:
        embed = "Restreinte (intégration interdite)"
    elif fs & 0x4:
        embed = "Aperçu & impression seulement"
    elif fs & 0x8:
        embed = "Intégrable (modifiable)"
    else:
        embed = "Installable (aucune restriction)"
    lic = get(13)
    info = {"Auteur": get(9) or get(8), "Copyright": get(0), "Licence": lic, "Lien": get(14),
            "Intégration": embed,
            "Commercial": commercial_status(" ".join((lic, get(0), get(1), get(14))))}
    return {k: v for k, v in info.items() if v}


def font_chars(path):
    try:
        cmap = font_tables(path).getBestCmap() or {}
        return sorted(c for c in cmap if c >= 32)
    except Exception:
        return []


# ---- corbeille
def trash_index():
    try:
        with open(os.path.join(TRASH, "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_trash_index(idx):
    os.makedirs(TRASH, exist_ok=True)
    with open(os.path.join(TRASH, "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)


def move_to_trash(fi):
    import time
    os.makedirs(TRASH, exist_ok=True)
    dest = os.path.join(TRASH, f"{int(time.time() * 1000)}_{os.path.basename(fi.path)}")
    shutil.move(fi.path, dest)
    idx = trash_index()
    idx[os.path.basename(dest)] = {"name": fi.name, "path": fi.path, "date": time.strftime("%d/%m/%Y %H:%M")}
    save_trash_index(idx)


def restore_from_trash(key):
    idx = trash_index()
    fi = install_font(os.path.join(TRASH, key))
    os.remove(os.path.join(TRASH, key))
    idx.pop(key, None)
    save_trash_index(idx)
    return fi


def empty_trash(keys):
    idx = trash_index()
    for k in keys:
        try:
            os.remove(os.path.join(TRASH, k))
        except OSError:
            pass
        idx.pop(k, None)
    save_trash_index(idx)


# ---------------------------------------------------------------- polices
class FontInfo:
    __slots__ = ("path", "family", "style", "user", "ext", "tags")

    def __init__(self, path, family, style, user):
        self.path, self.family, self.style, self.user = path, family, style, user
        self.ext = os.path.splitext(path)[1].lower()
        self.tags = set()

    @property
    def name(self):
        return self.family if self.style in ("Regular", "Normal", "") else f"{self.family} {self.style}"


def read_font(path, user):
    try:
        f = ImageFont.truetype(path, 12)
        fam, sty = f.getname()
        fi = FontInfo(path, fam or os.path.basename(path), sty or "", user)
        fi.tags = font_style_tags(path, fi.family, fi.style)
        return fi
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
    move_to_trash(fi)


def create_shortcut(exe):
    q = lambda t: t.replace("'", "''")  # apostrophe dans le chemin (PowerShell)
    # GetFolderPath gère aussi un bureau déplacé dans OneDrive
    ps = ("$d=[Environment]::GetFolderPath('Desktop');"
          "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\\Gestionnaire de polices.lnk\");"
          f"$s.TargetPath='{q(exe)}';$s.WorkingDirectory='{q(os.path.dirname(exe))}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   capture_output=True, creationflags=0x08000000)


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
class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("Gestionnaire de polices")
        try:  # même plume que l'exe (dans l'exe, les fichiers sont dans sys._MEIPASS)
            self.iconbitmap(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "icon.ico"))
        except Exception:
            pass
        self.geometry("1150x720")
        self.minsize(800, 500)
        self.configure(bg=BG)
        self.cfg = self.load_cfg()
        set_theme(self.cfg.get("theme", "clair"))
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
        self.after(2500, lambda: self.check_update(True))
        self.after(1500, self.offer_shortcut)

    # -- config
    def load_cfg(self):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                c = json.load(f)
        except Exception:
            c = {}
        c.setdefault("favorites", [])
        c.setdefault("tags", {})
        c.setdefault("collections", {})
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

    def pfg(self):
        return self.cfg.get("prev_fg") or FG

    def pbg(self):
        return self.cfg.get("prev_bg") or BG

    def filter_values(self):
        return (["Toutes", "Favoris", "Installées par moi", "Système", "Doublons"]
                + [f"Style : {s}" for s in STYLES]
                + [f"📁 {c}" for c in sorted(self.cfg["collections"])])

    # -- construction
    def build_ui(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        self.configure(bg=BG)
        st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=LINE,
                     troughcolor=BAR, arrowcolor=FG, lightcolor=BAR, darkcolor=BAR)
        st.configure("TButton", padding=(10, 5), background=BAR, foreground=FG)
        st.map("TButton", background=[("active", LINE)])
        st.configure("Accent.TButton", background=ACC, foreground="white")
        st.map("Accent.TButton", background=[("active", ACC)])
        st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)])
        st.configure("TEntry", insertcolor=FG)
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", FG)

        top = tk.Frame(self, bg=BG, padx=10, pady=8)
        top.pack(fill="x")
        ttk.Button(top, text="➕ Installer des polices…", style="Accent.TButton",
                   command=self.ask_install).pack(side="left")
        for txt, cmd in (("⭐ Favori", self.toggle_fav), ("📁 Collection", self.collection_dialog),
                         ("⚖ Comparer", self.compare), ("⚡ Tri rapide", self.quick_sort),
                         ("🗑 Désinstaller", self.uninstall_sel), ("♻ Corbeille", self.trash_dialog),
                         ("💾 Exporter", self.export_sel), ("📂", self.open_folder), ("⟳", self.reload)):
            ttk.Button(top, text=txt, command=cmd).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="🌙" if self.cfg.get("theme") != "sombre" else "☀", width=3,
                   command=self.toggle_theme).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="⬆ Mise à jour", command=lambda: self.check_update(False)).pack(side="right", padx=(8, 0))
        tk.Label(top, text=f"v{VERSION}", bg=BG, fg=MUTED).pack(side="right", padx=(8, 0))
        self.count = tk.Label(top, bg=BG, fg=MUTED)
        self.count.pack(side="right")

        bar = tk.Frame(self, bg=BAR, padx=10, pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text="Texte :", bg=BAR, fg=FG).pack(side="left")
        ttk.Entry(bar, textvariable=self.sample, width=40).pack(side="left", padx=(4, 12))
        tk.Label(bar, text="Taille :", bg=BAR, fg=FG).pack(side="left")
        ttk.Scale(bar, from_=10, to=72, variable=self.size, length=120,
                  command=lambda v: self.size.set(int(float(v)))).pack(side="left", padx=4)
        tk.Label(bar, textvariable=self.size, bg=BAR, fg=FG, width=3).pack(side="left", padx=(0, 12))
        tk.Label(bar, text="🔍", bg=BAR, fg=FG).pack(side="left")
        ttk.Entry(bar, textvariable=self.search, width=18).pack(side="left", padx=(2, 12))
        self.filter_box = ttk.Combobox(bar, textvariable=self.filter, state="readonly", width=18,
                                       values=self.filter_values())
        self.filter_box.pack(side="left")
        tk.Label(bar, text=" Tri :", bg=BAR, fg=FG).pack(side="left")
        ttk.Combobox(bar, textvariable=self.sort, state="readonly", width=10,
                     values=["Nom", "Type", "Fichier", "Taille"]).pack(side="left", padx=4)
        tk.Label(bar, text="  Couleurs :", bg=BAR, fg=FG).pack(side="left")
        ttk.Button(bar, text="A", width=2, command=lambda: self.pick_color("prev_fg")).pack(side="left", padx=2)
        ttk.Button(bar, text="▇", width=2, command=lambda: self.pick_color("prev_bg")).pack(side="left", padx=2)
        ttk.Button(bar, text="↺", width=2, command=lambda: self.pick_color(None)).pack(side="left", padx=2)

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=5, bg=LINE)
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
        self.d_info = tk.Label(right, bg=BG, fg=MUTED, anchor="w", justify="left", wraplength=330)
        self.d_info.pack(fill="x", pady=(2, 4))
        self.d_lic = tk.Label(right, bg=BG, fg=FG, anchor="w", justify="left", wraplength=330)
        self.d_lic.pack(fill="x", pady=(0, 4))
        ttk.Button(right, text="🔤 Tous les caractères", command=self.charmap).pack(anchor="w", pady=(0, 8))
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
        self.bind("<Control-c>", lambda e: None if isinstance(self.focus_get(), ttk.Entry) else self.copy_names())
        if TkinterDnD:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", lambda e: self.after(10, self.install_paths, list(self.tk.splitlist(e.data))))
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
        elif f == "Doublons":
            dups = find_duplicates(self.fonts)
            v = [x for x in v if x.path in dups]
        elif f.startswith("Style : "):
            v = [x for x in v if f[8:] in x.tags]
        elif f.startswith("📁 "):
            members = set(self.cfg["collections"].get(f[2:], []))
            v = [x for x in v if x.path in members]
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
                im = Image.new("RGB", (width, int(size * 1.5)), self.pbg())
                ImageDraw.Draw(im).text((0, size * 0.15), text, font=font, fill=self.pfg())
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
            c.create_line(0, y + rh - 1, w, y + rh - 1, fill=LINE)
            star = "⭐ " if self.is_fav(fi) else ""
            tag = "" if fi.user else "  · système"
            c.create_text(12, y + 6, anchor="nw", text=f"{star}{fi.name}{tag}",
                          fill=MUTED, font=("Segoe UI", 9))
            c.create_image(12, y + 22, anchor="nw", image=self.render(fi, text, size, w - 24))
        if not self.view:
            c.create_text(w // 2, 60, text="Aucune police", fill=MUTED, font=("Segoe UI", 12))

    def show_detail(self):
        fi = next((x for x in self.view if x.path == self.anchor), None)
        if not fi:
            self.d_title.config(text="Sélectionnez une police")
            self.d_info.config(text="Clic = sélection · Ctrl/Maj+clic = multi-sélection\n"
                                    "Double-clic ou F = favori · Suppr = désinstaller\n"
                                    "Ctrl+C = copier le nom · filtre Doublons = fichiers en double")
            self.d_img.config(image="")
            self.d_lic.config(text="")
            return
        try:
            kb = os.path.getsize(fi.path) // 1024
        except OSError:
            kb = "?"
        self.d_title.config(text=fi.name)
        self.d_info.config(text=f"{os.path.basename(fi.path)} · {kb} Ko · {fi.ext[1:].upper()}\n"
                                f"{'Installée pour vous' if fi.user else 'Police système'}"
                                f"{' · 🔒 protégée' if is_protected(fi.family, fi.user) else ''}\n"
                                f"Style : {', '.join(sorted(fi.tags)) or '?'}\n{fi.path}")
        lic = font_license(fi.path)
        self.d_lic.config(text="\n".join(f"{k} : {v[:160]}" for k, v in lic.items()))
        W = 360
        im = Image.new("RGB", (W, 900), self.pbg())
        d = ImageDraw.Draw(im)
        y = 0
        try:
            sample = self.sample.get() or "Aa"
            for s in (64, 40, 24, 16, 12):
                f = ImageFont.truetype(fi.path, s)
                d.text((0, y), "Aa Bb Cc" if s == 64 else sample, font=f, fill=self.pfg())
                y += int(s * 1.45)
            f = ImageFont.truetype(fi.path, 20)
            for line in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz",
                         "0123456789 àéèêçùôœ", "&@€$%?!«»()[]{}#*+-=/"):
                y += 6
                d.text((0, y), line, font=f, fill=self.pfg())
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

    def uninstall_sel(self, sel=None):
        sel = self.selected() if sel is None else sel
        prot = [x for x in sel if is_protected(x.family, x.user)]
        sel = [x for x in sel if x not in prot]
        if prot:
            messagebox.showwarning("Polices protégées", f"{len(prot)} police(s) de Windows protégée(s), non supprimée(s) :\n"
                                   + "\n".join("• " + x.name for x in prot[:10]))
        if not sel:
            return
        names = "\n".join("• " + x.name for x in sel[:15]) + ("\n…" if len(sel) > 15 else "")
        nsys = sum(not x.user for x in sel)
        warn = f"\n\n⚠ {nsys} police(s) système : droits administrateur nécessaires." if nsys else ""
        if not messagebox.askyesno("Désinstaller", f"Désinstaller {len(sel)} police(s) ?\n"
                                   f"(elles iront dans la corbeille ♻)\n\n{names}{warn}"):
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

    def pick_color(self, key):
        if key is None:
            self.cfg.pop("prev_fg", None)
            self.cfg.pop("prev_bg", None)
        else:
            c = colorchooser.askcolor(color=self.cfg.get(key) or (FG if key == "prev_fg" else BG), parent=self)[1]
            if not c:
                return
            self.cfg[key] = c
        self.save_cfg()
        self.cache.clear()
        self.refresh_previews()

    def collection_dialog(self):
        sel = self.selected()
        if not sel:
            messagebox.showinfo("Collection", "Sélectionnez d'abord une ou plusieurs polices.")
            return
        CollectionDialog(self, sel)
        self.filter_box.config(values=self.filter_values())
        self.apply_filter()

    def compare(self):
        sel = self.selected()
        if not 2 <= len(sel) <= 4:
            messagebox.showinfo("Comparer", "Sélectionnez 2 à 4 polices (Ctrl+clic).")
            return
        CompareWindow(self, sel)

    def quick_sort(self):
        if not self.view:
            return
        QuickSort(self, list(self.view))

    def charmap(self):
        fi = next((x for x in self.view if x.path == self.anchor), None)
        if fi:
            CharMap(self, fi)

    def trash_dialog(self):
        TrashDialog(self)

    def offer_shortcut(self):
        """Une seule fois, dans l'exe : propose une icône sur le bureau."""
        if not (IS_WIN and getattr(sys, "frozen", False)) or self.cfg.get("shortcut_asked"):
            return
        self.cfg["shortcut_asked"] = True
        self.save_cfg()
        if messagebox.askyesno("Icône", "Créer une icône sur le bureau ?"):
            try:
                create_shortcut(sys.executable)
            except Exception as e:
                messagebox.showerror("Icône", f"Impossible de créer l'icône :\n{e}")

    def toggle_theme(self):
        self.cfg["theme"] = "clair" if self.cfg.get("theme") == "sombre" else "sombre"
        set_theme(self.cfg["theme"])
        self.save_cfg()
        for w in self.winfo_children():
            w.destroy()
        self.cache.clear()
        self.build_ui()
        self.apply_filter()

    def copy_names(self):
        sel = self.selected()
        if sel:
            self.clipboard_clear()
            self.clipboard_append("\n".join(x.family for x in sel))
            self.count.config(text=f"{len(sel)} nom(s) copié(s)")

    def export_sel(self):
        sel = self.selected() or self.view
        if not sel:
            return
        dest = filedialog.askdirectory(title=f"Copier {len(sel)} fichier(s) police dans…")
        if not dest:
            return
        n = 0
        for x in sel:
            try:
                shutil.copy2(x.path, dest)
                n += 1
            except OSError:
                pass
        messagebox.showinfo("Export", f"{n} fichier(s) copié(s) dans\n{dest}")

    def check_update(self, silent):
        cur = parse_version(VERSION)
        if not getattr(sys, "frozen", False) or cur is None:
            if not silent:
                messagebox.showinfo("Mise à jour", "Mise à jour automatique disponible seulement dans l'exe.")
            return
        def work():
            try:
                tag, url = latest_release()
            except Exception as e:
                if not silent:
                    self.after(0, lambda: messagebox.showerror("Mise à jour", f"Pas de connexion à GitHub :\n{e}"))
                return
            new = parse_version(tag)
            if new and url and new > cur:
                self.after(0, lambda: self.offer_update(tag, url))
            elif not silent:
                self.after(0, lambda: messagebox.showinfo("Mise à jour", f"Vous avez déjà la dernière version (v{VERSION})."))
        threading.Thread(target=work, daemon=True).start()

    def offer_update(self, tag, url):
        if not messagebox.askyesno("Mise à jour", f"Nouvelle version {tag} disponible (vous : v{VERSION}).\n\nInstaller maintenant ?"):
            return
        import urllib.request
        exe = sys.executable
        tmp = exe + ".new"
        try:
            self.count.config(text="Téléchargement de la mise à jour…")
            self.update_idletasks()
            urllib.request.urlretrieve(url, tmp)
        except Exception as e:
            messagebox.showerror("Mise à jour", f"Téléchargement impossible :\n{e}")
            return
        # un exe ouvert ne peut pas s'écraser lui-même : petit script qui attend la fermeture
        bat = os.path.join(tempfile.gettempdir(), "maj_polices.bat")
        with open(bat, "w", encoding="mbcs") as f:
            f.write(f'@echo off\r\n:boucle\r\ntimeout /t 1 /nobreak >nul\r\n'
                    f'move /y "{tmp}" "{exe}" >nul 2>&1 || goto boucle\r\n'
                    f'start "" "{exe}"\r\ndel "%~f0"\r\n')
        # sans ça le nouvel exe réutilise le dossier temporaire (effacé) de l'ancien → "Failed to load Python DLL"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000, env=env)
        self.save_cfg()
        self.destroy()

    def open_folder(self):
        sel = self.selected()
        target = sel[0].path if sel else USER_FONTS
        if IS_WIN:
            if sel:
                subprocess.Popen(["explorer", "/select,", target])
            else:
                os.makedirs(USER_FONTS, exist_ok=True)
                os.startfile(USER_FONTS)


class Win(tk.Toplevel):
    def __init__(self, app, title, geom):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.geometry(geom)
        self.configure(bg=BG)
        self.transient(app)


class CollectionDialog(Win):
    def __init__(self, app, sel):
        super().__init__(app, "Collections", "380x200")
        self.sel = sel
        cols = app.cfg["collections"]
        tk.Label(self, text=f"{len(sel)} police(s) sélectionnée(s).\nCollection (choisir ou taper un nouveau nom) :",
                 bg=BG, fg=FG, justify="left").pack(anchor="w", padx=12, pady=(12, 4))
        self.name = tk.StringVar(value=app.filter.get()[2:] if app.filter.get().startswith("📁 ") else "")
        ttk.Combobox(self, textvariable=self.name, values=sorted(cols), width=36).pack(padx=12, anchor="w")
        b = tk.Frame(self, bg=BG)
        b.pack(fill="x", padx=12, pady=14)
        ttk.Button(b, text="➕ Ajouter", style="Accent.TButton", command=lambda: self.do("add")).pack(side="left")
        ttk.Button(b, text="➖ Retirer", command=lambda: self.do("del")).pack(side="left", padx=6)
        ttk.Button(b, text="🗑 Supprimer la collection", command=lambda: self.do("drop")).pack(side="left")
        self.grab_set()
        self.wait_window()

    def do(self, what):
        n = self.name.get().strip()
        if not n:
            return
        cols = self.app.cfg["collections"]
        if what == "drop":
            if n in cols and messagebox.askyesno("Collection", f"Supprimer la collection « {n} » ?\n(les polices restent installées)", parent=self):
                del cols[n]
        else:
            s = set(cols.get(n, []))
            paths = {x.path for x in self.sel}
            s = s | paths if what == "add" else s - paths
            cols[n] = sorted(s)
        self.app.save_cfg()
        self.destroy()


class CompareWindow(Win):
    def __init__(self, app, fonts):
        super().__init__(app, "Comparer", "1000x560")
        self.fonts = fonts
        self.text = tk.StringVar(value=app.sample.get() or "Aa")
        self.size = tk.IntVar(value=max(app.size.get(), 32))
        bar = tk.Frame(self, bg=BAR, padx=10, pady=6)
        bar.pack(fill="x")
        ttk.Entry(bar, textvariable=self.text, width=50).pack(side="left")
        ttk.Scale(bar, from_=12, to=120, variable=self.size, length=160,
                  command=lambda v: self.size.set(int(float(v)))).pack(side="left", padx=10)
        self.lbl = tk.Label(self, bg=BG, anchor="nw")
        self.lbl.pack(fill="both", expand=True, padx=10, pady=10)
        for v in (self.text, self.size):
            v.trace_add("write", lambda *_: self.after_idle(self.draw))
        self.bind("<Configure>", lambda e: self.after_idle(self.draw))
        self.draw()

    def draw(self):
        W = max(self.winfo_width() - 20, 400)
        s, t = self.size.get(), self.text.get() or "Aa"
        rows = []
        for fi in self.fonts:
            im = Image.new("RGB", (W, int(s * 1.6) + 26), self.app.pbg())
            d = ImageDraw.Draw(im)
            d.text((0, 2), fi.name, fill=MUTED)
            try:
                d.text((0, 20), t, font=ImageFont.truetype(fi.path, s), fill=self.app.pfg())
            except Exception:
                pass
            rows.append(im)
        full = Image.new("RGB", (W, sum(r.height + 8 for r in rows)), BG)
        y = 0
        for r in rows:
            full.paste(r, (0, y))
            y += r.height + 8
        self._img = ImageTk.PhotoImage(full)
        self.lbl.config(image=self._img)


class QuickSort(Win):
    """← jeter · → garder · ↑ favori · Retour arrière = annuler."""

    def __init__(self, app, fonts):
        super().__init__(app, "Tri rapide", "1000x560")
        self.fonts, self.i, self.hist, self.trash = fonts, 0, [], []
        self.info = tk.Label(self, bg=BG, fg=MUTED, font=("Segoe UI", 11))
        self.info.pack(pady=(10, 0))
        self.title_l = tk.Label(self, bg=BG, fg=FG, font=("Segoe UI", 16, "bold"))
        self.title_l.pack()
        self.img = tk.Label(self, bg=BG)
        self.img.pack(fill="both", expand=True, padx=20)
        tk.Label(self, bg=BG, fg=MUTED, font=("Segoe UI", 11),
                 text="←  jeter      →  garder      ↑  favori      ⌫  annuler      Échap  terminer").pack(pady=10)
        self.bind("<Left>", lambda e: self.act("trash"))
        self.bind("<Right>", lambda e: self.act("keep"))
        self.bind("<Up>", lambda e: self.act("fav"))
        self.bind("<BackSpace>", lambda e: self.undo())
        self.bind("<Escape>", lambda e: self.finish())
        self.protocol("WM_DELETE_WINDOW", self.finish)
        self.focus_force()
        self.show()

    def show(self):
        if self.i >= len(self.fonts):
            return self.finish()
        fi = self.fonts[self.i]
        lock = "  🔒 protégée" if is_protected(fi.family, fi.user) else ""
        self.info.config(text=f"{self.i + 1} / {len(self.fonts)}  ·  {len(self.trash)} à jeter")
        self.title_l.config(text=fi.name + ("  ⭐" if self.app.is_fav(fi) else "") + lock)
        W = 940
        im = Image.new("RGB", (W, 380), self.app.pbg())
        d = ImageDraw.Draw(im)
        try:
            y = 0
            for s, t in ((72, "Aa Bb Cc 123"), (40, self.app.sample.get() or "Aa"), (22, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
                         (22, "abcdefghijklmnopqrstuvwxyz 0123456789 àéèç&@€")):
                d.text((0, y), t, font=ImageFont.truetype(fi.path, s), fill=self.app.pfg())
                y += int(s * 1.5)
        except Exception as e:
            d.text((0, 0), str(e), fill="#a00")
        self._img = ImageTk.PhotoImage(im)
        self.img.config(image=self._img)

    def act(self, what):
        if self.i >= len(self.fonts):
            return
        fi = self.fonts[self.i]
        self.hist.append((what, fi))
        if what == "trash":
            self.trash.append(fi)
        elif what == "fav" and not self.app.is_fav(fi):
            self.app.cfg["favorites"].append(fi.path)
        self.i += 1
        self.show()

    def undo(self):
        if not self.hist:
            return
        what, fi = self.hist.pop()
        if what == "trash":
            self.trash.remove(fi)
        elif what == "fav" and fi.path in self.app.cfg["favorites"]:
            self.app.cfg["favorites"].remove(fi.path)
        self.i -= 1
        self.show()

    def finish(self):
        self.app.save_cfg()
        trash = self.trash
        self.destroy()
        self.app.draw()
        if trash:
            self.app.uninstall_sel(trash)


class CharMap(Win):
    CELL, COLS, PER_PAGE = 52, 16, 16 * 10

    def __init__(self, app, fi):
        super().__init__(app, f"Caractères — {fi.name}", f"{16 * 52 + 30}x680")
        self.fi, self.chars, self.page = fi, font_chars(fi.path), 0
        bar = tk.Frame(self, bg=BAR, padx=10, pady=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="◀", width=3, command=lambda: self.go(-1)).pack(side="left")
        ttk.Button(bar, text="▶", width=3, command=lambda: self.go(1)).pack(side="left", padx=4)
        self.info = tk.Label(bar, bg=BAR, fg=FG)
        self.info.pack(side="left", padx=10)
        self.cv = tk.Canvas(self, bg=self.app.pbg(), highlightthickness=0)
        self.cv.pack(fill="both", expand=True, padx=10, pady=10)
        self.cv.bind("<Button-1>", self.click)
        self.bind("<MouseWheel>", lambda e: self.go(-1 if e.delta > 0 else 1))
        self.draw()

    def go(self, d):
        last = max(0, (len(self.chars) - 1) // self.PER_PAGE)
        self.page = max(0, min(last, self.page + d))
        self.draw()

    def draw(self):
        C = self.CELL
        part = self.chars[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]
        rows = max(1, (len(part) + self.COLS - 1) // self.COLS)
        im = Image.new("RGB", (self.COLS * C, rows * C), self.app.pbg())
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype(self.fi.path, 28)
        except Exception:
            font = None
        for k, cp in enumerate(part):
            x, y = (k % self.COLS) * C, (k // self.COLS) * C
            d.rectangle((x, y, x + C - 1, y + C - 1), outline=LINE)
            if font:
                d.text((x + C / 2, y + C / 2 - 4), chr(cp), font=font, fill=self.app.pfg(), anchor="mm")
            d.text((x + 3, y + C - 12), f"{cp:04X}", fill=MUTED)
        self._img = ImageTk.PhotoImage(im)
        self.cv.delete("all")
        self.cv.create_image(0, 0, anchor="nw", image=self._img)
        pages = max(1, (len(self.chars) + self.PER_PAGE - 1) // self.PER_PAGE)
        self.info.config(text=f"{len(self.chars)} caractères · page {self.page + 1}/{pages} · clic = copier")

    def click(self, e):
        k = self.page * self.PER_PAGE + (e.y // self.CELL) * self.COLS + e.x // self.CELL
        if e.x < self.COLS * self.CELL and 0 <= k < len(self.chars):
            ch = chr(self.chars[k])
            self.clipboard_clear()
            self.clipboard_append(ch)
            self.info.config(text=f"« {ch} » (U+{self.chars[k]:04X}) copié dans le presse-papiers")


class TrashDialog(Win):
    def __init__(self, app):
        super().__init__(app, "Corbeille", "560x420")
        tk.Label(self, text="Polices désinstallées. Restaurer = réinstaller pour vous.",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=12, pady=(10, 4))
        self.lb = tk.Listbox(self, selectmode="extended", bg=FIELD, fg=FG, selectbackground=ACC,
                             highlightthickness=0, borderwidth=0, font=("Segoe UI", 10))
        self.lb.pack(fill="both", expand=True, padx=12)
        b = tk.Frame(self, bg=BG)
        b.pack(fill="x", padx=12, pady=10)
        ttk.Button(b, text="♻ Restaurer", style="Accent.TButton", command=self.restore).pack(side="left")
        ttk.Button(b, text="Supprimer définitivement", command=self.purge).pack(side="left", padx=6)
        ttk.Button(b, text="Vider la corbeille", command=lambda: self.purge(all_=True)).pack(side="right")
        self.fill()

    def fill(self):
        self.idx = trash_index()
        self.keys = sorted(self.idx, reverse=True)
        self.lb.delete(0, "end")
        for k in self.keys:
            self.lb.insert("end", f"{self.idx[k]['name']}   —   {self.idx[k]['date']}")
        if not self.keys:
            self.lb.insert("end", "(corbeille vide)")

    def chosen(self):
        return [self.keys[i] for i in self.lb.curselection() if i < len(self.keys)]

    def restore(self):
        done = []
        for k in self.chosen():
            try:
                fi = restore_from_trash(k)
                if fi:
                    done.append(fi)
            except Exception as e:
                messagebox.showerror("Corbeille", f"{self.idx[k]['name']} : {e}", parent=self)
        if done:
            notify_font_change()
            self.app.fonts += done
            self.app.apply_filter()
        self.fill()

    def purge(self, all_=False):
        keys = self.keys if all_ else self.chosen()
        if keys and messagebox.askyesno("Corbeille", f"Supprimer définitivement {len(keys)} police(s) ?", parent=self):
            empty_trash(keys)
            self.fill()


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
        tk.Label(self, text=msg, bg=BG, fg=FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=10)
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
            cv.create_text(0, y, anchor="nw", text=fi.name, fill=MUTED, font=("Segoe UI", 9))
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
