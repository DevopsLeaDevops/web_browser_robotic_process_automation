"""JSON Schema 2020-12；參數須在啟動瀏覽器之前驗證。"""
from copy import deepcopy
from jsonschema import Draft202012Validator, FormatChecker

INPUT_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object', 'required': ['title', 'quantity'], 'additionalProperties': False,
    'properties': {'title': {'type': 'string', 'minLength': 1, 'maxLength': 60, 'pattern': r'\S'},
                   'quantity': {'type': 'integer', 'minimum': 1, 'maximum': 30}},
}
RECORD_ID = {'type': 'string', 'pattern': '^DEMO-[A-Z0-9]+$'}
QUERY_SCHEMA = {
    **INPUT_SCHEMA, 'required': ['recordId', 'quantity'],
    'properties': {'recordId': RECORD_ID,
                   'quantity': {'type': 'integer', 'minimum': 1, 'maximum': 30},
                   'expectedTitle': {'type': 'string'}, 'note': {'type': 'string'}},
}
OUTPUT_SCHEMA = {
    **INPUT_SCHEMA, 'required': ['recordId', 'title', 'quantity'],
    'properties': {**INPUT_SCHEMA['properties'], 'recordId': RECORD_ID},
}
DEFAULTS = {'title': '介面驗證範例', 'quantity': 12}


def validate(value, schema):
    def walk(value):
        if isinstance(value, dict):
            if any(k in value for k in ('$ref', '$dynamicRef', '$recursiveRef')):
                raise ValueError('Schema 必須自包含，不允許遠端或遞迴引用')
            for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(schema)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    return value


def scene_catalog():
    example = {'recordId':'DEMO-001','title':'介面驗證範例','quantity':12}
    return deepcopy({
        'BA-001': {'revision':1, 'input':{'schema':INPUT_SCHEMA,'defaults':DEFAULTS},
                   'output':{'schema':OUTPUT_SCHEMA,'example':example}},
        'BA-002': {'revision':1, 'input':{'schema':QUERY_SCHEMA,
                   'defaults':{'recordId':'DEMO-001','quantity':12,'expectedTitle':'','note':'預設驗證說明'}},
                   'output':{'schema':OUTPUT_SCHEMA,'example':example}},
    })
