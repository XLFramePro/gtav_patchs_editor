"""
properties.py — Complete PropertyGroups for GTA V Pathing Editor.
YND flags are exactly matched to the provided reference (properties.py from ynd folder).
"""
import bpy
from bpy.props import (
    StringProperty, FloatProperty, IntProperty,
    BoolProperty, EnumProperty, PointerProperty,
    CollectionProperty, FloatVectorProperty,
)
from bpy.types import PropertyGroup


# ─────────────────────────────────────────────────────────────────────────────
#  YND — SPEED & SPECIAL TYPES (from reference)
# ─────────────────────────────────────────────────────────────────────────────

SPEED_ITEMS = [
    ("SLOW",   "Slow",   "", 0),
    ("NORMAL", "Normal", "", 1),
    ("FAST",   "Fast",   "", 2),
    ("FASTER", "Faster", "", 3),
]

SPECIAL_TYPE_ITEMS = [
    ("NONE",         "None",                          "0",  0),
    ("PARKING",      "Parking Space",                 "2",  1),
    ("PED_CROSSING", "PedNode Road Crossing",         "10", 2),
    ("PED_ASSISTED", "PedNode Assisted Movement",     "14", 3),
    ("TRAFFIC_LIGHT","Traffic Light Junction Stop",   "15", 4),
    ("STOP_SIGN",    "Stop Sign",                     "16", 5),
    ("CAUTION",      "Caution",                       "17", 6),
    ("PED_NOWAIT",   "PedRoad Crossing NoWait",       "18", 7),
    ("EMERGENCY",    "Emergency Vehicles Only",       "19", 8),
    ("OFFROAD_JCT",  "Offroad Junction",              "20", 9),
]

PED_SPECIAL_TYPES = {"PED_CROSSING", "PED_ASSISTED", "PED_NOWAIT"}


# ─────────────────────────────────────────────────────────────────────────────
#  YND NODE FLAGS (from reference yndref/properties.py)
# ─────────────────────────────────────────────────────────────────────────────

class YND_NodeFlags0(PropertyGroup):
    scripted:         BoolProperty(name="Scripted")
    gps_enabled:      BoolProperty(name="GPS Enabled")
    unused_4:         BoolProperty(name="Unused 4")
    offroad:          BoolProperty(name="Offroad")
    unused_16:        BoolProperty(name="Unused 16")
    no_big_vehicles:  BoolProperty(name="No Big Vehicles")
    cannot_go_right:  BoolProperty(name="Cannot Go Right")
    cannot_go_left:   BoolProperty(name="Cannot Go Left")

    def to_int(self):
        return (self.scripted        << 0) | (self.gps_enabled    << 1) |                (self.unused_4        << 2) | (self.offroad         << 3) |                (self.unused_16       << 4) | (self.no_big_vehicles << 5) |                (self.cannot_go_right << 6) | (self.cannot_go_left  << 7)

    def from_int(self, v):
        self.scripted       = bool(v & 1)
        self.gps_enabled    = bool(v & 2)
        self.unused_4       = bool(v & 4)
        self.offroad        = bool(v & 8)
        self.unused_16      = bool(v & 16)
        self.no_big_vehicles= bool(v & 32)
        self.cannot_go_right= bool(v & 64)
        self.cannot_go_left = bool(v & 128)


