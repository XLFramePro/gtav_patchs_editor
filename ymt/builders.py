import bpy


def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _link_obj(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def _build_ymt_objects(props, col, itype_names):
    root_obj = bpy.data.objects.new("YMT_Root", None)
    root_obj.empty_display_type = "PLAIN_AXES"
    root_obj.empty_display_size = 1.0
    root_obj["ymt_type"] = "root"
    _link_obj(root_obj, col)

    sp_root = bpy.data.objects.new("YMT_ScenarioPoints", None)
    sp_root.empty_display_type = "PLAIN_AXES"
    sp_root.empty_display_size = 0.1
    sp_root.parent = root_obj
    _link_obj(sp_root, col)

    for i, sp in enumerate(props.scenario_points):
        name = itype_names.get(sp.itype, f"type{sp.itype}")
        obj = bpy.data.objects.new(f"YMT_SP_{i}_{name}", None)
        obj.empty_display_type = "SINGLE_ARROW"
        obj.empty_display_size = 1.0
        obj.location = (sp.position[0], sp.position[1], sp.position[2])
        obj.rotation_euler = (0, 0, sp.position[3])
        obj["ymt_type"] = "scenario_point"
        obj["sp_index"] = i
        obj["itype"] = sp.itype
        obj["flags"] = sp.flags
        obj["time_start"] = sp.time_start
        obj["time_end"] = sp.time_end
        obj["model_set_id"] = sp.model_set_id
        obj["probability"] = sp.probability
        obj.parent = sp_root
        _link_obj(obj, col)

    cn_root = bpy.data.objects.new("YMT_ChainingNodes", None)
    cn_root.empty_display_type = "PLAIN_AXES"
    cn_root.empty_display_size = 0.1
    cn_root.parent = root_obj
    _link_obj(cn_root, col)

    for i, cn in enumerate(props.chaining_nodes):
        obj = bpy.data.objects.new(f"YMT_CNode_{i}_{cn.scenario_type}", None)
        obj.empty_display_type = "CIRCLE"
        obj.empty_display_size = 0.5
        obj.location = cn.position
        obj["ymt_type"] = "chaining_node"
        obj["cn_index"] = i
        obj["scenario_type"] = cn.scenario_type
        obj.parent = cn_root
        _link_obj(obj, col)

    return root_obj
