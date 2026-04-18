"""xmlio.py — Utilitaires XML partagés (lecture typée + écriture propre)."""
import xml.etree.ElementTree as ET


# ── Lecture ───────────────────────────────────────────────────────────────────

def geti(el, tag, default=0) -> int:
    c = el.find(tag)
    if c is None: return default
    try:    return int(c.get("value", default))
    except: return default

def getf(el, tag, default=0.0) -> float:
    c = el.find(tag)
    if c is None: return default
    try:    return float(c.get("value", default))
    except: return default

def gets(el, tag, default="") -> str:
    c = el.find(tag)
    if c is None: return default
    v = c.get("value")
    return v if v is not None else (c.text or default).strip()

def getb(el, tag, default=False) -> bool:
    return gets(el, tag, "true" if default else "false").lower() in ("true","1","yes")

def get_xyz(el, tag):
    c = el.find(tag)
    if c is None: return (0.0, 0.0, 0.0)
    return (float(c.get("x",0)), float(c.get("y",0)), float(c.get("z",0)))

def get_xyzw(el, tag):
    c = el.find(tag)
    if c is None: return (0.0, 0.0, 0.0, 0.0)
    return (float(c.get("x",0)), float(c.get("y",0)), float(c.get("z",0)), float(c.get("w",0)))


# ── Écriture ──────────────────────────────────────────────────────────────────

def seti(parent, tag, value) -> ET.Element:
    el = ET.SubElement(parent, tag); el.set("value", str(int(value))); return el

def setf(parent, tag, value, p=7) -> ET.Element:
    el = ET.SubElement(parent, tag); el.set("value", f"{float(value):.{p}g}"); return el

def sets_el(parent, tag, text) -> ET.Element:
    el = ET.SubElement(parent, tag); el.text = str(text); return el

def setb_el(parent, tag, value) -> ET.Element:
    el = ET.SubElement(parent, tag); el.set("value", "true" if value else "false"); return el

def set_xyz_el(parent, tag, x, y, z, p=7) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.set("x", f"{x:.{p}g}"); el.set("y", f"{y:.{p}g}"); el.set("z", f"{z:.{p}g}")
    return el

def set_xyzw_el(parent, tag, x, y, z, w, p=7) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.set("x",f"{x:.{p}g}"); el.set("y",f"{y:.{p}g}")
    el.set("z",f"{z:.{p}g}"); el.set("w",f"{w:.{p}g}")
    return el

def to_xml_string(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