class YND_NodeFlags1(PropertyGroup):
    slip_lane:           BoolProperty(name="Slip Lane")
    indicate_keep_left:  BoolProperty(name="Indicate Keep Left")
    indicate_keep_right: BoolProperty(name="Indicate Keep Right")
    special_type:        EnumProperty(items=SPECIAL_TYPE_ITEMS, name="Special Type", default="NONE")

    def to_int(self):
        spec_map = {"NONE":0,"PARKING":2,"PED_CROSSING":10,"PED_ASSISTED":14,
                    "TRAFFIC_LIGHT":15,"STOP_SIGN":16,"CAUTION":17,"PED_NOWAIT":18,
                    "EMERGENCY":19,"OFFROAD_JCT":20}
        return (self.slip_lane           << 0) |                (self.indicate_keep_left  << 1) |                (self.indicate_keep_right << 2) |                (spec_map.get(self.special_type, 0) << 3)

    def from_int(self, v):
        self.slip_lane           = bool(v & 1)
        self.indicate_keep_left  = bool(v & 2)
        self.indicate_keep_right = bool(v & 4)
        spec_raw = v >> 3
        spec_map_r = {0:"NONE",2:"PARKING",10:"PED_CROSSING",14:"PED_ASSISTED",
                      15:"TRAFFIC_LIGHT",16:"STOP_SIGN",17:"CAUTION",18:"PED_NOWAIT",
                      19:"EMERGENCY",20:"OFFROAD_JCT"}
        self.special_type = spec_map_r.get(spec_raw, "NONE")


class YND_NodeFlags2(PropertyGroup):
    no_gps:      BoolProperty(name="No GPS")
    unused_2:    BoolProperty(name="Unused 2")
    junction:    BoolProperty(name="Junction")
    unused_8:    BoolProperty(name="Unused 8")
    disabled_1:  BoolProperty(name="Disabled 1")
    water_boats: BoolProperty(name="Water/Boats")
    freeway:     BoolProperty(name="Freeway")
    disabled_2:  BoolProperty(name="Disabled 2")

    def to_int(self):
        return (self.no_gps      << 0) | (self.unused_2   << 1) |                (self.junction    << 2) | (self.unused_8    << 3) |                (self.disabled_1  << 4) | (self.water_boats << 5) |                (self.freeway     << 6) | (self.disabled_2  << 7)

    def from_int(self, v):
        self.no_gps      = bool(v & 1);   self.unused_2   = bool(v & 2)
        self.junction    = bool(v & 4);   self.unused_8   = bool(v & 8)
        self.disabled_1  = bool(v & 16);  self.water_boats= bool(v & 32)
        self.freeway     = bool(v & 64);  self.disabled_2 = bool(v & 128)


class YND_NodeFlags3(PropertyGroup):
    tunnel:    BoolProperty(name="Tunnel")
    heuristic: IntProperty(name="Heuristic", min=0, max=127)

    def to_int(self):
        return int(self.tunnel) | (self.heuristic << 1)

    def from_int(self, v):
        self.tunnel    = bool(v & 1)
        self.heuristic = (v >> 1) & 127


class YND_NodeFlags4(PropertyGroup):
    density:      IntProperty(name="Density",     min=0, max=15)
    deadendness:  IntProperty(name="Deadendness", min=0, max=7)
    left_turn_only: BoolProperty(name="Left Turn Only")

    def to_int(self):
        return (self.density & 0xF) | ((self.deadendness & 0x7) << 4) | (int(self.left_turn_only) << 7)

    def from_int(self, v):
        self.density       = v & 0xF
        self.deadendness   = (v >> 4) & 7
        self.left_turn_only= bool(v & 128)


class YND_NodeFlags5(PropertyGroup):
    has_junction_heightmap: BoolProperty(name="Has Junction Heightmap")
    speed: EnumProperty(items=SPEED_ITEMS, name="Speed", default="NORMAL")

    def to_int(self):
        speed_map = {"SLOW": 0, "NORMAL": 2, "FAST": 4, "FASTER": 6}
        return int(self.has_junction_heightmap) | speed_map.get(self.speed, 0)

    def from_int(self, v):
        self.has_junction_heightmap = bool(v & 1)
        speed_val = v & 0xFE
        speed_map = {0:"SLOW", 2:"NORMAL", 4:"FAST", 6:"FASTER"}
        self.speed = speed_map.get(speed_val, "NORMAL")


# ─────────────────────────────────────────────────────────────────────────────
#  YND LINK FLAGS
# ─────────────────────────────────────────────────────────────────────────────

