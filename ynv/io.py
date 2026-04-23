import json
import xml.etree.ElementTree as ET

from ..shared.xml_utils import sub_val, to_xml_string


def _parse_flags_str(flags_str):
    """Convert raw flag string to 7 bytes: b0..b6.

    CodeWalker accepts 7 bytes for YNV polygon flags.
    """
    try:
        parts = [int(x) for x in flags_str.split()]
        while len(parts) < 7:
            parts.append(0)
        return parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
    except Exception:
        return 0, 0, 0, 0, 0, 0, 0


def _parse_vertex_line(line):
    parts = line.strip().split(",")
    return tuple(float(p.strip()) for p in parts if p.strip())


def _parse_ynv_xml(filepath, props):
    props.portals.clear()
    props.nav_points.clear()
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e), []
    root = tree.getroot()
    if root.tag != "NavMesh":
        return False, f"Expected NavMesh root, found {root.tag}", []

    cf = root.find("ContentFlags")
    props.content_flags = (cf.text or "").strip() if cf is not None else "Polygons, Portals"
    aid = root.find("AreaID")
    props.area_id = int(aid.get("value", 0)) if aid is not None else 0

    for tag, attr in [("BBMin", "bb_min"), ("BBMax", "bb_max")]:
        el = root.find(tag)
        if el is not None:
            setattr(props, attr, (float(el.get("x", 0)), float(el.get("y", 0)), float(el.get("z", 0))))

    polygons_data = []
    polys_el = root.find("Polygons")
    if polys_el is not None:
        for item in polys_el.findall("Item"):
            flags_el = item.find("Flags")
            flags_str = (flags_el.text or "0 0 0 0 0 0").strip() if flags_el is not None else "0 0 0 0 0 0"
            verts_el = item.find("Vertices")
            verts = []
            if verts_el is not None and verts_el.text:
                for line in verts_el.text.strip().split("\n"):
                    if line.strip():
                        parsed = _parse_vertex_line(line)
                        if len(parsed) == 3:
                            verts.append(parsed)
            edges_el = item.find("Edges")
            edges_raw = []
            if edges_el is not None and edges_el.text:
                for line in edges_el.text.strip().split("\n"):
                    if line.strip():
                        edges_raw.append(line.strip())
            edges_flags_el = item.find("EdgesFlags")
            edges_flags_raw = []
            if edges_flags_el is not None and edges_flags_el.text:
                for line in edges_flags_el.text.strip().split("\n"):
                    if line.strip():
                        edges_flags_raw.append(line.strip())

            portals_poly_el = item.find("Portals")
            portals_poly_raw = []
            if portals_poly_el is not None and portals_poly_el.text:
                for tok in portals_poly_el.text.replace("\n", " ").replace(",", " ").split():
                    try:
                        portals_poly_raw.append(int(tok))
                    except ValueError:
                        pass

            polygons_data.append(
                {
                    "flags": flags_str,
                    "verts": verts,
                    "edges": edges_raw,
                    "edges_flags": edges_flags_raw,
                    "poly_portals": portals_poly_raw,
                }
            )

    portals_el = root.find("Portals")
    if portals_el is not None:
        for item in portals_el.findall("Item"):
            p = props.portals.add()
            t = item.find("Type")
            p.portal_type = int(t.get("value", 1)) if t is not None else 1
            a = item.find("Angle")
            p.angle = float(a.get("value", 0)) if a is not None else 0.0
            pf_el = item.find("PolyFrom")
            p.poly_from = int(pf_el.get("value", 0)) if pf_el is not None else 0
            pt_el = item.find("PolyTo")
            p.poly_to = int(pt_el.get("value", 0)) if pt_el is not None else 0
            pfrom = item.find("PositionFrom")
            if pfrom is not None:
                p.pos_from = (float(pfrom.get("x", 0)), float(pfrom.get("y", 0)), float(pfrom.get("z", 0)))
            pto = item.find("PositionTo")
            if pto is not None:
                p.pos_to = (float(pto.get("x", 0)), float(pto.get("y", 0)), float(pto.get("z", 0)))

    points_el = root.find("Points")
    if points_el is not None:
        for item in points_el.findall("Item"):
            np = props.nav_points.add()
            t = item.find("Type")
            np.point_type = int(t.get("value", 0)) if t is not None else 0
            a = item.find("Angle")
            np.angle = float(a.get("value", 0)) if a is not None else 0.0
            pos = item.find("Position")
            if pos is not None:
                np.position = (float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0)))

    props.stat_polygons = len(polygons_data)
    props.stat_portals = len(props.portals)
    props.stat_navpoints = len(props.nav_points)
    return True, "OK", polygons_data


def _edge_lines_valid_for_poly(edge_list, poly, vert_count):
    """Check if cached edge lines are structurally valid for this polygon."""
    if not isinstance(edge_list, list):
        return False
    if len(edge_list) != poly.loop_total:
        return False

    for line in edge_list:
        if not isinstance(line, str) or ":" not in line or "," not in line:
            return False
        try:
            left, right = line.split(",", 1)
            _, a = left.strip().split(":", 1)
            _, b = right.strip().split(":", 1)
            ia = int(a.strip())
            ib = int(b.strip())
        except Exception:
            return False
        if ia < 0 or ib < 0 or ia >= vert_count or ib >= vert_count:
            return False

    return True


