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