class YND_LinkFlags0(PropertyGroup):
    gps_both_ways:    BoolProperty(name="GPS Both Ways")
    block_if_no_lanes:BoolProperty(name="Block If No Lanes")
    unknown_1:        IntProperty(name="Unknown 1", min=0, max=7)
    unknown_2:        IntProperty(name="Unknown 2", min=0, max=7)

    def to_int(self):
        return int(self.gps_both_ways) | (int(self.block_if_no_lanes) << 1) |                ((self.unknown_1 & 7) << 2) | ((self.unknown_2 & 7) << 5)

    def from_int(self, v):
        self.gps_both_ways     = bool(v & 1)
        self.block_if_no_lanes = bool(v & 2)
        self.unknown_1         = (v >> 2) & 7
        self.unknown_2         = (v >> 5) & 7


class YND_LinkFlags1(PropertyGroup):
    unused_1:        BoolProperty(name="Unused 1")
    narrow_road:     BoolProperty(name="Narrow Road")
    dead_end:        BoolProperty(name="Dead End")
    dead_end_exit:   BoolProperty(name="Dead End Exit")
    negative_offset: BoolProperty(name="Negative Offset")
    offset:          IntProperty(name="Offset", min=0, max=7)

    def to_int(self):
        return int(self.unused_1) | (int(self.narrow_road) << 1) |                (int(self.dead_end) << 2) | (int(self.dead_end_exit) << 3) |                ((self.offset & 7) << 4) | (int(self.negative_offset) << 7)

    def from_int(self, v):
        self.unused_1        = bool(v & 1)
        self.narrow_road     = bool(v & 2)
        self.dead_end        = bool(v & 4)
        self.dead_end_exit   = bool(v & 8)
        self.offset          = (v >> 4) & 7
        self.negative_offset = bool(v & 128)


class YND_LinkFlags2(PropertyGroup):
    dont_use_for_navigation: BoolProperty(name="Don't Use For Navigation")
    shortcut:    BoolProperty(name="Shortcut")
    back_lanes:  IntProperty(name="Back Lanes",    min=0, max=7)
    forward_lanes:IntProperty(name="Forward Lanes",min=0, max=7)

    def to_int(self):
        return int(self.dont_use_for_navigation) | (int(self.shortcut) << 1) |                ((self.back_lanes & 7) << 2) | ((self.forward_lanes & 7) << 5)

    def from_int(self, v):
        self.dont_use_for_navigation = bool(v & 1)
        self.shortcut    = bool(v & 2)
        self.back_lanes  = (v >> 2) & 7
        self.forward_lanes = (v >> 5) & 7


# ─────────────────────────────────────────────────────────────────────────────
#  YND JUNCTION
# ─────────────────────────────────────────────────────────────────────────────

class YND_JunctionProps(PropertyGroup):
    max_z:    FloatProperty(name="Max Z", default=0.0)
    min_z:    FloatProperty(name="Min Z", default=0.0)
    pos_x:    FloatProperty(name="Pos X", default=0.0)
    pos_y:    FloatProperty(name="Pos Y", default=0.0)
    size_x:   IntProperty(name="Size X",  default=8, min=1)
    size_y:   IntProperty(name="Size Y",  default=8, min=1)
    ref_unk0: IntProperty(name="Ref Unk0", default=0)
    heightmap:StringProperty(name="Heightmap", default="")


# ─────────────────────────────────────────────────────────────────────────────
#  YND LINK & NODE
# ─────────────────────────────────────────────────────────────────────────────

class YND_LinkItem(PropertyGroup):
    to_area_id:  IntProperty(name="ToArea",   default=0)
    to_node_id:  IntProperty(name="ToNode",   default=0)
    flags0:      PointerProperty(type=YND_LinkFlags0, name="Flags 0")
    flags1:      PointerProperty(type=YND_LinkFlags1, name="Flags 1")
    flags2:      PointerProperty(type=YND_LinkFlags2, name="Flags 2")
    # Raw values for fast import/export
    raw_flags0:  IntProperty(default=0, min=0, max=255)
    raw_flags1:  IntProperty(default=0, min=0, max=255)
    raw_flags2:  IntProperty(default=0, min=0, max=255)
    link_length: IntProperty(name="Length", default=10, min=1, max=255)