def _edge_flag_lines_valid_for_poly(edge_flags_list, expected_count):
    """Check cached EdgesFlags block validity for one polygon."""
    if not isinstance(edge_flags_list, list):
        return False
    if len(edge_flags_list) != expected_count:
        return False

    for line in edge_flags_list:
        if not isinstance(line, str) or ":" not in line or "," not in line:
            return False
        try:
            left, right = line.split(",", 1)
            a0, a1 = left.strip().split(":", 1)
            b0, b1 = right.strip().split(":", 1)
            int(a0.strip())
            int(a1.strip())
            int(b0.strip())
            int(b1.strip())
        except Exception:
            return False
    return True


def _poly_portal_links_valid(portal_links, portal_count):
    """Check per-poly portal link list values are within portal index bounds."""
    if not isinstance(portal_links, list):
        return False
    for x in portal_links:
        try:
            v = int(x)
        except Exception:
            return False
        if v < 0 or v >= portal_count:
            return False
    return True


def _normalize_poly_portal_links(poly_portal_links, poly_count):
    """Align per-face portal link cache length with polygon count."""
    if not isinstance(poly_portal_links, list):
        poly_portal_links = []

    normalized = []
    for entry in poly_portal_links:
        normalized.append(entry if isinstance(entry, list) else [])

    if len(normalized) < poly_count:
        normalized.extend([[] for _ in range(poly_count - len(normalized))])
    elif len(normalized) > poly_count:
        normalized = normalized[:poly_count]

    return normalized


def _sanitize_portals_for_poly_count(props, poly_count):
    """Keep only portals that reference existing polygon indices.

    Returns number of removed portals.
    """
    if poly_count < 0:
        poly_count = 0

    keep = []
    for p in props.portals:
        pf = int(p.poly_from)
        pt = int(p.poly_to)
        if 0 <= pf < poly_count and 0 <= pt < poly_count:
            keep.append(
                {
                    "portal_type": int(p.portal_type),
                    "angle": float(p.angle),
                    "poly_from": pf,
                    "poly_to": pt,
                    "pos_from": tuple(p.pos_from),
                    "pos_to": tuple(p.pos_to),
                }
            )

    removed = len(props.portals) - len(keep)
    if removed <= 0:
        return 0

    props.portals.clear()
    for entry in keep:
        p = props.portals.add()
        p.portal_type = entry["portal_type"]
        p.angle = entry["angle"]
        p.poly_from = entry["poly_from"]
        p.poly_to = entry["poly_to"]
        p.pos_from = entry["pos_from"]
        p.pos_to = entry["pos_to"]

    props.portal_index = min(props.portal_index, len(props.portals) - 1)
    props.stat_portals = len(props.portals)
    return removed


