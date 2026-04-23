import os
from mathutils import Vector


def _parse_trains_dat(filepath, props):
    """Parses trains*.dat and fills the point collection."""
    props.points.clear()

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except OSError as e:
        return False, f"Read error: {e}"

    if not lines:
        return False, "Empty file."

    try:
        expected = int(lines[0])
    except ValueError:
        return False, f"Invalid line 1 (expected integer): '{lines[0]}'"

    data_lines = lines[1:]
    count = 0
    junctions = 0

    for line in data_lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
            z = float(parts[2])
            flag = int(parts[3]) if len(parts) >= 4 else 0
        except ValueError:
            continue

        pt = props.points.add()
        pt.position = (x, y, z)
        pt.flag = flag
        count += 1
        if flag == 4:
            junctions += 1

    props.stat_points = count
    props.stat_junctions = junctions
    props.track_name = os.path.splitext(os.path.basename(filepath))[0]
    return True, "OK"


def _build_trains_dat(context, props) -> str:
    """Rebuilds the .dat file from Blender data."""
    curve_obj = next((o for o in context.scene.objects if o.get("trains_type") == "track_curve"), None)

    if curve_obj and curve_obj.type == "CURVE":
        props.points.clear()
        curve = curve_obj.data
        for spline in curve.splines:
            if spline.type == "POLY":
                for pt in spline.points:
                    item = props.points.add()
                    item.position = tuple(curve_obj.matrix_world @ Vector(pt.co[:3]))
                    item.flag = int(pt.radius) if pt.radius in (0, 1, 4, 5) else 0
            elif spline.type == "BEZIER":
                for pt in spline.bezier_points:
                    item = props.points.add()
                    item.position = tuple(curve_obj.matrix_world @ Vector(pt.co))
                    item.flag = 0

    n = len(props.points)
    lines = [str(n)]
    for pt in props.points:
        x, y, z = pt.position
        lines.append(f"{x:.3f} {y:.3f} {z:.3f} {pt.flag}")
    return "\r\n".join(lines) + "\r\n"