class YND_NodeItem(PropertyGroup):
    area_id:    IntProperty(name="Area ID",  default=400)
    node_id:    IntProperty(name="Node ID",  default=0)
    curve_chain_index: IntProperty(default=-1)
    curve_point_index: IntProperty(default=-1)
    street_name:StringProperty(name="Street",   default="")
    position:   FloatVectorProperty(name="Position", size=3, default=(0,0,0), precision=5)
    flags0:     PointerProperty(type=YND_NodeFlags0, name="Flags 0")
    flags1:     PointerProperty(type=YND_NodeFlags1, name="Flags 1")
    flags2:     PointerProperty(type=YND_NodeFlags2, name="Flags 2")
    flags3:     PointerProperty(type=YND_NodeFlags3, name="Flags 3")
    flags4:     PointerProperty(type=YND_NodeFlags4, name="Flags 4")
    flags5:     PointerProperty(type=YND_NodeFlags5, name="Flags 5")
    junction:   PointerProperty(type=YND_JunctionProps, name="Junction")
    # Raw ints for I/O compatibility
    raw0:  IntProperty(default=2,   min=0, max=255)
    raw1:  IntProperty(default=0,   min=0, max=255)
    raw2:  IntProperty(default=0,   min=0, max=255)
    raw3:  IntProperty(default=64,  min=0, max=255)
    raw4:  IntProperty(default=134, min=0, max=255)
    raw5:  IntProperty(default=2,   min=0, max=255)
    links:      CollectionProperty(type=YND_LinkItem)
    link_index: IntProperty(default=-1)

    @property
    def is_vehicle(self):
        return self.flags1.special_type not in PED_SPECIAL_TYPES


class YND_Props(PropertyGroup):
    filepath:           StringProperty(name="File", subtype="FILE_PATH", default="")
    area_id:            IntProperty(name="Area ID", default=400)
    curve_bidirectional: BoolProperty(name="Bidirectional Links", default=True)
    curve_preset:       EnumProperty(
        name="Curve Preset",
        items=[
            ("TWO_LANES", "2 Lanes L | 2 Lanes R", "Default 2x2 road"),
            ("ONE_EACH", "1 Lanes L | 1 Lanes R", "One lane per direction"),
            ("CENTER_ONE", "One center lane", "Single centered traffic lane"),
            ("CENTER_TWO", "Two center lane", "Two centered traffic lanes"),
            ("CENTER_THREE", "Three center lane", "Three centered traffic lanes"),
            ("NO_TRAFFIC", "One lane - no Traffic", "Lane with no traffic hints"),
            ("BOATS", "Boats", "Boat path defaults"),
            ("PARKING", "Parking", "Parking pair, requires exactly 2 points"),
        ],
        default="TWO_LANES",
    )
    vehicle_node_count: IntProperty(default=0)
    ped_node_count:     IntProperty(default=0)
    nodes:              CollectionProperty(type=YND_NodeItem)
    node_index:         IntProperty(default=-1)
    show_vehicle:       BoolProperty(name="Vehicles",  default=True)
    show_ped:           BoolProperty(name="Pedestrians",    default=True)
    show_links:         BoolProperty(name="Links",      default=True)
    show_junctions:     BoolProperty(name="Junctions", default=True)
    filter_street:      StringProperty(name="Street", default="")
    stat_nodes:         IntProperty(default=0)
    stat_vehicle:       IntProperty(default=0)
    stat_ped:           IntProperty(default=0)
    stat_junctions:     IntProperty(default=0)


# ─────────────────────────────────────────────────────────────────────────────
#  YNV FLAGS (bytes 0-3 complets + bytes 4-5 raw)
# ─────────────────────────────────────────────────────────────────────────────

