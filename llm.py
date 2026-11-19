"""Function calling and structured reporting via OpenAI-compatible Chat Completions."""

import json
import os
from urllib.parse import urlsplit

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError

from analytics import TOOLS, execute_tool, validate_filters


class ProviderError(RuntimeError):
    """The configured provider failed to return a usable protocol response."""


class ProviderConfigurationError(ProviderError):
    """The server lacks a usable provider configuration."""


class ChatClarification(ValueError):
    """The question needs more information to resolve an analytics operation."""


def _settings():
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    key = os.getenv("LLM_API_KEY")
    if not base_url:
        use_openai = not key and not os.getenv("OPENROUTER_API_KEY") and os.getenv("OPENAI_API_KEY")
        base_url = "https://api.openai.com/v1" if use_openai else "https://openrouter.ai/api/v1"
    try:
        address = urlsplit(base_url)
        if (address.scheme not in {"https", "http"} or not address.hostname
                or address.username or address.password or address.query or address.fragment):
            raise ValueError
        hostname = address.hostname.lower()
    except ValueError as error:
        raise ProviderConfigurationError("Проверьте адрес API в LLM_BASE_URL.") from error
    router = hostname == "openrouter.ai"
    if not key and router:
        key = os.getenv("OPENROUTER_API_KEY")
    elif not key and (hostname == "api.openai.com" or base_url == os.getenv("OPENAI_BASE_URL")):
        key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL") or ("openai/gpt-4o-mini" if router else "gpt-4o-mini")
    return base_url.rstrip("/"), model, key, router


def get_config():
    """Public status for the server; the API key stays in the request client."""
    base_url, model, key, _ = _settings()
    return {"base_url": base_url, "model": model, "configured": bool(key)}


CLARIFY = {
    "period": "За какой период построить отчёт? Укажите даты или число последних смен.",
    "equipment": "Уточните линию (А или Б) или станок (S-101, S-102, S-201, S-202).",
    "metric": "Какой показатель вывести: выпуск, план, долю брака, простои или загрузку?",
    "scope": "Уточните задачу для цеха, например «Где выпуск отстаёт от плана за последние 5 смен?»",
}
CLARIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "request_clarification",
        "description": "Запросить уточнение, если вопрос неоднозначен или данных для него нет в витрине.",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string", "enum": list(CLARIFY)}},
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
}


INSTRUCTIONS = """Ты аналитик цеха. Выбери одну функцию для текущего вопроса.
При уточнении меняй только названные условия. Уже действующие фильтры и базовый
инструмент представлены в context. Для самостоятельного нового вопроса учитывай
явно указанные пользователем условия. Учебная витрина заканчивается 19 ноября
2026 в 08:00 местного времени. Участки А и Б обозначают соответствующие линии.
Неизвестный объект, неподдерживаемую метрику или незнакомый производственный
участок уточни через request_clarification. Храни исходный смысл вопроса.
Запрос об отстающих сменах и их браке решается одним вызовом plan_shortfalls;
«только ночные» уточняет текущий отчёт; сравнение с предыдущей неделей вызывает
compare_week с сохранением выборки; порог длительности относится к отдельному
событию простоя. Пользуйся параметрами и перечислениями из описаний функций.
Когда функция вернёт список проверенных фактов и рекомендаций, ответь по схеме
JSON: выбери идентификаторы фактов по вопросу в порядке важности и подходящую
рекомендацию. Отсутствие записей также является результатом. Все выводы,
цифры и зарегистрированные причины определяет результат расчётной функции."""


def _json_object(raw, description):
    if not isinstance(raw, str) or len(raw) > 32_000:
        raise ProviderError(f"Провайдер вернул некорректный формат: {description}.")
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ProviderError(f"Провайдер вернул некорректный JSON: {description}.") from error
    if not isinstance(value, dict):
        raise ProviderError(f"Провайдер вернул некорректный объект: {description}.")
    return value


def _completion(client, common, messages, **options):
    try:
        result = client.chat.completions.create(messages=messages, **common, **options)
    except APIStatusError as error:
        status = error.status_code
        if status in {401, 403}:
            reason = "Проверьте ключ и доступ к выбранной модели."
        elif status in {402, 429}:
            reason = "Проверьте баланс и лимиты у провайдера."
        elif status in {400, 404, 422}:
            reason = "Проверьте адрес API, имя модели и поддержку tools и json_schema."
        else:
            reason = "Повторите запрос позднее."
        raise ProviderError(f"Ошибка LLM-провайдера (HTTP {status}). {reason}") from error
    except APIConnectionError as error:
        raise ProviderError("Не удалось связаться с LLM-провайдером. Проверьте адрес API и сеть.") from error
    except OpenAIError as error:
        raise ProviderError("Клиент OpenAI не получил корректный ответ провайдера.") from error
    if not result.choices:
        raise ProviderError("LLM-провайдер вернул пустой ответ.")
    choice = result.choices[0]
    if choice.finish_reason in {"length", "content_filter"} or getattr(choice.message, "refusal", None):
        raise ProviderError("Провайдер прервал формирование ответа. Попробуйте уточнить вопрос.")
    return choice.message


