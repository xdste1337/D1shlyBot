import logging
import random
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from .config import load_config
from .database import Database
from .keyboards import main_menu, recipe_keyboard, dish_day_keyboard, dish_alternative_keyboard, catalog_keyboard, catalog_card_keyboard, all_catalog_keyboard, all_catalog_card_keyboard, filter_home_keyboard, filter_options_keyboard, filter_time_keyboard, filtered_results_keyboard, filtered_card_keyboard, list_keyboard, unknown_keyboard, settings_keyboard, servings_keyboard, restriction_keyboard
from .parser import parse_query
from .search import blocked, filter_recipes, rank_recipes, canonical

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
db = None
queries = {}
filter_states = {}
filter_results = {}
MAX_INPUT = 500
FILTER_METHODS = ["микроволновка","аэрогриль","кастрюля","сковорода","духовка","без готовки"]
FILTER_MOODS = ["сладкое","сытное","полезное","вегетарианское","завтрак","обед","ужин","суп","салат","перекус"]
ALLERGY_OPTIONS = ["молочное","яйца","глютен","рыба","мясо","орехи","арахис","соя","кунжут","морепродукты"]

def user_restrictions(settings):
    return sorted(set(settings["excluded"]) | set(settings["allergies"]))

def recipe_text(recipe, servings=None):
    ratio = (servings or recipe["servings"]) / recipe["servings"]
    lines=[f"🍽 <b>{recipe['title']}</b>",recipe["description"],f"⏱ {recipe['minutes']} мин. · {recipe['difficulty']} · {servings or recipe['servings']} порц.",f"Способ: {recipe['method']}"]
    lines += ["", "<b>Ингредиенты</b>"]
    for i in recipe["ingredients"]:
        amount = round(i["amount"]*ratio, 1)
        lines.append(f"• {i['name']}: {amount:g} {i['unit']}" + (" (по желанию)" if i.get("optional") else ""))
    lines += ["", "<b>Приготовление</b>"]
    lines += [f"{n}. {step}" for n,step in enumerate(recipe["steps"],1)]
    lines += ["", recipe["source"]]
    return "\n".join(lines)