class YNV_PolyFlagsItem(PropertyGroup):
    poly_index:      IntProperty(name="Index Polygone", default=0)
    small_poly:      BoolProperty(name="Small Poly",     default=False)
    large_poly:      BoolProperty(name="Large Poly",     default=False)
    is_pavement:     BoolProperty(name="Is Pavement",    default=False)
    is_underground:  BoolProperty(name="Is Underground", default=False)
    unused_f1_4:     BoolProperty(name="Not Used B1-4",  default=False)
    unused_f1_5:     BoolProperty(name="Not Used B1-5",  default=False)
    is_too_steep:    BoolProperty(name="Is Too Steep",   default=False)
    is_water:        BoolProperty(name="Is Water",       default=False)
    audio_prop1:     BoolProperty(name="AudioPro 1",     default=False)
    audio_prop2:     BoolProperty(name="AudioPro 2",     default=False)
    audio_prop3:     BoolProperty(name="AudioPro 3",     default=False)
    unused_f2_3:     BoolProperty(name="Not Used B2-3",  default=False)
    near_car_node:   BoolProperty(name="Near Car Node",  default=False)
    is_interior:     BoolProperty(name="Is Interior",    default=False)
    is_isolated:     BoolProperty(name="Is Isolated",    default=False)
    unused_f2_7:     BoolProperty(name="Not Used B2-7",  default=False)
    can_spawn:       BoolProperty(name="Can Spawn",      default=False)
    is_road:         BoolProperty(name="Is Road",        default=False)
    along_edge:      BoolProperty(name="Along Edge",     default=False)
    is_train_track:  BoolProperty(name="Is Train Track", default=False)
    is_shallow:      BoolProperty(name="Is Shallow",     default=False)
    ped_density1:    BoolProperty(name="PedDensity 1",   default=False)
    ped_density2:    BoolProperty(name="PedDensity 2",   default=False)
    ped_density3:    BoolProperty(name="PedDensity 3",   default=False)
    cover_south:     BoolProperty(name="Cover South",    default=False)
    cover_south2:    BoolProperty(name="Cover South 2",  default=False)
    cover_east:      BoolProperty(name="Cover East",     default=False)
    cover_north:     BoolProperty(name="Cover North",    default=False)
    cover_north2:    BoolProperty(name="Cover North 2",  default=False)
    cover_north3:    BoolProperty(name="Cover North 3",  default=False)
    cover_west:      BoolProperty(name="Cover West",     default=False)
    cover_south3:    BoolProperty(name="Cover South 3",  default=False)
    byte4:           IntProperty(name="Byte4 (raw)", default=0, min=0, max=255)
    byte5:           IntProperty(name="Byte5 (raw)", default=0, min=0, max=255)

    def to_flags_str(self):
        b0 = (self.small_poly <<0)|(self.large_poly <<1)|(self.is_pavement <<2)|(self.is_underground <<3)|(self.unused_f1_4 <<4)|(self.unused_f1_5 <<5)|(self.is_too_steep <<6)|(self.is_water <<7)
        b1 = (self.audio_prop1<<0)|(self.audio_prop2<<1)|(self.audio_prop3<<2)|(self.unused_f2_3   <<3)|(self.near_car_node<<4)|(self.is_interior<<5)|(self.is_isolated<<6)|(self.unused_f2_7<<7)
        b2 = (self.can_spawn  <<0)|(self.is_road    <<1)|(self.along_edge <<2)|(self.is_train_track <<3)|(self.is_shallow  <<4)|(self.ped_density1<<5)|(self.ped_density2<<6)|(self.ped_density3<<7)
        b3 = (self.cover_south<<0)|(self.cover_south2<<1)|(self.cover_east<<2)|(self.cover_north    <<3)|(self.cover_north2<<4)|(self.cover_north3<<5)|(self.cover_west <<6)|(self.cover_south3<<7)
        return f"{b0} {b1} {b2} {b3} {self.byte4} {self.byte5}"

    def from_flags_str(self, s):
        try:
            p = [int(x) for x in s.split()]
            while len(p) < 6: p.append(0)
        except Exception: return
        b0,b1,b2,b3 = p[0],p[1],p[2],p[3]
        self.byte4,self.byte5 = p[4],p[5]
        self.small_poly     = bool(b0&1);  self.large_poly    = bool(b0&2)
        self.is_pavement    = bool(b0&4);  self.is_underground= bool(b0&8)
        self.unused_f1_4    = bool(b0&16); self.unused_f1_5   = bool(b0&32)
        self.is_too_steep   = bool(b0&64); self.is_water      = bool(b0&128)
        self.audio_prop1    = bool(b1&1);  self.audio_prop2   = bool(b1&2)
        self.audio_prop3    = bool(b1&4);  self.unused_f2_3   = bool(b1&8)
        self.near_car_node  = bool(b1&16); self.is_interior   = bool(b1&32)
        self.is_isolated    = bool(b1&64); self.unused_f2_7   = bool(b1&128)
        self.can_spawn      = bool(b2&1);  self.is_road       = bool(b2&2)
        self.along_edge     = bool(b2&4);  self.is_train_track= bool(b2&8)
        self.is_shallow     = bool(b2&16); self.ped_density1  = bool(b2&32)
        self.ped_density2   = bool(b2&64); self.ped_density3  = bool(b2&128)
        self.cover_south    = bool(b3&1);  self.cover_south2  = bool(b3&2)
        self.cover_east     = bool(b3&4);  self.cover_north   = bool(b3&8)
        self.cover_north2   = bool(b3&16); self.cover_north3  = bool(b3&32)
        self.cover_west     = bool(b3&64); self.cover_south3  = bool(b3&128)