def _id_list(allowed, description):
    return {
        "type": "array",
        "description": description,
        "items": {"type": "string", "enum": list(allowed)},
        "minItems": 1,
        "maxItems": len(allowed),
    }


def _resolve_ids(selection, catalog):
    if (not isinstance(selection, list) or not selection or len(selection) > len(catalog)
            or any(not isinstance(item, str) or item not in catalog for item in selection)):
        raise ProviderError("Структурированный ответ ссылается на неизвестный результат расчёта.")
    return [catalog[item] for item in dict.fromkeys(selection)]


def _analyze(client, db_path, question, context, model, router):
    messages = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": json.dumps({"question": question, "context": context}, ensure_ascii=False)},
    ]
    common = {"model": model, "tools": [*TOOLS, CLARIFY_TOOL]}
    if router:
        common["extra_body"] = {"provider": {"require_parameters": True}}
    planned = _completion(client, common, messages, tool_choice="required", parallel_tool_calls=False)
    calls = planned.tool_calls or []
    if len(calls) != 1 or calls[0].type != "function" or not calls[0].id:
        raise ProviderError("Ожидался один вызов расчётной функции. Проверьте поддержку function calling.")
    call = calls[0]
    name = call.function.name
    args = _json_object(call.function.arguments, "аргументы функции")
    if name == "request_clarification":
        topic = args.get("topic")
        if set(args) != {"topic"} or not isinstance(topic, str) or topic not in CLARIFY:
            raise ProviderError("Некорректные параметры запроса уточнения.")
        raise ChatClarification(CLARIFY[topic])
    if not any(tool["function"]["name"] == name for tool in TOOLS):
        raise ProviderError("Модель выбрала неизвестную расчётную функцию.")
    report = execute_tool(db_path, name, args, context)

    facts = {f"F{i}": fact for i, fact in enumerate(report["facts"], 1)}
    tips = {"R1": report["recommendation"]}
    evidence = json.dumps({"facts": facts, "recommendations": tips}, ensure_ascii=False)
    # Preserve provider-specific reasoning blocks required by some routed models.
    assistant = {
        "role": "assistant",
        "content": planned.content,
        "tool_calls": [{"id": call.id, "type": "function", "function": {
            "name": name, "arguments": call.function.arguments,
        }}],
    }
    for field in ("reasoning_details", "reasoning_content"):
        value = getattr(planned, field, None)
        if value:
            assistant[field] = value
    messages.extend([assistant, {"role": "tool", "tool_call_id": call.id, "content": evidence}])
    properties = {
        "summary_facts": _id_list(facts, "Коды фактов из результата расчёта в порядке значимости."),
        "recommendations": _id_list(tips, "Коды рекомендаций для текущего отчёта."),
    }
    response_format = {"type": "json_schema", "json_schema": {
        "name": "workshop_findings", "strict": True,
        "schema": {"type": "object", "additionalProperties": False, "properties": properties,
                   "required": list(properties)},
    }}
    final = _completion(client, common, messages, tool_choice="none", response_format=response_format)
    parsed = _json_object(final.content, "структурированный отчёт")
    if set(parsed) != set(properties):
        raise ProviderError("Структура ответа провайдера отличается от JSON-схемы отчёта.")
    return {
        **report,
        "summary": " ".join(_resolve_ids(parsed["summary_facts"], facts)),
        "recommendations": _resolve_ids(parsed["recommendations"], tips),
        "mode": "llm",
        "model": model,
    }


def run_chat(db_path, question, context=None, *, client=None):
    """Plan one read-only analytics call, then select evidence with Structured Outputs."""
    if not isinstance(question, str) or not question.strip() or len(question) > 1500:
        raise ValueError("Введите вопрос длиной от 1 до 1500 символов.")
    filters = validate_filters({} if context is None else context)
    base_url, model, api_key, router = _settings()
    if client is not None:
        return _analyze(client, db_path, question.strip(), filters, model, router)
    if not api_key:
        raise ProviderConfigurationError("Для чата задайте ключ LLM_API_KEY в настройках сервера.")
    with OpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=1) as api:
        return _analyze(api, db_path, question.strip(), filters, model, router)