async def show_search(message, offset=0, user_id=None, edit=False):
    uid=user_id or message.from_user.id
    query,raw=queries.get(uid,(None,""))
    if not query: return
    settings=db.settings(uid)
    all_results=rank_recipes(db.recipes(),query,user_restrictions(settings),offset=0,limit=100)
    page=all_results[offset:offset+5]
    if not page:
        text="По этому запросу больше рецептов нет. Попробуй другие продукты или пожелания."
        if edit: await message.edit_text(text,reply_markup=None)
        else: await message.answer(text,reply_markup=main_menu())
        return
    lines=[f"📚 <b>Каталог рецептов</b> · запрос: «{raw[:80]}»",""]
    for i,(_,recipe,*_) in enumerate(page,offset+1):
        lines.append(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин.")
    markup=catalog_keyboard([row[1] for row in page],offset,offset+len(page)<len(all_results))
    text="\n".join(lines)
    if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
    else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

async def show_all_catalog(message, offset=0, user_id=None, edit=False):
    recipes=sorted(db.recipes(),key=lambda recipe:recipe["title"].casefold())
    page=recipes[offset:offset+5]
    if not page:
        text="В каталоге пока нет рецептов."
        if edit: await message.edit_text(text,reply_markup=None)
        else: await message.answer(text,reply_markup=main_menu())
        return
    start=offset+1; end=offset+len(page)
    text=f"📚 <b>Все рецепты</b> · {start}–{end} из {len(recipes)}\n\n"
    text+="\n".join(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин." for i,recipe in enumerate(page,start))
    markup=all_catalog_keyboard(page,offset,end<len(recipes))
    if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
    else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

async def main():
    global db
    config=load_config(); db=Database(config.database_path)
    bot=Bot(config.bot_token); dp=Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message):
        db.ensure_user(message.from_user.id)
        await message.answer("Привет! Я Dishly — помогу выбрать блюдо по продуктам или настроению. Ищу только в каталоге рецептов. Напиши, например: «яйца, помидоры» или «быстрое без духовки».",reply_markup=main_menu())

    @dp.message(Command("help"))
    async def help_cmd(message):
        await message.answer("Напиши продукты или пожелания: «сытное из курицы без духовки». Можно открыть рецепт кнопкой из выдачи.",reply_markup=main_menu())

    @dp.message(F.text)
    async def text_handler(message: Message):
        text=message.text.strip()
        if text in {"Найти рецепт","🔎 Найти рецепт"}:
            await message.answer("Напиши продукты или пожелание, например: «есть яйца и помидоры» или «что-нибудь сладкое до 20 минут»."); return
        if text=="Все рецепты":
            await show_all_catalog(message); return
        if text=="Фильтры":
            await show_filter_home(message,message.from_user.id); return
        if text=="Блюдо дня":
            await dish_day(message); return
        if text=="Избранное":
            await show_list(message,"Избранное",db.favorites(message.from_user.id)); return
        if text=="История":
            await show_list(message,"Недавно просмотренные",db.history(message.from_user.id)); return
        if text=="Настройки":
            await show_settings(message); return
        if len(text)>MAX_INPUT:
            await message.answer(f"Запрос слишком длинный. Сократи его до {MAX_INPUT} символов."); return
        query=parse_query(text)
        if not query.understood:
            await message.answer("Не понял запрос. Напиши продукты или пожелание вроде «быстрое блюдо без духовки».",reply_markup=unknown_keyboard()); return
        queries[message.from_user.id]=(query,text)
        await show_search(message)

    async def show_list(message,title,recipes):
        if not recipes: await message.answer(f"{title}: пока пусто.",reply_markup=main_menu()); return
        await message.answer(title+":",reply_markup=list_keyboard(recipes))

    async def show_settings(message):
        s=db.settings(message.from_user.id)
        info=[]
        info.append("Аллергии: "+(", ".join(s["allergies"]) or "не указаны"))
        info.append("Не ем: "+(", ".join(s["excluded"]) or "ничего не исключено"))
        await message.answer("Настройки\n"+"\n".join(info),reply_markup=settings_keyboard(s))

    async def show_restrictions(message,uid,category,page=0):
        s=db.settings(uid)
        if category=="allergies":
            options=ALLERGY_OPTIONS; selected=set(s["allergies"])
            title="Выбери аллергены. Рецепты с ними будут исключены по составу и аллергенам каталога. Возможные следы аллергенов каталог не описывает."
        else:
            options=sorted(set(ingredient_filter_options())|{"молочное","глютен","мясо"}); selected=set(s["excluded"])
            title="Отметь продукты, которые не хочешь видеть в рецептах."
        await message.edit_text(title+"\nОтмечено: "+(", ".join(sorted(selected)) or "ничего"),reply_markup=restriction_keyboard(category,options,selected,page))

    def get_filter_state(uid):
        return filter_states.setdefault(uid,{"ingredients":set(),"methods":set(),"moods":set(),"max_minutes":None})

    def ingredient_filter_options():
        return sorted({canonical(item["name"]) for recipe in db.recipes() for item in recipe["ingredients"] if not item.get("optional",False)})

    def filter_options(category):
        if category=="ingredients": return ingredient_filter_options()
        if category=="methods": return FILTER_METHODS
        if category=="moods": return FILTER_MOODS
        return []

    async def show_filter_home(message,uid,edit=False):
        state=get_filter_state(uid)
        selected=[]
        for key,title in (("ingredients","продукты"),("methods","способ"),("moods","пожелания")):
            if state[key]: selected.append(title+": "+", ".join(sorted(state[key])))
        if state["max_minutes"]: selected.append(f"время: до {state['max_minutes']} мин.")
        summary="\n".join(selected) if selected else "Пока фильтры не выбраны — покажу весь каталог."
        text="🔎 <b>Фильтры поиска</b>\nВыбери условия. Между разделами действует И: результат должен подходить всем выбранным фильтрам.\n\n"+summary
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=filter_home_keyboard(state))
        else: await message.answer(text,parse_mode="HTML",reply_markup=filter_home_keyboard(state))

    async def show_filter_category(message,uid,category,page=0):
        state=get_filter_state(uid)
        if category=="time":
            text="Выбери максимальное время готовки:"
            markup=filter_time_keyboard(state["max_minutes"])
        else:
            titles={"ingredients":"Выбери продукты. Будут показаны блюда, в которых есть каждый выбранный продукт:","methods":"Выбери способ приготовления:","moods":"Выбери пожелания к блюду:"}
            options=filter_options(category)
            selected=state[category]
            text=titles[category]+f"\nВыбрано: {', '.join(sorted(selected)) if selected else 'ничего'}"
            markup=filter_options_keyboard(category,options,selected,page)
        await message.edit_text(text,reply_markup=markup)

    async def show_filtered_results(message,uid,offset=0,edit=True):
        state=get_filter_state(uid); settings=db.settings(uid)
        recipes=filter_recipes(db.recipes(),state["ingredients"],state["methods"]|state["moods"],state["max_minutes"],user_restrictions(settings))
        filter_results[uid]=[recipe["id"] for recipe in recipes]
        if not recipes:
            text="По всем выбранным условиям рецептов не нашлось. Попробуй убрать один из фильтров."
            if edit: await message.edit_text(text,reply_markup=filter_home_keyboard(state))
            else: await message.answer(text,reply_markup=filter_home_keyboard(state))
            return
        ids=filter_results[uid][offset:offset+5]
        page=[db.get_recipe(rid) for rid in ids]
        text=f"📚 <b>Рецепты по фильтрам</b> · {offset+1}–{offset+len(page)} из {len(recipes)}\n\n"
        text+="\n".join(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин." for i,recipe in enumerate(page,offset+1))
        markup=filtered_results_keyboard(page,offset,offset+len(page)<len(recipes))
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

    async def dish_day(message, user_id=None, edit=False):
        uid=user_id or message.from_user.id; settings=db.settings(uid)
        rid=db.shared_dish_today()
        if not rid:
            candidates=db.recipes()
            if not candidates: return
            recipe=random.choice(candidates); db.set_shared_dish_today(recipe["id"]); rid=recipe["id"]
        recipe=db.get_recipe(rid); db.add_history(uid,rid)
        if blocked(recipe,user_restrictions(settings)):
            text=(f"🍲 <b>Блюдо дня для всех</b>\n\n<b>{recipe['title']}</b> · {recipe['minutes']} мин.\n"
                  "В рецепте есть продукт из твоих исключений. Чтобы подобрать другой подходящий вариант, воспользуйся поиском.")
        else:
            text="🍲 <b>Блюдо дня для всех</b>\n\n"+recipe_text(recipe,settings["servings"])
        markup=dish_day_keyboard(recipe["id"],recipe in db.favorites(uid))
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

    async def show_another_dish(message, user_id, edit=True):
        settings=db.settings(user_id)
        daily_id=db.shared_dish_today()
        seen=db.user_alternatives_today(user_id)
        candidates=[r for r in db.recipes() if r["id"] != daily_id and r["id"] not in seen and not blocked(r,user_restrictions(settings))]
        if not candidates:
            text="На сегодня больше подходящих вариантов нет. Общее блюдо дня осталось прежним."
            if edit: await message.edit_text(text,reply_markup=None)
            else: await message.answer(text,reply_markup=main_menu())
            return
        recipe=random.choice(candidates); db.mark_user_alternative(user_id,recipe["id"]); db.add_history(user_id,recipe["id"])
        saved=any(r["id"]==recipe["id"] for r in db.favorites(user_id))
        text="🍽 <b>Другой вариант для тебя</b>\n\n"+recipe_text(recipe,settings["servings"])
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=dish_alternative_keyboard(recipe["id"],saved))
        else: await message.answer(text,parse_mode="HTML",reply_markup=dish_alternative_keyboard(recipe["id"],saved))

    @dp.callback_query(F.data=="daymore")
    async def daymore_handler(call):
        await show_another_dish(call.message,call.from_user.id)
        await call.answer()

    @dp.callback_query(F.data=="dayhome")
    async def back_to_shared_dish(call):
        await dish_day(call.message,call.from_user.id,edit=True)
        await call.answer("Общее блюдо дня не менялось")

    @dp.callback_query(F.data.startswith("altfav:"))
    async def alternative_favorite(call):
        rid=call.data.split(":",1)[1]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=dish_alternative_keyboard(rid,saved))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("dayfav:"))
    async def shared_dish_favorite(call):
        rid=call.data.split(":",1)[1]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=dish_day_keyboard(rid,saved))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("catalogopen:"))
    async def open_catalog_recipe(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        recipe=db.get_recipe(rid)
        if not recipe: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        saved=any(x["id"]==rid for x in db.favorites(call.from_user.id))
        await call.message.edit_text(recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=catalog_card_keyboard(rid,offset,saved))
        await call.answer()

    @dp.callback_query(F.data.startswith("catalog:"))
    async def catalog_page(call):
        offset=int(call.data.split(":")[1])
        await show_search(call.message,offset,user_id=call.from_user.id,edit=True)
        await call.answer()

    @dp.callback_query(F.data.startswith("catalogfav:"))
    async def catalog_favorite(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=catalog_card_keyboard(rid,offset,saved))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("allcatalogopen:"))
    async def open_all_catalog_recipe(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        recipe=db.get_recipe(rid)
        if not recipe: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        saved=any(x["id"]==rid for x in db.favorites(call.from_user.id))
        await call.message.edit_text(recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=all_catalog_card_keyboard(rid,offset,saved))
        await call.answer()

    @dp.callback_query(F.data.startswith("allcatalog:"))
    async def all_catalog_page(call):
        offset=int(call.data.split(":")[1])
        await show_all_catalog(call.message,offset,user_id=call.from_user.id,edit=True)
        await call.answer()

    @dp.callback_query(F.data.startswith("allcatalogfav:"))
    async def all_catalog_favorite(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=all_catalog_card_keyboard(rid,offset,saved))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("fcat:"))
    async def filter_category(call):
        await show_filter_category(call.message,call.from_user.id,call.data.split(":",1)[1])
        await call.answer()

    @dp.callback_query(F.data.startswith("foptpage:"))
    async def filter_options_page(call):
        _,category,page=call.data.split(":")
        await show_filter_category(call.message,call.from_user.id,category,int(page))
        await call.answer()

    @dp.callback_query(F.data.startswith("ftoggle:"))
    async def toggle_filter(call):
        _,category,index=call.data.split(":")
        index=int(index); options=filter_options(category)
        if index<0 or index>=len(options): await call.answer("Фильтр не найден",show_alert=True); return
        value=options[index]; selected=get_filter_state(call.from_user.id)[category]
        if value in selected: selected.remove(value)
        else:
            if category=="methods": selected.clear()
            selected.add(value)
        await show_filter_category(call.message,call.from_user.id,category,index//12)
        await call.answer()

    @dp.callback_query(F.data.startswith("ftime:"))
    async def set_filter_time(call):
        value=int(call.data.split(":")[1]); get_filter_state(call.from_user.id)["max_minutes"]=value or None
        await show_filter_category(call.message,call.from_user.id,"time")
        await call.answer()

    @dp.callback_query(F.data=="fhome")
    async def filter_home(call):
        await show_filter_home(call.message,call.from_user.id,edit=True)
        await call.answer()

    @dp.callback_query(F.data=="freset")
    async def reset_filters(call):
        filter_states[call.from_user.id]={"ingredients":set(),"methods":set(),"moods":set(),"max_minutes":None}
        await show_filter_home(call.message,call.from_user.id,edit=True)
        await call.answer("Фильтры сброшены")

    @dp.callback_query(F.data=="fapply")
    async def apply_filters(call):
        await show_filtered_results(call.message,call.from_user.id,edit=True)
        await call.answer()

    @dp.callback_query(F.data.startswith("filterpage:"))
    async def filtered_page(call):
        offset=int(call.data.split(":")[1])
        await show_filtered_results(call.message,call.from_user.id,offset,edit=True)
        await call.answer()

    @dp.callback_query(F.data.startswith("filteropen:"))
    async def open_filtered_recipe(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        recipe=db.get_recipe(rid)
        if not recipe: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        saved=any(item["id"]==rid for item in db.favorites(call.from_user.id))
        await call.message.edit_text(recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=filtered_card_keyboard(rid,offset,saved))
        await call.answer()

    @dp.callback_query(F.data.startswith("filterfav:"))
    async def filtered_favorite(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=filtered_card_keyboard(rid,offset,saved))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("recipe:"))
    async def open_recipe(call):
        rid=call.data.split(":",1)[1]; r=db.get_recipe(rid)
        if not r: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        fav=any(x["id"]==rid for x in db.favorites(call.from_user.id))
        await call.message.answer(recipe_text(r,settings["servings"]),parse_mode="HTML",reply_markup=recipe_keyboard(rid,fav)); await call.answer()

    @dp.callback_query(F.data.startswith("fav:"))
    async def favorite(call):
        rid=call.data.split(":",1)[1]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")
        await call.message.edit_reply_markup(reply_markup=recipe_keyboard(rid,saved))

    @dp.callback_query(F.data.startswith("cooked:"))
    async def cooked(call):
        await call.answer("Приятного аппетита!",show_alert=False)

    @dp.callback_query(F.data=="menu")
    async def menu(call):
        await call.message.answer("Главное меню",reply_markup=main_menu()); await call.answer()

    @dp.callback_query(F.data.startswith("hint:"))
    async def hint(call):
        prompt="Напиши продукты через запятую, например: яйца, помидоры." if call.data.endswith("ingredients") else "Напиши пожелание, например: быстрое, сытное или без духовки."
        await call.message.answer(prompt); await call.answer()

    @dp.callback_query(F.data.startswith("settings:"))
    async def settings_action(call):
        action=call.data.split(":")[1]; s=db.settings(call.from_user.id)
        if action in ("servings",): await call.message.edit_text("Выбери число порций:",reply_markup=servings_keyboard())
        elif action in ("exclude","allergies"): await show_restrictions(call.message,call.from_user.id,action)
        elif action=="clear":
            db.set_excluded(call.from_user.id,[]); db.set_allergies(call.from_user.id,[])
            await call.message.edit_text("Аллергии и исключённые продукты сброшены.",reply_markup=settings_keyboard(db.settings(call.from_user.id)))
        elif action=="back":
            info="Настройки\nАллергии: "+(", ".join(s["allergies"]) or "не указаны")+"\nНе ем: "+(", ".join(s["excluded"]) or "ничего не исключено")
            await call.message.edit_text(info,reply_markup=settings_keyboard(s))
        await call.answer()

    @dp.callback_query(F.data.startswith("servings:"))
    async def set_servings(call):
        n=int(call.data.split(":")[1]); db.set_servings(call.from_user.id,n); await call.message.edit_text(f"Количество порций: {n}.",reply_markup=settings_keyboard(db.settings(call.from_user.id))); await call.answer()

    @dp.callback_query(F.data.startswith("exclude:"))
    async def toggle_exclusion(call):
        x=call.data.split(":",1)[1]; s=db.settings(call.from_user.id); values=set(s["excluded"])
        if x in values: values.remove(x)
        else: values.add(x)
        db.set_excluded(call.from_user.id,sorted(values)); await call.message.edit_reply_markup(reply_markup=exclusions_keyboard(values)); await call.answer()

    @dp.callback_query(F.data.startswith("rpage:"))
    async def restriction_page(call):
        _,category,page=call.data.split(":")
        await show_restrictions(call.message,call.from_user.id,category,int(page)); await call.answer()

    @dp.callback_query(F.data.startswith("rtoggle:"))
    async def toggle_restriction(call):
        _,category,index=call.data.split(":"); index=int(index)
        if category=="allergies": options=ALLERGY_OPTIONS
        elif category=="excluded": options=sorted(set(ingredient_filter_options())|{"молочное","глютен","мясо"})
        else: await call.answer("Раздел не найден",show_alert=True); return
        if index<0 or index>=len(options): await call.answer("Пункт не найден",show_alert=True); return
        s=db.settings(call.from_user.id); field="allergies" if category=="allergies" else "excluded"
        values=set(s[field]); value=options[index]
        if value in values: values.remove(value)
        else: values.add(value)
        if field=="allergies": db.set_allergies(call.from_user.id,sorted(values))
        else: db.set_excluded(call.from_user.id,sorted(values))
        await show_restrictions(call.message,call.from_user.id,category,index//12); await call.answer()

    @dp.errors()
    async def errors(event):
        logging.exception("Unhandled bot error: %s",type(event.exception).__name__)

    logging.info("Dishly polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

