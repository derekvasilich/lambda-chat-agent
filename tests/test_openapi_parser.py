import pytest

from app.openapi.parser import parse_spec

PETSTORE = {
    "openapi": "3.0.0",
    "info": {"title": "Petstore", "version": "1.0"},
    "servers": [{"url": "https://petstore.example.com/api/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List all pets",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                ],
                "responses": {"200": {"description": "ok"}},
            },
            "post": {
                "operationId": "createPet",
                "summary": "Create a pet",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Pet"}
                        }
                    },
                },
                "responses": {"201": {"description": "created"}},
            },
        },
        "/pets/{petId}": {
            "parameters": [
                {"name": "petId", "in": "path", "required": True, "schema": {"type": "string"}}
            ],
            "get": {
                "operationId": "getPetById",
                "summary": "Get a pet by ID",
                "responses": {"200": {"description": "ok"}},
            },
            "delete": {
                "operationId": "deletePet",
                "summary": "Delete a pet",
                "responses": {"204": {"description": "deleted"}},
            },
        },
    },
    "components": {
        "schemas": {
            "Pet": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "tag": {"type": "string", "nullable": True},
                },
            }
        }
    },
}


def test_petstore_yields_expected_operations():
    ops = parse_spec("petstore", PETSTORE)
    by_id = {op.op_id: op for op in ops}
    assert set(by_id.keys()) == {"listPets", "createPet", "getPetById", "deletePet"}


def test_petstore_methods_and_paths():
    ops = parse_spec("petstore", PETSTORE)
    by_id = {op.op_id: op for op in ops}
    assert by_id["listPets"].method == "get"
    assert by_id["listPets"].path_template == "/pets"
    assert by_id["createPet"].method == "post"
    assert by_id["getPetById"].path_template == "/pets/{petId}"


def test_path_level_params_are_inherited():
    ops = parse_spec("petstore", PETSTORE)
    by_id = {op.op_id: op for op in ops}
    get_by_id = by_id["getPetById"]
    assert "petId" in get_by_id.param_schema["properties"]
    assert "petId" in get_by_id.param_schema["required"]


def test_request_body_becomes_body_property():
    ops = parse_spec("petstore", PETSTORE)
    create = next(op for op in ops if op.op_id == "createPet")
    props = create.param_schema["properties"]
    assert "body" in props
    assert props["body"]["type"] == "object"
    assert "name" in props["body"]["properties"]
    assert create.param_schema["required"] == ["body"]


def test_nullable_normalized_to_union_type():
    ops = parse_spec("petstore", PETSTORE)
    create = next(op for op in ops if op.op_id == "createPet")
    tag_schema = create.param_schema["properties"]["body"]["properties"]["tag"]
    assert tag_schema["type"] == ["string", "null"]


def test_synthesized_op_id_when_missing():
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/widgets/{id}": {
                "get": {"responses": {"200": {"description": "ok"}}},
            }
        },
    }
    ops = parse_spec("widgets", spec)
    assert len(ops) == 1
    assert ops[0].op_id == "get_widgets_id"


def test_allof_merges_properties():
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/things": {
                "post": {
                    "operationId": "createThing",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
                                        {"type": "object", "properties": {"b": {"type": "integer"}}},
                                    ]
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "ok"}},
                }
            }
        },
    }
    ops = parse_spec("things", spec)
    body = ops[0].param_schema["properties"]["body"]
    assert set(body["properties"].keys()) == {"a", "b"}
    assert body["required"] == ["a"]


def test_circular_ref_terminates():
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/loop": {
                "post": {
                    "operationId": "loopOp",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "next": {"$ref": "#/components/schemas/Node"},
                    },
                }
            }
        },
    }
    # Should not infinite-loop
    ops = parse_spec("loop", spec)
    assert len(ops) == 1


def test_missing_paths_raises():
    with pytest.raises(ValueError):
        parse_spec("x", {"openapi": "3.0.0"})


def test_servers_captured():
    ops = parse_spec("petstore", PETSTORE)
    assert ops[0].servers == ["https://petstore.example.com/api/v1"]


def test_embedding_text_combines_fields():
    ops = parse_spec("petstore", PETSTORE)
    list_pets = next(op for op in ops if op.op_id == "listPets")
    text = list_pets.embedding_text()
    assert "GET" in text
    assert "/pets" in text
    assert "List all pets" in text


def test_slim_view_shape():
    ops = parse_spec("petstore", PETSTORE)
    list_pets = next(op for op in ops if op.op_id == "listPets")
    slim = list_pets.slim_view()
    assert slim["spec_id"] == "petstore"
    assert slim["operation_id"] == "listPets"
    assert slim["method"] == "GET"
    assert slim["path"] == "/pets"
