import json
import uuid

from openai import OpenAI

SYSTEM_PROMPT = """
Ты — ассистент, который преобразует запросы на естественном языке 
в инструкции для MUI Data Grid.

Доступные колонки: {columns}

Верни JSON строго следующего формата:
{{
  "filterModel": {{"items": [...], "logicOperator": "and"}},
  "sortModel": [{{"field": "...", "sort": "asc"|"desc"}}]
}}

Используй только доступные операторы: "contains", "equals", ">", "<", ">=", "<=", "!=", "startsWith", "endsWith".
"""


def call_ai_provider(query, context, conversation_id, options):
    # Приводим context к единому виду списку колонок
    if isinstance(context, list):
        columns = context
    elif isinstance(context, dict):
        columns = context.get('columns', [])
    else:
        columns = []

    examples = []
    for col in columns:
        col_examples = col.get('examples', [])
        if col_examples:
            examples.extend(col_examples)

    system = SYSTEM_PROMPT.format(columns=json.dumps(columns, ensure_ascii=False))
    user = f"Запрос: {query}\nПримеры значений: {json.dumps(examples, ensure_ascii=False)}"

    client = OpenAI(
        api_key="sk-c0059f8b0d69405d9ec8cdef54128408",
        base_url="https://api.deepseek.com"
    )

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        response_format={"type": "json_object"}
    )

    raw_result = json.loads(response.choices[0].message.content)

    mui_response = {
        "select": -1,
        "filters": [],
        "aggregation": {},
        "sorting": [],
        "grouping": [],
        "pivoting": {},
        "chart": None,
        "conversationId": conversation_id or str(uuid.uuid4())
    }

    if "filterModel" in raw_result:
        filter_model = raw_result["filterModel"]
        mui_response["filters"] = [
            {
                "column": item.get("field"),
                "operator": item.get("operator", "contains"),
                "value": item.get("value")
            }
            for item in filter_model.get("items", [])
        ]

    # Преобразуем sortModel -> sorting
    if "sortModel" in raw_result:
        mui_response["sorting"] = [
            {
                "column": item.get("field"),
                "direction": item.get("sort", "asc")
            }
            for item in raw_result["sortModel"]
        ]

    return mui_response
