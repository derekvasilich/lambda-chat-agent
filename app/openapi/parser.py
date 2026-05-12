from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from app.openapi.operation import Operation


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def parse_spec(spec_id: str, spec: Dict[str, Any]) -> List[Operation]:
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    if "paths" not in spec or not isinstance(spec["paths"], dict):
        raise ValueError("spec missing 'paths' object")

    components = spec.get("components", {}).get("schemas", {})
    servers = [s.get("url", "") for s in spec.get("servers", []) if isinstance(s, dict)]

    operations: List[Operation] = []
    for path_template, path_item in spec["paths"].items():
        if not isinstance(path_item, dict):
            continue
        path_level_params = path_item.get("parameters", [])
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(op, dict):
                continue
            operation = _build_operation(
                spec_id=spec_id,
                method=method,
                path_template=path_template,
                op=op,
                path_level_params=path_level_params,
                components=components,
                servers=servers,
            )
            operations.append(operation)
    return operations


def _build_operation(
    spec_id: str,
    method: str,
    path_template: str,
    op: Dict[str, Any],
    path_level_params: List[Dict[str, Any]],
    components: Dict[str, Any],
    servers: List[str],
) -> Operation:
    op_id = op.get("operationId") or _synth_op_id(method, path_template)
    summary = (op.get("summary") or "").strip()
    description = (op.get("description") or "").strip()
    raw_params = list(path_level_params) + list(op.get("parameters", []))
    request_body = op.get("requestBody")

    param_schema = _build_param_schema(raw_params, request_body, components)
    security = list(op.get("security", []))

    return Operation(
        spec_id=spec_id,
        op_id=op_id,
        method=method.lower(),
        path_template=path_template,
        summary=summary,
        description=description,
        param_schema=param_schema,
        security=security,
        servers=servers,
    )


def _synth_op_id(method: str, path_template: str) -> str:
    cleaned = path_template.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method.lower()}_{cleaned}" if cleaned else method.lower()


def _build_param_schema(
    params: List[Dict[str, Any]],
    request_body: Optional[Dict[str, Any]],
    components: Dict[str, Any],
) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    param_locations: Dict[str, str] = {}

    for p in params:
        resolved = _resolve_ref(p, components)
        if not isinstance(resolved, dict):
            continue
        name = resolved.get("name")
        if not name:
            continue
        schema = resolved.get("schema", {})
        if not isinstance(schema, dict):
            schema = {}
        normalized = _normalize_schema(schema, components)
        if resolved.get("description"):
            normalized.setdefault("description", resolved["description"])
        properties[name] = normalized
        if resolved.get("required") or resolved.get("in") == "path":
            required.append(name)
        param_locations[name] = resolved.get("in", "query")

    if request_body and isinstance(request_body, dict):
        resolved_body = _resolve_ref(request_body, components)
        content = resolved_body.get("content", {}) if isinstance(resolved_body, dict) else {}
        json_media = content.get("application/json")
        if isinstance(json_media, dict) and "schema" in json_media:
            body_schema = _normalize_schema(json_media["schema"], components)
            properties["body"] = body_schema
            if resolved_body.get("required"):
                required.append("body")
            param_locations["body"] = "body"

    schema_out: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema_out["required"] = sorted(set(required))
    schema_out["x-param-locations"] = param_locations
    return schema_out


def _resolve_ref(obj: Any, components: Dict[str, Any], seen: Optional[set] = None) -> Any:
    if not isinstance(obj, dict):
        return obj
    if "$ref" not in obj:
        return obj
    if seen is None:
        seen = set()
    ref = obj["$ref"]
    if ref in seen:
        return {}
    seen.add(ref)
    if not ref.startswith("#/components/schemas/"):
        return {}
    name = ref[len("#/components/schemas/"):]
    target = components.get(name)
    if target is None:
        return {}
    return _resolve_ref(target, components, seen)


def _normalize_schema(
    schema: Dict[str, Any],
    components: Dict[str, Any],
    depth: int = 0,
) -> Dict[str, Any]:
    if depth > 12:
        return {"type": "object"}
    if not isinstance(schema, dict):
        return {}

    resolved = _resolve_ref(schema, components) if "$ref" in schema else schema
    if not isinstance(resolved, dict):
        return {}

    out: Dict[str, Any] = {}
    for key, value in resolved.items():
        if key == "nullable" and value:
            existing_type = out.get("type") or resolved.get("type")
            if existing_type and existing_type != "null":
                out["type"] = [existing_type, "null"]
            continue
        if key == "properties" and isinstance(value, dict):
            out["properties"] = {
                k: _normalize_schema(v, components, depth + 1) for k, v in value.items()
            }
            continue
        if key == "items" and isinstance(value, dict):
            out["items"] = _normalize_schema(value, components, depth + 1)
            continue
        if key in ("oneOf", "anyOf") and isinstance(value, list):
            out[key] = [_normalize_schema(v, components, depth + 1) for v in value]
            continue
        if key == "allOf" and isinstance(value, list):
            merged: Dict[str, Any] = {"type": "object", "properties": {}}
            merged_required: List[str] = []
            for sub in value:
                sub_norm = _normalize_schema(sub, components, depth + 1)
                if "properties" in sub_norm:
                    merged["properties"].update(sub_norm["properties"])
                if "required" in sub_norm:
                    merged_required.extend(sub_norm["required"])
                if not merged["properties"] and "type" in sub_norm and sub_norm["type"] != "object":
                    merged = sub_norm
                    break
            if merged_required:
                merged["required"] = sorted(set(merged_required))
            return merged
        out[key] = value
    return out