def _build_ynv_xml(context, props):
    # Local import to avoid circular dependency between builders and io modules.
    from .builders import _sync_navpoints_from_objects

    _sync_navpoints_from_objects(context, props, keep_props_if_no_objects=True)

    root = ET.Element("NavMesh")
    cf = ET.SubElement(root, "ContentFlags")
    cf.text = props.content_flags
    sub_val(root, "AreaID", props.area_id)
    for tag, v in [("BBMin", props.bb_min), ("BBMax", props.bb_max)]:
        el = ET.SubElement(root, tag)
        el.set("x", str(int(v[0])))
        el.set("y", str(int(v[1])))
        el.set("z", f"{v[2]:.7g}")
    bb_size = ET.SubElement(root, "BBSize")
    bb_size.set("x", f"{props.bb_max[0] - props.bb_min[0]:.7g}")
    bb_size.set("y", f"{props.bb_max[1] - props.bb_min[1]:.7g}")
    bb_size.set("z", f"{props.bb_max[2] - props.bb_min[2]:.7g}")

    polys_el = ET.SubElement(root, "Polygons")
    poly_obj = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
    poly_count = 0
    if poly_obj and poly_obj.type == "MESH":
        mesh = poly_obj.data
        poly_count = len(mesh.polygons)
        removed_portals = _sanitize_portals_for_poly_count(props, poly_count)
        if removed_portals:
            print(f"[YNV] Removed {removed_portals} invalid portal(s) during export (poly index out of range)")

        try:
            b456_data = json.loads(poly_obj.get("ynv_bytes456", "[]"))
        except Exception:
            b456_data = []
        if not isinstance(b456_data, list):
            b456_data = []

        if not b456_data:
            try:
                b45_data = json.loads(poly_obj.get("ynv_bytes45", "[]"))
            except Exception:
                b45_data = []
            if isinstance(b45_data, list):
                b456_data = []
                for pair in b45_data:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        b456_data.append([int(pair[0]), int(pair[1]), 0])
                    else:
                        b456_data.append([0, 0, 0])

        try:
            edge_lines = json.loads(poly_obj.get("ynv_edge_lines", "[]"))
        except Exception:
            edge_lines = []
        if not isinstance(edge_lines, list):
            edge_lines = []

        try:
            edge_flag_lines = json.loads(poly_obj.get("ynv_edge_flag_lines", "[]"))
        except Exception:
            edge_flag_lines = []
        if not isinstance(edge_flag_lines, list):
            edge_flag_lines = []

        try:
            poly_portal_links = json.loads(poly_obj.get("ynv_poly_portals", "[]"))
        except Exception:
            poly_portal_links = []

        poly_portal_links = _normalize_poly_portal_links(poly_portal_links, poly_count)

        if len(edge_lines) != poly_count:
            edge_lines = []
        if len(edge_flag_lines) != poly_count:
            edge_flag_lines = []

        if len(b456_data) < poly_count:
            b456_data.extend([[0, 0, 0] for _ in range(poly_count - len(b456_data))])
        elif len(b456_data) > poly_count:
            b456_data = b456_data[:poly_count]

        for i, poly in enumerate(mesh.polygons):
            mi = poly.material_index
            mat = mesh.materials[mi] if mi < len(mesh.materials) else None
            if mat and "ynv_b0" in mat:
                b0, b1, b2, b3 = mat["ynv_b0"], mat["ynv_b1"], mat["ynv_b2"], mat["ynv_b3"]
            else:
                b0, b1, b2, b3 = 0, 0, 0, 0
            if i < len(b456_data):
                triplet = b456_data[i]
                if isinstance(triplet, (list, tuple)) and len(triplet) >= 3:
                    b4, b5, b6 = int(triplet[0]), int(triplet[1]), int(triplet[2])
                elif isinstance(triplet, (list, tuple)) and len(triplet) >= 2:
                    b4, b5, b6 = int(triplet[0]), int(triplet[1]), 0
                else:
                    b4, b5, b6 = 0, 0, 0
            else:
                b4, b5, b6 = 0, 0, 0

            item = ET.SubElement(polys_el, "Item")
            flags_el = ET.SubElement(item, "Flags")
            flags_el.text = f"{b0} {b1} {b2} {b3} {b4} {b5} {b6}"

            verts_el = ET.SubElement(item, "Vertices")
            vert_lines = []
            for vi in poly.vertices:
                v = mesh.vertices[vi].co
                vert_lines.append(f"    {v.x:.7g}, {v.y:.7g}, {v.z:.7g}")
            verts_el.text = "\n" + "\n".join(vert_lines) + "\n   "

            edges_el = ET.SubElement(item, "Edges")
            if i < len(edge_lines) and _edge_lines_valid_for_poly(edge_lines[i], poly, len(mesh.vertices)):
                final_edges = edge_lines[i]
            else:
                final_edges = ["16383:16383, 16383:16383" for _ in range(poly.loop_total)]
            edges_el.text = "\n" + "\n".join([f"    {ln}" for ln in final_edges]) + "\n   "

            edges_flags_el = ET.SubElement(item, "EdgesFlags")
            if i < len(edge_flag_lines) and _edge_flag_lines_valid_for_poly(edge_flag_lines[i], len(final_edges)):
                final_edge_flags = edge_flag_lines[i]
            else:
                final_edge_flags = ["0:0, 0:0" for _ in range(len(final_edges))]
            edges_flags_el.text = "\n" + "\n".join([f"    {ln}" for ln in final_edge_flags]) + "\n   "

            if i < len(poly_portal_links):
                links = []
                for raw in poly_portal_links[i]:
                    try:
                        idx = int(raw)
                    except Exception:
                        continue
                    if 0 <= idx < len(props.portals):
                        links.append(str(idx))
                if links:
                    p_el = ET.SubElement(item, "Portals")
                    p_el.text = "\n" + "\n".join([f"    {v}" for v in links]) + "\n   "

    portals_el = ET.SubElement(root, "Portals")
    for portal in props.portals:
        item = ET.SubElement(portals_el, "Item")
        sub_val(item, "Type", portal.portal_type)
        sub_val(item, "Angle", f"{portal.angle:.7g}")
        sub_val(item, "PolyFrom", portal.poly_from)
        sub_val(item, "PolyTo", portal.poly_to)
        for tag, pos in [("PositionFrom", portal.pos_from), ("PositionTo", portal.pos_to)]:
            el = ET.SubElement(item, tag)
            el.set("x", f"{pos[0]:.7g}")
            el.set("y", f"{pos[1]:.7g}")
            el.set("z", f"{pos[2]:.7g}")

    points_el = ET.SubElement(root, "Points")
    for np_item in props.nav_points:
        item = ET.SubElement(points_el, "Item")
        sub_val(item, "Type", np_item.point_type)
        sub_val(item, "Angle", f"{np_item.angle:.7g}")
        pos_el = ET.SubElement(item, "Position")
        pos_el.set("x", f"{np_item.position[0]:.7g}")
        pos_el.set("y", f"{np_item.position[1]:.7g}")
        pos_el.set("z", f"{np_item.position[2]:.7g}")

    return to_xml_string(root)
