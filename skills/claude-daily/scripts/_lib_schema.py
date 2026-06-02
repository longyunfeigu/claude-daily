# input: Python dict (instance) and JSON Schema dict (schema)
# output: validate() returning list of error strings; empty list means valid
# owner: wanhua.gu
# pos: skill library - minimal zero-dependency JSON Schema validator (draft-07 subset); 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Minimal JSON Schema validator (draft-07 subset, stdlib only).

Supports: type, enum, required, additionalProperties, properties,
          pattern, minLength, maxLength, minimum, maximum.
"""
import re

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def validate(instance, schema, path=""):
    """Validate *instance* against *schema* and return a list of error strings.

    Returns an empty list when the instance is valid.
    """
    errors = []

    # --- type check ---
    if "type" in schema:
        type_spec = schema["type"]
        if isinstance(type_spec, list):
            allowed_types = tuple(
                _TYPE_MAP[t] for t in type_spec if t in _TYPE_MAP
            )
            # bool is subclass of int; only allow it when "boolean" is listed
            if isinstance(instance, bool) and "boolean" not in type_spec:
                errors.append(
                    f"{path or 'root'}: expected one of {type_spec}, got bool"
                )
                return errors
            if not isinstance(instance, allowed_types):
                errors.append(
                    f"{path or 'root'}: expected one of {type_spec}, "
                    f"got {type(instance).__name__}"
                )
                return errors
        else:
            expected = _TYPE_MAP.get(type_spec)
            if expected is None:
                pass  # unknown type keyword — skip
            else:
                # bool is a subclass of int; reject bool when only "integer"/"number" wanted
                if isinstance(instance, bool) and type_spec in ("integer", "number"):
                    errors.append(
                        f"{path or 'root'}: expected {type_spec}, got bool"
                    )
                    return errors
                if not isinstance(instance, expected):
                    errors.append(
                        f"{path or 'root'}: expected {type_spec}, "
                        f"got {type(instance).__name__}"
                    )
                    return errors

    # --- enum ---
    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append(
                f"{path or 'root'}: value {instance!r} not in enum {schema['enum']}"
            )

    # --- string keywords ---
    if isinstance(instance, str):
        if "pattern" in schema:
            if not re.search(schema["pattern"], instance):
                errors.append(
                    f"{path or 'root'}: value {instance!r} does not match "
                    f"pattern {schema['pattern']!r}"
                )
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(
                f"{path or 'root'}: length {len(instance)} < minLength {schema['minLength']}"
            )
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(
                f"{path or 'root'}: length {len(instance)} > maxLength {schema['maxLength']}"
            )

    # --- numeric keywords (exclude bool which is subclass of int) ---
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(
                f"{path or 'root'}: value {instance} < minimum {schema['minimum']}"
            )
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(
                f"{path or 'root'}: value {instance} > maximum {schema['maximum']}"
            )

    # --- object keywords ---
    if isinstance(instance, dict):
        # required
        for key in schema.get("required", []):
            if key not in instance:
                field_path = f"{path}.{key}" if path else key
                errors.append(f"{field_path}: required field missing")

        # additionalProperties: False
        if schema.get("additionalProperties") is False:
            known = set(schema.get("properties", {}).keys())
            for key in instance:
                if key not in known:
                    field_path = f"{path}.{key}" if path else key
                    errors.append(f"{field_path}: additional property not allowed")

        # recurse into properties
        for key, sub_schema in schema.get("properties", {}).items():
            if key in instance:
                field_path = f"{path}.{key}" if path else key
                errors.extend(validate(instance[key], sub_schema, field_path))

    return errors
