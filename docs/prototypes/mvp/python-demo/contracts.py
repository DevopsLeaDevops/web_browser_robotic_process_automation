"""JSON Schema 2020-12；參數須在啟動瀏覽器之前驗證。"""
from jsonschema import Draft202012Validator

INPUT_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object', 'required': ['title', 'quantity'], 'additionalProperties': False,
    'properties': {'title': {'type': 'string', 'minLength': 1, 'maxLength': 60, 'pattern': r'\S'},
                   'quantity': {'type': 'integer', 'minimum': 1, 'maximum': 30}},
}
QUERY_SCHEMA = {
    **INPUT_SCHEMA, 'required': ['recordId'],
    'properties': {'recordId': {'type': 'string', 'pattern': '^DEMO-[A-Z0-9]+$'}},
}
OUTPUT_SCHEMA = {
    **INPUT_SCHEMA, 'required': ['recordId', 'title', 'quantity'],
    'properties': {**INPUT_SCHEMA['properties'], **QUERY_SCHEMA['properties']},
}
DEFAULTS = {'title': '介面驗證範例', 'quantity': 12}


def validate(value, schema):
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)
    return value
