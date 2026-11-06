from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Найти рецепт"),KeyboardButton(text="Фильтры")],[KeyboardButton(text="Все рецепты"),KeyboardButton(text="Блюдо дня")],[KeyboardButton(text="Избранное"),KeyboardButton(text="История")],[KeyboardButton(text="Настройки")]], resize_keyboard=True)

def result_keyboard(rid, offset=None):
    rows=[[InlineKeyboardButton(text="Открыть рецепт",callback_data=f"recipe:{rid}")]]
    if offset is not None: rows.append([InlineKeyboardButton(text="Ещё варианты",callback_data=f"more:{offset}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def catalog_keyboard(recipes, offset=0, has_more=False):
    rows = [[InlineKeyboardButton(text=f"{i}. {r['title']}", callback_data=f"catalogopen:{offset}:{r['id']}")]
            for i, r in enumerate(recipes, offset + 1)]
    nav=[]
    if offset > 0:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"catalog:{max(0, offset - 5)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="Другие рецепты →", callback_data=f"catalog:{offset + len(recipes)}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def catalog_card_keyboard(rid, offset=0, saved=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное", callback_data=f"catalogfav:{offset}:{rid}")],
        [InlineKeyboardButton(text="Приготовил", callback_data=f"cooked:{rid}")],
        [InlineKeyboardButton(text="← К списку рецептов", callback_data=f"catalog:{offset}")],
    ])

def all_catalog_keyboard(recipes, offset=0, has_more=False):
    rows=[[InlineKeyboardButton(text=f"{i}. {r['title']}",callback_data=f"allcatalogopen:{offset}:{r['id']}")]
          for i,r in enumerate(recipes,offset+1)]
    nav=[]
    if offset>0: nav.append(InlineKeyboardButton(text="← Назад",callback_data=f"allcatalog:{max(0,offset-5)}"))
    if has_more: nav.append(InlineKeyboardButton(text="Дальше →",callback_data=f"allcatalog:{offset+len(recipes)}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="В меню",callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def all_catalog_card_keyboard(rid, offset=0, saved=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"allcatalogfav:{offset}:{rid}")],
        [InlineKeyboardButton(text="Приготовил",callback_data=f"cooked:{rid}")],
        [InlineKeyboardButton(text="← Все рецепты",callback_data=f"allcatalog:{offset}")],
    ])

def filter_home_keyboard(state):
    def count(key): return len(state[key]) if key != "max_minutes" else int(state[key] is not None)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Продукты · {count('ingredients')}",callback_data="fcat:ingredients"),InlineKeyboardButton(text=f"Способ · {count('methods')}",callback_data="fcat:methods")],
        [InlineKeyboardButton(text=f"Время · {state['max_minutes'] or 'любое'}",callback_data="fcat:time"),InlineKeyboardButton(text=f"Пожелания · {count('moods')}",callback_data="fcat:moods")],
        [InlineKeyboardButton(text="Показать рецепты",callback_data="fapply")],
        [InlineKeyboardButton(text="Сбросить фильтры",callback_data="freset"),InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def filter_options_keyboard(category, options, selected, page=0, page_size=12):
    start=page*page_size; visible=options[start:start+page_size]
    rows=[]
    buttons=[]
    for idx,label in enumerate(visible,start):
        marker="✓ " if label in selected else ""
        buttons.append(InlineKeyboardButton(text=marker+label,callback_data=f"ftoggle:{category}:{idx}"))
        if len(buttons)==2:
            rows.append(buttons); buttons=[]
    if buttons: rows.append(buttons)
    nav=[]
    if page>0: nav.append(InlineKeyboardButton(text="←",callback_data=f"foptpage:{category}:{page-1}"))
    if start+page_size<len(options): nav.append(InlineKeyboardButton(text="→",callback_data=f"foptpage:{category}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="Готово",callback_data="fhome")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def filter_time_keyboard(selected):
    options=[15,20,30,45,60]
    rows=[]
    for i in range(0,len(options),2):
        rows.append([InlineKeyboardButton(text=("✓ " if selected==n else "")+f"До {n} мин.",callback_data=f"ftime:{n}") for n in options[i:i+2]])
    rows.append([InlineKeyboardButton(text="Любое время",callback_data="ftime:0")])
    rows.append([InlineKeyboardButton(text="Готово",callback_data="fhome")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def filtered_results_keyboard(recipes,offset=0,has_more=False):
    rows=[[InlineKeyboardButton(text=f"{i}. {r['title']}",callback_data=f"filteropen:{offset}:{r['id']}")]
          for i,r in enumerate(recipes,offset+1)]
    nav=[]
    if offset>0: nav.append(InlineKeyboardButton(text="← Назад",callback_data=f"filterpage:{max(0,offset-5)}"))
    if has_more: nav.append(InlineKeyboardButton(text="Дальше →",callback_data=f"filterpage:{offset+len(recipes)}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="Изменить фильтры",callback_data="fhome")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def filtered_card_keyboard(rid,offset=0,saved=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"filterfav:{offset}:{rid}")],
        [InlineKeyboardButton(text="Приготовил",callback_data=f"cooked:{rid}")],
        [InlineKeyboardButton(text="← К результатам",callback_data=f"filterpage:{offset}")],
    ])

def recipe_keyboard(rid, saved=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"fav:{rid}")],
        [InlineKeyboardButton(text="Приготовил",callback_data=f"cooked:{rid}")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def dish_day_keyboard(rid, saved=False):
    kb = recipe_keyboard(rid, saved)
    kb.inline_keyboard[0][0].callback_data=f"dayfav:{rid}"
    kb.inline_keyboard.insert(2, [InlineKeyboardButton(text="Другой вариант",callback_data="daymore")])
    return kb

def dish_alternative_keyboard(rid, saved=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"altfav:{rid}")],
        [InlineKeyboardButton(text="Приготовил",callback_data=f"cooked:{rid}")],
        [InlineKeyboardButton(text="Другой вариант",callback_data="daymore")],
        [InlineKeyboardButton(text="К блюду дня для всех",callback_data="dayhome")],
    ])

def list_keyboard(recipes, prefix="recipe"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=r["title"],callback_data=f"{prefix}:{r['id']}")] for r in recipes] + [[InlineKeyboardButton(text="В меню",callback_data="menu")]])

def unknown_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="По ингредиентам",callback_data="hint:ingredients"),InlineKeyboardButton(text="По настроению",callback_data="hint:mood")]])

