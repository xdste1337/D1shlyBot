from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def recipe_feedback_buttons(rid, feedback=None):
    feedback=feedback or {}
    liked=bool(feedback.get("liked")); not_suggest=bool(feedback.get("not_suggest"))
    return [
        [InlineKeyboardButton(text="👍 Понравилось ✓" if liked else "👍 Понравилось",callback_data=f"feedback:liked:{rid}")],
        [InlineKeyboardButton(text="↩️ Вернуть в подбор" if not_suggest else "🚫 Не предлагать",callback_data=f"feedback:not_suggest:{rid}")],
    ]

def cooked_button(rid, feedback=None):
    cooked=bool((feedback or {}).get("cooked"))
    return InlineKeyboardButton(text="✅ Приготовил" if cooked else "🍳 Приготовил",callback_data=f"cooked:{rid}")

def report_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена",callback_data="report:cancel")]])

def plus_keyboard(active=False, accepted=False, payments_ready=False, canceled=False):
    rows=[]
    if active:
        if not canceled:
            rows.append([InlineKeyboardButton(text="Отключить автопродление",callback_data="plus:cancel")])
        rows.append([InlineKeyboardButton(text="👩‍🍳 Спросить советчика",callback_data="advisor:start")])
    elif payments_ready:
        rows.append([InlineKeyboardButton(text="⭐ Открыть Dishly Plus",callback_data="plus:terms" if not accepted else "plus:subscribe")])
    else:
        rows.append([InlineKeyboardButton(text="Проверить настройку Plus",callback_data="plus:refresh")])
    rows.append([InlineKeyboardButton(text="В меню",callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def plus_terms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принимаю условия и продолжить",callback_data="plus:accept")],
        [InlineKeyboardButton(text="Назад",callback_data="plus:home")],
    ])

def advisor_terms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Прочитал(а), продолжить",callback_data="advisor:terms_accept")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def advisor_test_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩‍🍳 Спросить советчика",callback_data="advisor:start")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def admin_access_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Код на 7 дней",callback_data="admin:key:7"),InlineKeyboardButton(text="🎟 Код на 30 дней",callback_data="admin:key:30")],
        [InlineKeyboardButton(text="🎟 Код на 90 дней",callback_data="admin:key:90")],
        [InlineKeyboardButton(text="🗂 Неиспользованные коды",callback_data="admin:keys")],
        [InlineKeyboardButton(text="👥 Доступы по кодам",callback_data="admin:users")],
        [InlineKeyboardButton(text="🏠 Главное меню",callback_data="menu")],
    ])

def admin_access_users_keyboard(users):
    rows=[[InlineKeyboardButton(text=f"🚫 Отозвать {uid}",callback_data=f"admin:revoke:{uid}")] for uid in users]
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель",callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def advisor_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Завершить консультацию",callback_data="advisor:stop")]])

def advisor_recipes_keyboard(recipes):
    rows=[[InlineKeyboardButton(text=f"📖 {recipe['title']}",callback_data=f"recipe:{recipe['id']}")] for recipe in recipes]
    rows.append([InlineKeyboardButton(text="Задать ещё вопрос",callback_data="advisor:start")])
    rows.append([InlineKeyboardButton(text="Завершить",callback_data="advisor:stop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🍳 Подобрать блюдо"),KeyboardButton(text="🔎 Фильтры")],
        [KeyboardButton(text="📚 Каталог"),KeyboardButton(text="🍲 Блюдо дня")],
        [KeyboardButton(text="✨ Ещё")],
    ],resize_keyboard=True)

def first_start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настроить предпочтения",callback_data="firststart:settings")],
        [InlineKeyboardButton(text="🍳 Сразу к рецептам",callback_data="firststart:skip")],
    ])

def more_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👩‍🍳 ИИ-советчик")],
        [KeyboardButton(text="🧺 Из моих продуктов")],
        [KeyboardButton(text="📅 План на 3 дня")],
        [KeyboardButton(text="⭐ Избранное"),KeyboardButton(text="🕘 История")],
        [KeyboardButton(text="⚙️ Настройки"),KeyboardButton(text="❔ Помощь")],
        [KeyboardButton(text="🏠 Главное меню")],
    ],resize_keyboard=True)

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