class YNV_PortalItem(PropertyGroup):
    portal_type: IntProperty(name="Type", default=1, min=1, max=3)
    angle:       FloatProperty(name="Angle", default=0.0, precision=6)
    poly_from:   IntProperty(name="PolyFrom", default=0, min=0)
    poly_to:     IntProperty(name="PolyTo",   default=0, min=0)
    pos_from:    FloatVectorProperty(name="Pos From", size=3, default=(0,0,0), precision=6)
    pos_to:      FloatVectorProperty(name="Pos To",   size=3, default=(0,0,0), precision=6)


class YNV_NavPointItem(PropertyGroup):
    point_type: IntProperty(name="Type",  default=0, min=0, max=255)
    angle:      FloatProperty(name="Angle (rad)", default=0.0, min=0.0, max=6.2832, precision=6)
    position:   FloatVectorProperty(name="Position", size=3, default=(0,0,0), precision=5)


class YNV_Props(PropertyGroup):
    filepath:      StringProperty(name="File", subtype="FILE_PATH", default="")
    area_id:       IntProperty(name="Area ID", default=0)
    content_flags: StringProperty(name="ContentFlags", default="Polygons, Portals")
    bb_min:        FloatVectorProperty(name="BB Min", size=3, default=(0,0,0))
    bb_max:        FloatVectorProperty(name="BB Max", size=3, default=(0,0,0))
    portals:       CollectionProperty(type=YNV_PortalItem)
    portal_index:  IntProperty(default=-1)
    nav_points:         CollectionProperty(type=YNV_NavPointItem)
    nav_point_index:    IntProperty(default=-1)
    selected_poly_flags:PointerProperty(type=YNV_PolyFlagsItem)
    flag_preset: EnumProperty(
        name="Flag Preset",
        items=[
            ("ROAD","Road","Road"),("PAVEMENT","Pavement","Pavement"),
            ("INTERIOR","Interior","Interior"),("WATER","Water","Water"),
            ("SHALLOW","Shallow","Shallow"),("TRAIN","Train Track","Train"),
            ("COVER","Cover","Cover"),("SPAWN","Spawn Zone","Spawn"),("CUSTOM","Custom","Custom"),
        ],
        default="ROAD",
    )
    filter_flag:    EnumProperty(name="Filter", items=[("NONE","All","")], default="NONE")
    show_polygons:  BoolProperty(name="Polygons",  default=True)
    show_portals:   BoolProperty(name="Portals",   default=True)
    show_navpoints: BoolProperty(name="Nav Points", default=True)
    stat_polygons:  IntProperty(default=0)
    stat_portals:   IntProperty(default=0)
    stat_navpoints: IntProperty(default=0)
    tile_size:      FloatProperty(name="Tile Size", default=150.0, min=1.0)
    offset_x:       FloatProperty(name="Offset X",  default=0.0)
    offset_y:       FloatProperty(name="Offset Y",  default=0.0)