def settings_keyboard(settings):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Порций: {settings['servings']} (изменить)",callback_data="settings:servings")],
        [InlineKeyboardButton(text=f"Аллергии · {len(settings['allergies'])}",callback_data="settings:allergies"),InlineKeyboardButton(text=f"Не ем · {len(settings['excluded'])}",callback_data="settings:exclude")],
        [InlineKeyboardButton(text="Сбросить ограничения",callback_data="settings:clear")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def servings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(i),callback_data=f"servings:{i}") for i in range(1,7)], [InlineKeyboardButton(text="Назад",callback_data="settings:back")]])

def exclusions_keyboard(current):
    options=["лук","молочное","глютен","мясо"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=("✓ " if x in current else "")+x,callback_data=f"exclude:{x}")] for x in options]+[[InlineKeyboardButton(text="Готово",callback_data="settings:back")]])

def restriction_keyboard(category, options, selected, page=0, page_size=12):
    start=page*page_size; visible=options[start:start+page_size]; rows=[]; pending=[]
    for idx,label in enumerate(visible,start):
        prefix="✓ " if label in selected else ""
        pending.append(InlineKeyboardButton(text=prefix+label,callback_data=f"rtoggle:{category}:{idx}"))
        if len(pending)==2: rows.append(pending); pending=[]
    if pending: rows.append(pending)
    nav=[]
    if page>0: nav.append(InlineKeyboardButton(text="←",callback_data=f"rpage:{category}:{page-1}"))
    if start+page_size<len(options): nav.append(InlineKeyboardButton(text="→",callback_data=f"rpage:{category}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="Готово",callback_data="settings:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

