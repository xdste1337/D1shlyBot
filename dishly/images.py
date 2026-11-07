"""Free, openly licensed recipe illustrations from the Openverse image catalog."""

import logging

import aiohttp

PHOTO_CACHE = {}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=7)

TITLE_HINTS = {
    "сырники": "cottage cheese pancakes", "фрикадель": "meatballs", "котлет": "cutlets",
    "маффин": "muffins", "кекс": "cake", "печень": "cookies", "пирог": "pie",
    "пирож": "pastry", "булочк": "buns", "круассан": "croissant", "блин": "pancakes",
    "олад": "pancakes", "чизкейк": "cheesecake", "торт": "cake", "бисквит": "sponge cake",
    "крамбл": "crumble", "пицц": "pizza", "хумус": "hummus", "омлет": "omelette",
    "паста": "pasta", "макарон": "pasta", "лапша": "noodles", "суп": "soup",
    "салат": "salad", "каша": "porridge", "смузи": "smoothie", "тост": "toast",
    "пудинг": "pudding", "рагу": "stew", "запеканк": "casserole", "хлеб": "bread",
}

INGREDIENT_HINTS = {
    "курица": "chicken", "фарш": "ground meat", "котлеты": "meat", "говядина": "beef",
    "рыба": "fish", "креветки": "shrimp", "яйца": "egg", "макароны": "pasta",
    "лапша": "noodles", "мука": "baking", "яблоко": "apple", "груша": "pear",
    "ягоды": "berries", "вишня": "cherry", "шоколад": "chocolate", "тыква": "pumpkin",
    "картофель": "potato", "грибы": "mushroom", "гречка": "buckwheat",
    "рис": "rice", "брокколи": "broccoli", "кабачок": "zucchini", "баклажан": "eggplant",
    "нут": "chickpea", "фасоль": "beans", "чечевица": "lentils", "сыр": "cheese",
    "творог": "cottage cheese", "банан": "banana", "апельсин": "orange", "свёкла": "beet",
    "перловка": "barley", "овсянка": "oatmeal", "капуста": "cabbage", "помидоры": "tomato",
}


def image_search_query(recipe):
    title = recipe["title"].casefold()
    dish = next((english for russian, english in TITLE_HINTS.items() if russian in title), "")
    ingredients = []
    for ingredient in recipe["ingredients"]:
        english = INGREDIENT_HINTS.get(ingredient["name"])
        if english and english not in ingredients:
            ingredients.append(english)
        if len(ingredients) == 2:
            break
    words = ([dish] if dish else []) + ingredients
    return " ".join(words[:3]) or "food dish"


def _caption(image):
    title = (image.get("title") or "Food photo")[:90]
    creator = (image.get("creator") or "author not listed")[:70]
    license_code = (image.get("license") or "").casefold()
    license_names = {
        "by": "CC BY", "by-sa": "CC BY-SA", "cc0": "CC0",
        "pdm": "Public Domain Mark", "publicdomain": "Public domain",
    }
    license_version = image.get("license_version")
    license_text = license_names.get(license_code, "CC " + (license_code.upper() or "license details"))
    if license_version and license_code in {"by", "by-sa"}:
        license_text += " " + str(license_version)
    license_url = image.get("license_url") or ""
    landing = image.get("foreign_landing_url") or image.get("detail_url") or ""
    caption = f"Фото-иллюстрация: {title}\nАвтор: {creator} · {license_text}"
    if license_url:
        caption += f" · {license_url}"
    if landing:
        caption += f"\nИсточник: {landing}"
    return caption[:1024]


async def find_recipe_photo(recipe):
    """Return (image bytes, attribution caption), or None when no usable image is found."""
    recipe_id = recipe["id"]
    if recipe_id in PHOTO_CACHE:
        return PHOTO_CACHE[recipe_id]

    query = image_search_query(recipe)
    headers = {"User-Agent": "DishlyTelegramBot/1.0 (openverse image lookup)"}
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT, headers=headers) as session:
            async with session.get(
                "https://api.openverse.org/v1/images/",
                params={"q": query, "page_size": 5, "filter_dead": "true", "license_type": "commercial,modification"},
            ) as response:
                if response.status != 200:
                    logging.info("Openverse image search returned HTTP %s", response.status)
                    return None
                data = await response.json()

            image = next((result for result in data.get("results", []) if result.get("thumbnail") or result.get("url")), None)
            if not image:
                return None
            async with session.get(image.get("thumbnail") or image["url"]) as response:
                if response.status != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
                    return None
                content = await response.read()
                if not content or len(content) > 10 * 1024 * 1024:
                    return None

        result = (content, _caption(image))
        PHOTO_CACHE[recipe_id] = result
        return result
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        logging.info("Openverse image lookup failed: %s", type(exc).__name__)
        return None
