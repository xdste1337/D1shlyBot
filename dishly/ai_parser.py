"""Optional AI intent extraction. The model only returns search filters, never recipes."""
import json
import logging

from openai import AsyncOpenAI

from .data.vocabulary import INGREDIENTS, TAGS
from .parser import ParsedQuery, parse_query

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "excluded": {"type": "array", "items": {"type": "string"}},
        "max_minutes": {"type": ["integer", "null"]},
        "understood": {"type": "boolean"},
    },
    "required": ["ingredients", "tags", "excluded", "max_minutes", "understood"],
    "additionalProperties": False,
}

async def analyze_query(text: str, api_key: str | None, model: str = "gpt-4o-mini") -> ParsedQuery:
    """Understand natural-language intent and constrain it to the bot's local vocabulary."""
    local = parse_query(text)
    if not api_key:
        return local
    allowed_ingredients = sorted(INGREDIENTS)
    allowed_tags = sorted(TAGS)
    allowed_exclusions = sorted(set(INGREDIENTS) | {"молочное", "глютен", "мясо", "острое"})
    client = AsyncOpenAI(api_key=api_key, timeout=15, max_retries=1)
    try:
        response = await client.responses.create(
            model=model,
            store=False,
            input=[
                {"role": "system", "content": (
                    "Ты извлекаешь фильтры для поиска еды в готовом каталоге. Не составляй рецепты, "
                    "не добавляй ингредиенты или ограничения, которых пользователь не называл. "
                    "Верни только значения из разрешённых списков. Разговорные фразы вроде 'чото вкусного' "
                    "понимай по смыслу; 'вкусное' само по себе не означает сладкое. Неясный текст помечай understood=false. "
                    f"Ингредиенты: {allowed_ingredients}. Теги: {allowed_tags}. Исключения: {allowed_exclusions}. "
                    "max_minutes указывай только при явном времени или просьбе 'быстро'; для 'быстро' ставь 20."
                )},
                {"role": "user", "content": text[:500]},
            ],
            text={"format": {"type": "json_schema", "name": "dishly_query", "strict": True, "schema": SCHEMA}},
        )
        payload = json.loads(response.output_text)
        ingredients = set(payload["ingredients"]) & set(allowed_ingredients)
        tags = set(payload["tags"]) & set(allowed_tags)
        excluded = set(payload["excluded"]) & set(allowed_exclusions)
        minutes = payload["max_minutes"]
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 300:
            minutes = None
        ingredients |= local.ingredients
        tags |= local.tags
        excluded |= local.excluded
        minutes = minutes or local.max_minutes
        return ParsedQuery(ingredients - excluded, tags, excluded, minutes, text[:500])
    except Exception as exc:
        logger.warning("AI query parsing unavailable (%s); using local parser", type(exc).__name__)
        return local
    finally:
        await client.close()
