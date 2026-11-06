from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Найти рецепт"),KeyboardButton(text="Блюдо дня")],[KeyboardButton(text="Избранное"),KeyboardButton(text="История")],[KeyboardButton(text="Настройки")]], resize_keyboard=True)

def result_keyboard(rid, offset=None):
    rows=[[InlineKeyboardButton(text="Открыть рецепт",callback_data=f"recipe:{rid}")]]
    if offset is not None: rows.append([InlineKeyboardButton(text="Ещё варианты",callback_data=f"more:{offset}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def recipe_keyboard(rid, saved=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"fav:{rid}")],
        [InlineKeyboardButton(text="Приготовил",callback_data=f"cooked:{rid}")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def dish_day_keyboard(rid, saved=False):
    kb = recipe_keyboard(rid, saved)
    kb.inline_keyboard.insert(2, [InlineKeyboardButton(text="Другой вариант",callback_data="daymore")])
    return kb

def list_keyboard(recipes, prefix="recipe"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=r["title"],callback_data=f"{prefix}:{r['id']}")] for r in recipes] + [[InlineKeyboardButton(text="В меню",callback_data="menu")]])

def unknown_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="По ингредиентам",callback_data="hint:ingredients"),InlineKeyboardButton(text="По настроению",callback_data="hint:mood")]])

def settings_keyboard(settings):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Порций: {settings['servings']} (изменить)",callback_data="settings:servings")],
        [InlineKeyboardButton(text="Исключить ингредиент",callback_data="settings:exclude")],
        [InlineKeyboardButton(text="Сбросить исключения",callback_data="settings:clear")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def servings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(i),callback_data=f"servings:{i}") for i in range(1,7)], [InlineKeyboardButton(text="Назад",callback_data="settings:back")]])

def exclusions_keyboard(current):
    options=["лук","молочное","глютен","мясо"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=("✓ " if x in current else "")+x,callback_data=f"exclude:{x}")] for x in options]+[[InlineKeyboardButton(text="Готово",callback_data="settings:back")]])