def catalog_card_keyboard(rid, offset=0, saved=False, feedback=None):
    rows=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное", callback_data=f"catalogfav:{offset}:{rid}")],
        [cooked_button(rid,feedback)],
    ]
    rows.extend(recipe_feedback_buttons(rid,feedback))
    rows.append([InlineKeyboardButton(text="⚠️ Сообщить о проблеме",callback_data=f"report:start:{rid}")])
    rows.append([InlineKeyboardButton(text="← К списку рецептов", callback_data=f"catalog:{offset}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def all_catalog_keyboard(recipes, offset=0, has_more=False):
    rows=[[InlineKeyboardButton(text=f"{i}. {r['title']}",callback_data=f"allcatalogopen:{offset}:{r['id']}")]
          for i,r in enumerate(recipes,offset+1)]
    nav=[]
    if offset>0: nav.append(InlineKeyboardButton(text="← Назад",callback_data=f"allcatalog:{max(0,offset-5)}"))
    if has_more: nav.append(InlineKeyboardButton(text="Дальше →",callback_data=f"allcatalog:{offset+len(recipes)}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="В меню",callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def all_catalog_card_keyboard(rid, offset=0, saved=False, feedback=None):
    rows=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"allcatalogfav:{offset}:{rid}")],
        [cooked_button(rid,feedback)],
    ]
    rows.extend(recipe_feedback_buttons(rid,feedback))
    rows.append([InlineKeyboardButton(text="⚠️ Сообщить о проблеме",callback_data=f"report:start:{rid}")])
    rows.append([InlineKeyboardButton(text="← Все рецепты",callback_data=f"allcatalog:{offset}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

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
        shown="Полезное / ПП" if category=="moods" and label=="полезное" else label
        buttons.append(InlineKeyboardButton(text=marker+shown,callback_data=f"ftoggle:{category}:{idx}"))
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

def filtered_card_keyboard(rid,offset=0,saved=False,feedback=None):
    rows=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"filterfav:{offset}:{rid}")],
        [cooked_button(rid,feedback)],
    ]
    rows.extend(recipe_feedback_buttons(rid,feedback))
    rows.append([InlineKeyboardButton(text="⚠️ Сообщить о проблеме",callback_data=f"report:start:{rid}")])
    rows.append([InlineKeyboardButton(text="← К результатам",callback_data=f"filterpage:{offset}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def recipe_keyboard(rid, saved=False, feedback=None):
    rows=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"fav:{rid}")],
        [cooked_button(rid,feedback)],
    ]
    rows.extend(recipe_feedback_buttons(rid,feedback))
    rows.append([InlineKeyboardButton(text="⚠️ Сообщить о проблеме",callback_data=f"report:start:{rid}")])
    rows.append([InlineKeyboardButton(text="В меню",callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def dish_day_keyboard(rid, saved=False, feedback=None):
    kb = recipe_keyboard(rid, saved, feedback)
    kb.inline_keyboard[0][0].callback_data=f"dayfav:{rid}"
    kb.inline_keyboard.insert(2, [InlineKeyboardButton(text="Другой вариант",callback_data="daymore")])
    return kb

def dish_alternative_keyboard(rid, saved=False, feedback=None):
    rows=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"altfav:{rid}")],
        [cooked_button(rid,feedback)],
    ]
    rows.extend(recipe_feedback_buttons(rid,feedback))
    rows.extend([
        [InlineKeyboardButton(text="⚠️ Сообщить о проблеме",callback_data=f"report:start:{rid}")],
        [InlineKeyboardButton(text="Другой вариант",callback_data="daymore")],
        [InlineKeyboardButton(text="К блюду дня для всех",callback_data="dayhome")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def list_keyboard(recipes, prefix="recipe"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=r["title"],callback_data=f"{prefix}:{r['id']}")] for r in recipes] + [[InlineKeyboardButton(text="В меню",callback_data="menu")]])

def meal_plan_keyboard(recipes):
    rows=[[InlineKeyboardButton(text=f"📖 Открыть блюдо {index+1}",callback_data=f"mealplan:open:{index}")] for index,_ in enumerate(recipes)]
    rows.extend([
        [InlineKeyboardButton(text="🛒 Список покупок",callback_data="mealplan:shopping")],
        [InlineKeyboardButton(text="🔄 Новый план",callback_data="mealplan:refresh")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def shopping_list_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← К плану",callback_data="mealplan:back")]])

def meal_plan_recipe_keyboard(index, rid, saved=False, feedback=None):
    rows=[
        [InlineKeyboardButton(text="Убрать из избранного" if saved else "В избранное",callback_data=f"mealplan:fav:{index}")],
        [cooked_button(rid,feedback)],
    ]
    rows.extend(recipe_feedback_buttons(rid,feedback))
    rows.append([InlineKeyboardButton(text="⚠️ Сообщить о проблеме",callback_data=f"report:start:{rid}")])
    rows.append([InlineKeyboardButton(text="← К плану",callback_data="mealplan:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def meal_plan_unavailable_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В меню",callback_data="menu")]])

def unknown_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="По ингредиентам",callback_data="hint:ingredients"),InlineKeyboardButton(text="По настроению",callback_data="hint:mood")]])

def pantry_prompt_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена",callback_data="pantry:cancel")]])

def setup_reset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, пройти настройку заново",callback_data="setupreset:confirm")],
        [InlineKeyboardButton(text="Отмена",callback_data="setupreset:cancel")],
    ])

def settings_keyboard(settings):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Порций: {settings['servings']} (изменить)",callback_data="settings:servings")],
        [InlineKeyboardButton(text=f"Аллергии · {len(settings['allergies'])}",callback_data="settings:allergies"),InlineKeyboardButton(text=f"Не ем · {len(settings['excluded'])}",callback_data="settings:exclude")],
        [InlineKeyboardButton(text=f"🍳 Техника · {len(settings['equipment']) or 'не ограничивать'}",callback_data="settings:equipment")],
        [InlineKeyboardButton(text="Сбросить ограничения",callback_data="settings:clear")],
        [InlineKeyboardButton(text="🔄 Пройти настройку заново",callback_data="settings:restart_setup")],
        [InlineKeyboardButton(text="В меню",callback_data="menu")],
    ])

def equipment_keyboard(options, selected):
    rows=[]; pending=[]
    for index,label in enumerate(options):
        prefix="✓ " if label in selected else ""
        pending.append(InlineKeyboardButton(text=prefix+label,callback_data=f"equipment:{index}"))
        if len(pending)==2:
            rows.append(pending); pending=[]
    if pending: rows.append(pending)
    rows.append([InlineKeyboardButton(text="Готово",callback_data="settings:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

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

