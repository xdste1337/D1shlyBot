import logging
import random
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from .config import load_config
from .database import Database
from .keyboards import main_menu, recipe_keyboard, dish_day_keyboard, catalog_keyboard, catalog_card_keyboard, list_keyboard, unknown_keyboard, settings_keyboard, servings_keyboard, exclusions_keyboard
from .parser import parse_query
from .search import rank_recipes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
db = None
queries = {}
MAX_INPUT = 500

def recipe_text(recipe, servings=None):
    ratio = (servings or recipe["servings"]) / recipe["servings"]
    lines=[f"🍽 <b>{recipe['title']}</b>",recipe["description"],f"⏱ {recipe['minutes']} мин. · {recipe['difficulty']} · {servings or recipe['servings']} порц."]
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
    all_results=rank_recipes(db.recipes(),query,settings["excluded"],offset=0,limit=100)
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
        await message.answer("Настройки\nИсключения: "+(", ".join(s["excluded"]) or "нет"),reply_markup=settings_keyboard(s))

    async def dish_day(message, user_id=None, exclude_shown=True):
        uid=user_id or message.from_user.id; settings=db.settings(uid); shown=db.shown_today(uid) if exclude_shown else set()
        candidates=[r for r in db.recipes() if r["id"] not in shown and not __import__("dishly.search",fromlist=["blocked"]).blocked(r,settings["excluded"])]
        if not candidates:
            await message.answer("На сегодня варианты закончились. Загляни завтра или попробуй поиск.",reply_markup=main_menu()); return
        recipe=random.choice(candidates); db.mark_today(uid,recipe["id"]); db.add_history(uid,recipe["id"])
        await message.answer("🍲 <b>Блюдо дня</b>\n\n"+recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=dish_day_keyboard(recipe["id"],recipe in db.favorites(uid)))

    @dp.callback_query(F.data=="daymore")
    async def another_dish(call):
        await dish_day(call.message,call.from_user.id)
        await call.answer()

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
        elif action=="exclude": await call.message.edit_text("Нажимай исключения, чтобы включать или убирать:",reply_markup=exclusions_keyboard(s["excluded"]))
        elif action=="clear": db.set_excluded(call.from_user.id,[]); await call.message.edit_text("Исключения сброшены.",reply_markup=settings_keyboard(db.settings(call.from_user.id)))
        elif action=="back": await call.message.edit_text("Настройки\nИсключения: "+(", ".join(s["excluded"]) or "нет"),reply_markup=settings_keyboard(s))
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

    @dp.errors()
    async def errors(event):
        logging.exception("Unhandled bot error: %s",type(event.exception).__name__)

    logging.info("Dishly polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

