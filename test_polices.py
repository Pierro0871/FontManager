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

# familles : regroupement, dépliage, la famille suit
r = p.FontInfo("r.ttf", "Roboto", "Regular", True)
rb = p.FontInfo("rb.ttf", "Roboto", "Bold", True)
ri = p.FontInfo("ri.ttf", "Roboto", "Italic", True)
lo = p.FontInfo("lo.ttf", "Lobster", "Regular", True)
rows = p.build_rows([rb, r, ri, lo], set())
assert [x.key for x in rows] == ["F:roboto", "lo.ttf"] and rows[0].rep is r
rows = p.build_rows([rb, r, ri, lo], {"F:roboto"})
assert [x.key for x in rows] == ["F:roboto", "rb.ttf", "r.ttf", "ri.ttf", "lo.ttf"] and rows[1].child
assert p.family_paths([r, rb, ri, lo], [rb]) == {"r.ttf", "rb.ttf", "ri.ttf"}

# couleurs
assert p.blend("#000000", "#ffffff", 0.5) == "#808080"
assert p.text_on("#ffffff") == "#111111" and p.text_on("#6e56cf") == "#ffffff"
print("ok familles")

# droits façon DaFont
rc = p.rights_category
assert rc("This font is licensed under the SIL Open Font License") == "Libre (OFL, Apache…)"
assert rc("Free for personal use only. Contact me for commercial license") == "Usage personnel"
assert rc("DEMO version - buy the full font") == "Démo"
assert rc("This font is donationware, paypal me") == "Donationware"
assert rc("Released into the public domain") == "Domaine public"
assert rc("© Microsoft Corporation", user=False) == "Fournie par Windows"
assert rc("© Microsoft Corporation", user=True) == "Inconnue"
assert rc("") == "Inconnue"
assert all(r in p.RIGHTS_ORDER for r in ("Démo", "Inconnue"))
print("ok droits")

# sites de polices (sans réseau)
cat = p.catalog_entries(
    [{"family": "Roboto", "id": "roboto", "category": "sans-serif", "license": "OFL-1.1", "type": "google"},
     {"family": "Free Thing", "id": "ft", "license": "CC0-1.0", "type": "other"}],
    [{"family_name": "Roboto", "family_urlname": "roboto", "classification": "Sans Serif"},
     {"family_name": "Lobster Two", "family_urlname": "lobster-two", "classification": "Script"}])
idx = p.web_lookup(cat)
assert idx["roboto"]["site"] == "Google Fonts"  # Google passe avant Squirrel
assert idx["freething"]["rights"] == "Domaine public" and idx["freething"]["site"] == "Fontsource"
assert idx[p.norm("Lobster-Two")]["rights"] == "100% gratuite"
print("ok web")

# langues
fr = [ord(c) for c in p.LANGS["Français"]] + list(range(32, 127))
assert "Français" in p.langs_of(fr) and "Cyrillique" not in p.langs_of(fr)
assert "Français" not in p.langs_of(range(32, 127))

# polices d'un document (docx minimal) et correspondance
import zipfile as _z
tmp = tempfile.mkdtemp()
docx = os.path.join(tmp, "a.docx")
with _z.ZipFile(docx, "w") as z:
    z.writestr("word/fontTable.xml", '<w:fonts><w:font w:name="Roboto"/><w:font w:name="Lobster Two"/></w:fonts>')
    z.writestr("word/document.xml", '<w:rFonts w:ascii="Roboto" w:hAnsi="Roboto"/>')
assert p.doc_font_names(docx) == ["Lobster Two", "Roboto"]
html = os.path.join(tmp, "a.css")
open(html, "w").write("h1 { font-family: 'Pacifico', cursive; }")
assert p.doc_font_names(html) == ["Pacifico"]
rob, rbb = p.FontInfo("r.ttf", "Roboto", "Regular", True), p.FontInfo("rc.ttf", "Roboto Condensed", "Regular", True)
assert p.match_installed("ABCDEF+Roboto-BoldItalic".split("+")[1], [rob, rbb]) is rob
assert p.match_installed("RobotoCondensed-Bold", [rob, rbb]) is rbb
assert p.match_installed("Lobster Two", [rob]) is None

# fichier cassé
bad = os.path.join(tmp, "bad.ttf")
open(bad, "wb").write(b"x" * 10)
assert p.broken_reason(bad)

# paires : un serif propose des sans complets
t = p.FontInfo("t.ttf", "Playfair", "Regular", True); t.tags = {"Serif"}
s1 = [p.FontInfo(f"s{i}.ttf", "Inter", st, True) for i, st in enumerate(("Regular", "Bold", "Italic"))]
for x in s1: x.tags = {"Sans"}
sc = p.FontInfo("sc.ttf", "Great Vibes", "Regular", True); sc.tags = {"Script"}
assert [x.family for x in p.pair_candidates(t, [t] + s1 + [sc])] == ["Inter"]
shutil.rmtree(tmp)
print("ok v1.12")
