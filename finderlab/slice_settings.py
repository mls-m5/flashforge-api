"""Small typed quality-option allowlist, not arbitrary Orca JSON/CLI input."""


def normalize_settings(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {"layer_height", "brim", "brim_width"}:
        raise ValueError("Only layer_height, brim and brim_width slicing settings are supported")
    layer = value.get("layer_height")
    brim = value.get("brim", "profile")
    width = value.get("brim_width", 5)
    if layer is not None:
        if type(layer) not in (int, float) or not 0.08 <= layer <= 0.28:
            raise ValueError("Layer height must be a finite number from 0.08 to 0.28 mm, or null for profile")
    if not isinstance(brim, str) or brim not in ("profile", "off", "outer"):
        raise ValueError("Brim must be profile, off or outer")
    if type(width) not in (int, float) or not 1 <= width <= 10:
        raise ValueError("Brim width must be a finite number from 1 to 10 mm")
    return {"layer_height": layer, "brim": brim, "brim_width": width}


def process_overrides(settings):
    settings = normalize_settings(settings)
    result = {}
    if settings["layer_height"] is not None:
        result["layer_height"] = format(settings["layer_height"], ".8g")
    if settings["brim"] == "off":
        result.update(brim_type="no_brim", brim_width="0")
    elif settings["brim"] == "outer":
        result.update(brim_type="outer_only", brim_width=format(settings["brim_width"], ".8g"))
    return result
