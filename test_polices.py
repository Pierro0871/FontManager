"""Petit auto-test sans interface : python test_polices.py"""
import polices as p

assert p.parse_version("v1.12") == (1, 12)
assert p.parse_version("dev") is None
assert p.parse_version("1.10") > p.parse_version("1.9")

a = p.FontInfo("a.ttf", "Arial", "Bold", True)
b = p.FontInfo("b.ttf", "arial", "bold", False)
c = p.FontInfo("c.ttf", "Arial", "Regular", False)
assert p.find_duplicates([a, b, c]) == {"a.ttf", "b.ttf"}

for name in p.THEMES:
    p.set_theme(name)
    assert p.BG == p.THEMES[name]["BG"]
print("ok")

# styles
assert "Script" in p.classify("Great Vibes", "Regular", panose_family=3)
assert p.classify("Roboto", "Bold", panose_serif=11, weight=700) == {"Sans", "Gras"}
assert "Mono" in p.classify("Fira Code", "Regular")
assert "Italique" in p.classify("Georgia", "Italic", panose_serif=2)

# licences
assert p.commercial_status("Licensed under the SIL Open Font License").startswith("✅")
assert p.commercial_status("Free for personal use only").startswith("⚠")
assert p.commercial_status("").startswith("❓")

# protection
assert p.is_protected("Segoe UI", user=False)
assert not p.is_protected("Segoe UI", user=True)
assert not p.is_protected("Great Vibes", user=False)

# corbeille : jeter puis restaurer
import os, shutil, tempfile
tmp = tempfile.mkdtemp()
p.TRASH, p.USER_FONTS = os.path.join(tmp, "corbeille"), os.path.join(tmp, "fonts")
src = os.path.join(tmp, "x.ttf")
open(src, "wb").write(b"fake")
p.move_to_trash(p.FontInfo(src, "X", "Regular", True))
assert not os.path.exists(src)
(key,) = p.trash_index()
p.restore_from_trash(key)
assert os.listdir(p.USER_FONTS) and not p.trash_index()
shutil.rmtree(tmp)
print("ok tout")