# ─────────────────────────────────────────────────────────────────────────────
#  YMT
# ─────────────────────────────────────────────────────────────────────────────

class YMT_ScenarioPointItem(PropertyGroup):
    itype:            IntProperty(name="Type iType", default=1, min=0, max=255)
    model_set_id:     IntProperty(name="ModelSet ID", default=0)
    interior_id:      IntProperty(name="Interior ID", default=0)
    imap_id:          IntProperty(name="IMap ID",     default=0)
    probability:      IntProperty(name="Probability", default=0, min=0, max=255)
    avail_mp_sp:      IntProperty(name="MP/SP",       default=1, min=0, max=3)
    time_start:       IntProperty(name="Time Start", default=0, min=0, max=23)
    time_end:         IntProperty(name="Time End",   default=24,min=0, max=24)
    radius:           IntProperty(name="Radius",       default=0)
    time_till_leaves: IntProperty(name="Time Till Leaves",default=255,min=0,max=255)
    scenario_group:   IntProperty(name="Group",      default=0)
    flags:            StringProperty(name="Flags",    default="")
    position:         FloatVectorProperty(name="Position XYZW", size=4, default=(0,0,0,0))

class YMT_ChainingNodeItem(PropertyGroup):
    position:      FloatVectorProperty(name="Position", size=3, default=(0,0,0))
    scenario_type: StringProperty(name="Scenario Type", default="standing")
    has_incoming:  BoolProperty(name="Incoming",  default=False)
    has_outgoing:  BoolProperty(name="Outgoing",  default=True)
    hash_prop:     StringProperty(name="hash_9B1D60AB", default="")

class YMT_ChainingEdgeItem(PropertyGroup):
    node_from: IntProperty(name="From",      default=0, min=0)
    node_to:   IntProperty(name="To",       default=0, min=0)
    action:    IntProperty(name="Action",  default=0)
    nav_mode:  IntProperty(name="NavMode", default=1)
    nav_speed: IntProperty(name="Speed", default=2)

class YMT_ChainItem(PropertyGroup):
    hash_name: StringProperty(name="Hash Name", default="")
    edge_ids:  StringProperty(name="Edge IDs", default="")

class YMT_EntityOverrideItem(PropertyGroup):
    entity_type:     StringProperty(name="Entity Type",   default="")
    entity_position: FloatVectorProperty(name="Position", size=3, default=(0,0,0))
    may_not_exist:   BoolProperty(name="May Not Exist",   default=True)
    prevent_art:     BoolProperty(name="Prevent Art",     default=False)

