"""
xml_utils.py — Shared XML utilities.
Reading and writing GTA V formats: YNV, YND, YMT.
"""

import xml.etree.ElementTree as ET
from mathutils import Vector


# ─────────────────────────────────────────────────────────────────────────────
#  READING
# ─────────────────────────────────────────────────────────────────────────────

def fval(elem, tag, default=0.0):
    """Read the float value from a sub-element <tag value="..."/>."""
    child = elem.find(tag)
    if child is None:
        return default
    try:
        return float(child.get("value", default))
    except (ValueError, TypeError):
        return default


def ival(elem, tag, default=0):
    """Read the int value from a sub-element."""
    child = elem.find(tag)
    if child is None:
        return default
    try:
        return int(child.get("value", default))
    except (ValueError, TypeError):
        return default


def sval(elem, tag, default=""):
    """Read the text value from a sub-element (attribute value or text)."""
    child = elem.find(tag)
    if child is None:
        return default
    v = child.get("value")
    if v is not None:
        return v
    return (child.text or default).strip()


def bval(elem, tag, default=False):
    """Read the boolean value from a sub-element."""
    v = sval(elem, tag, "false" if not default else "true")
    return v.lower() == "true"


def vec3(elem, tag, default=(0.0, 0.0, 0.0)):
    """Read an XYZ vector from <tag x="..." y="..." z="..."/>."""
    child = elem.find(tag)
    if child is None:
        return default
    try:
        return (
            float(child.get("x", 0)),
            float(child.get("y", 0)),
            float(child.get("z", 0)),
        )
    except (ValueError, TypeError):
        return default


def vec4(elem, tag, default=(0.0, 0.0, 0.0, 0.0)):
    """Read an XYZW vector from <tag x="..." y="..." z="..." w="..."/>."""
    child = elem.find(tag)
    if child is None:
        return default
    try:
        return (
            float(child.get("x", 0)),
            float(child.get("y", 0)),
            float(child.get("z", 0)),
            float(child.get("w", 0)),
        )
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
#  WRITING
# ─────────────────────────────────────────────────────────────────────────────

def sub_val(parent, tag, value):
    """Create <tag value="value"/> under parent."""
    el = ET.SubElement(parent, tag)
    el.set("value", str(value))
    return el


def sub_text(parent, tag, text):
    """Create <tag>text</tag> under parent."""
    el = ET.SubElement(parent, tag)
    el.text = str(text)
    return el


def sub_vec3(parent, tag, x, y, z):
    """Create <tag x="x" y="y" z="z"/> under parent."""
    el = ET.SubElement(parent, tag)
    el.set("x", f"{x:.7g}")
    el.set("y", f"{y:.7g}")
    el.set("z", f"{z:.7g}")
    return el


def sub_vec4(parent, tag, x, y, z, w):
    """Create <tag x="x" y="y" z="z" w="w"/> under parent."""
    el = ET.SubElement(parent, tag)
    el.set("x", f"{x:.7g}")
    el.set("y", f"{y:.7g}")
    el.set("z", f"{z:.7g}")
    el.set("w", f"{w:.7g}")
    return el


def to_xml_string(root) -> str:
    """Serialize an ElementTree to a formatted XML string."""
    ET.indent(root, space=" ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