class YMT_Props(PropertyGroup):
    filepath:       StringProperty(name="File", subtype="FILE_PATH", default="")
    version_number: IntProperty(name="Version", default=80)
    scenario_points:       CollectionProperty(type=YMT_ScenarioPointItem)
    point_index:           IntProperty(default=-1)
    chaining_nodes:        CollectionProperty(type=YMT_ChainingNodeItem)
    chain_node_index:      IntProperty(default=-1)
    chaining_edges:        CollectionProperty(type=YMT_ChainingEdgeItem)
    chain_edge_index:      IntProperty(default=-1)
    chains:                CollectionProperty(type=YMT_ChainItem)
    chain_index:           IntProperty(default=-1)
    entity_overrides:      CollectionProperty(type=YMT_EntityOverrideItem)
    entity_override_index: IntProperty(default=-1)
    type_names:            StringProperty(default="")
    ped_modelset_names:    StringProperty(default="")
    veh_modelset_names:    StringProperty(default="")
    accel_min_cell_x:IntProperty(default=-4); accel_max_cell_x:IntProperty(default=5)
    accel_min_cell_y:IntProperty(default=-64); accel_max_cell_y:IntProperty(default=-48)
    accel_cell_dim_x:IntProperty(default=32); accel_cell_dim_y:IntProperty(default=32)
    show_scenario_pts:BoolProperty(name="Scenario Points", default=True)
    show_chain_nodes: BoolProperty(name="Chaining Nodes", default=True)
    show_chain_edges: BoolProperty(name="Edges",          default=True)
    filter_type:    EnumProperty(name="Filter", items=[("ALL","All","")], default="ALL")
    stat_points:    IntProperty(default=0)
    stat_nodes:     IntProperty(default=0)
    stat_edges:     IntProperty(default=0)
    stat_chains:    IntProperty(default=0)


# ─────────────────────────────────────────────────────────────────────────────
#  TRAINS
# ─────────────────────────────────────────────────────────────────────────────

class TRAINS_TrackPointItem(PropertyGroup):
    position: FloatVectorProperty(name="Position", size=3, default=(0,0,0), precision=3)
    flag:     IntProperty(name="Flag", default=0, min=0, max=5)

class TRAINS_Props(PropertyGroup):
    filepath:       StringProperty(name="File", subtype="FILE_PATH", default="")
    track_name:     StringProperty(name="Track Name", default="trains4")
    points:         CollectionProperty(type=TRAINS_TrackPointItem)
    point_index:    IntProperty(default=-1)
    show_track:     BoolProperty(name="Track",        default=True)
    show_junctions: BoolProperty(name="Junctions", default=True)
    stat_points:    IntProperty(default=0)
    stat_junctions: IntProperty(default=0)
    use_curve_gen:  BoolProperty(name="Generate Blender Curve", default=True)


# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

class GTA5_PathingProps(PropertyGroup):
    active_module: EnumProperty(
        name="Module",
        items=[
            ("YNV",    "NavMesh (YNV)",   "Pedestrian/Vehicle NavMesh", "MOD_FLUID",    0),
            ("YND",    "PathNodes (YND)", "Path Nodes",         "EMPTY_ARROWS", 1),
            ("YMT",    "Scenarios (YMT)", "Scenario Points",       "ARMATURE_DATA",2),
            ("TRAINS", "Train Tracks",    "Train Tracks",           "CURVE_PATH",   3),
        ],
        default="YNV",
    )
    ynv:    PointerProperty(type=YNV_Props)
    ynd:    PointerProperty(type=YND_Props)
    ymt:    PointerProperty(type=YMT_Props)
    trains: PointerProperty(type=TRAINS_Props)


_classes = [
    # YND flags
    YND_NodeFlags0, YND_NodeFlags1, YND_NodeFlags2, YND_NodeFlags3, YND_NodeFlags4, YND_NodeFlags5,
    YND_LinkFlags0, YND_LinkFlags1, YND_LinkFlags2,
    YND_JunctionProps,
    YND_LinkItem, YND_NodeItem, YND_Props,
    # YNV
    YNV_PolyFlagsItem, YNV_PortalItem, YNV_NavPointItem, YNV_Props,
    # YMT
    YMT_ScenarioPointItem, YMT_ChainingNodeItem, YMT_ChainingEdgeItem,
    YMT_ChainItem, YMT_EntityOverrideItem, YMT_Props,
    # Trains
    TRAINS_TrackPointItem, TRAINS_Props,
    # Global
    GTA5_PathingProps,
]

def register():
    for cls in _classes:
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
        bpy.utils.register_class(cls)
    bpy.types.Scene.gta5_pathing = PointerProperty(type=GTA5_PathingProps)

def unregister():
    try: del bpy.types.Scene.gta5_pathing
    except Exception: pass
    for cls in reversed(_classes):
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
