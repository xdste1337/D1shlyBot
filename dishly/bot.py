import asyncio
import logging
import asyncio
import os
import random
import re
import html
import json
import secrets
import aiohttp
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message, CallbackQuery, LabeledPrice, ReplyKeyboardRemove

from .config import load_config
from .database import Database
from .keyboards import main_menu, more_menu, recipe_keyboard, dish_day_keyboard, dish_alternative_keyboard, catalog_keyboard, catalog_card_keyboard, all_catalog_keyboard, all_catalog_card_keyboard, filter_home_keyboard, filter_options_keyboard, filter_time_keyboard, filtered_results_keyboard, filtered_card_keyboard, list_keyboard, meal_plan_keyboard, meal_plan_recipe_keyboard, meal_plan_unavailable_keyboard, shopping_list_keyboard, unknown_keyboard, settings_keyboard, servings_keyboard, restriction_keyboard, first_start_keyboard, equipment_keyboard, pantry_prompt_keyboard, setup_reset_keyboard, report_cancel_keyboard, plus_keyboard, plus_terms_keyboard, advisor_cancel_keyboard, advisor_recipes_keyboard, advisor_test_keyboard, admin_access_keyboard, admin_access_users_keyboard, advisor_terms_keyboard
from .parser import parse_query
from .search import blocked, filter_recipes, rank_recipes, rank_pantry_recipes, pantry_substitutions, recipe_ingredients, canonical

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
db = None
queries = {}
filter_states = {}
filter_results = {}
pantry_mode = set()
pantry_results = set()
report_mode = {}
advisor_sessions = {}
payment_support_mode = set()
MAX_INPUT = 500
FILTER_METHODS = ["микроволновка","аэрогриль","кастрюля","сковорода","духовка","без готовки"]
EQUIPMENT_OPTIONS = ["плита","духовка","микроволновка","аэрогриль"]
FILTER_MOODS = ["сладкое","сытное","полезное","вегетарианское","завтрак","обед","ужин","суп","салат","перекус","рыбное","морепродукты","выпечка","печенье"]
ALLERGY_OPTIONS = ["молочное","яйца","глютен","рыба","орехи","арахис","соя","кунжут","морепродукты"]
MENU_TEXTS = {"🍳 Подобрать блюдо","Найти рецепт","🔎 Найти рецепт","📚 Каталог","Все рецепты","🔎 Фильтры","Фильтры","🍲 Блюдо дня","Блюдо дня","✨ Ещё","👩‍🍳 ИИ-советчик","📅 План на 3 дня","🏠 Главное меню","⭐ Избранное","Избранное","🕘 История","История","⚙️ Настройки","Настройки","❔ Помощь"}
HOME_BANNER = Path(__file__).resolve().parent.parent / "assets" / "dishly-home-banner.png"

def russian_sort_key(value):
    value=value.casefold()
    return (value.replace("ё","е"),value)

def alphabetize(values):
    return sorted(set(values),key=russian_sort_key)

def prioritize_selected(options, selected):
    selected=set(selected)
    return sorted(set(options),key=lambda x:(x not in selected,*russian_sort_key(x)))

def user_restrictions(settings):
    return sorted(set(settings["excluded"]) | set(settings["allergies"]))

def suitable_for_equipment(recipe, equipment):
    if not equipment or recipe["method"] == "без готовки":
        return True
    method = recipe["method"]
    if method in {"плита", "кастрюля", "сковорода"}:
        return "плита" in equipment
    return method in equipment

def scaled_ingredient_amount(amount, ratio, unit):
    scaled=amount*ratio
    if unit=="шт":
        return max(1,int(scaled+0.5))
    if unit in {"г","мл"}:
        step=10 if scaled>=100 else 5 if scaled>=20 else 1
        return max(1,int(scaled/step+0.5)*step)
    return round(scaled,1)

def normalize_restriction_category(category):
    return "excluded" if category=="exclude" else category

def recipe_text(recipe, servings=None, available_ingredients=None, user_exclusions=()):
    ratio = (servings or recipe["servings"]) / recipe["servings"]
    lines=[f"🍽 <b>{recipe['title']}</b>",recipe["description"],f"⏱ {recipe['minutes']} мин. · {recipe['difficulty']} · {servings or recipe['servings']} порц. · 🔥 ~{recipe['kcal_per_serving']} ккал/порц.",f"Способ: {recipe['method']}"]
    lines += ["", "<b>Ингредиенты</b>"]
    for i in recipe["ingredients"]:
        amount=scaled_ingredient_amount(i["amount"],ratio,i["unit"])
        lines.append(f"• {i['name']}: {amount:g} {i['unit']}" + (" (по желанию)" if i.get("optional") else ""))
    if available_ingredients is not None:
        missing=recipe_ingredients(recipe)-{canonical(name) for name in available_ingredients}
        substitutions=pantry_substitutions(missing,available_ingredients,user_exclusions)
        if substitutions:
            lines += ["", "<b>Возможные замены из твоих продуктов</b>"]
            lines += [f"• Вместо {source} можно попробовать {alternative}." for source,alternative in substitutions]
            lines.append("Замена может немного изменить вкус или текстуру.")
    lines += ["", "<b>Приготовление</b>"]
    lines += [f"{n}. {step}" for n,step in enumerate(recipe["steps"],1)]
    lines += ["", recipe["source"]]
    return "\n".join(lines)

async def show_search(message, offset=0, user_id=None, edit=False):
    uid=user_id or message.from_user.id
    query,raw=queries.get(uid,(None,""))
    if not query: return
    settings=db.settings(uid)
    hidden=db.not_suggested_recipe_ids(uid)
    recipes=[recipe for recipe in db.recipes() if recipe["id"] not in hidden and suitable_for_equipment(recipe,settings["equipment"])]
    if uid in pantry_results:
        all_results=rank_pantry_recipes(recipes,query.ingredients,set(user_restrictions(settings))|set(query.excluded))
        page=all_results[offset:offset+5]
        if not page:
            text="По этим продуктам больше рецептов нет. Попробуй изменить список продуктов."
            if edit: await message.edit_text(text,reply_markup=None)
            else: await message.answer(text,reply_markup=main_menu())
            return
        lines=[f"🧺 <b>Из твоих продуктов</b> · {offset+1}–{offset+len(page)} из {len(all_results)}",f"Есть: {html.escape(raw[:80])}",""]
        for i,(recipe,matched,missing) in enumerate(page,offset+1):
            lines.append(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин. · 🔥 ~{recipe['kcal_per_serving']} ккал")
            lines.append("✅ Уже есть: "+", ".join(alphabetize(matched)))
            if missing:
                missing_sorted=alphabetize(missing)
                shown=missing_sorted[:4]
                extra=f" и ещё {len(missing_sorted)-4}" if len(missing_sorted)>4 else ""
                lines.append("🛒 Понадобится: "+", ".join(shown)+extra)
                substitutions=pantry_substitutions(missing,query.ingredients,user_restrictions(settings))
                if substitutions:
                    lines.append("🔁 Можно попробовать заменить: "+"; ".join(f"{source} → {alternative}" for source,alternative in substitutions))
            else:
                lines.append("✅ Основные продукты уже есть")
        markup=catalog_keyboard([row[0] for row in page],offset,offset+len(page)<len(all_results))
        text="\n".join(lines)
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)
        return
    all_results=rank_recipes(recipes,query,user_restrictions(settings),offset=0,limit=100,liked_recipe_ids=db.liked_recipe_ids(uid),recently_cooked_recipe_ids=db.recently_cooked_recipe_ids(uid))
    page=all_results[offset:offset+5]
    if not page:
        text="По этому запросу больше рецептов нет. Попробуй другие продукты или пожелания."
        if edit: await message.edit_text(text,reply_markup=None)
        else: await message.answer(text,reply_markup=main_menu())
        return
    lines=[f"📚 <b>Каталог рецептов</b> · запрос: «{html.escape(raw[:80])}»",""]
    for i,(_,recipe,*_) in enumerate(page,offset+1):
        lines.append(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин. · 🔥 ~{recipe['kcal_per_serving']} ккал")
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
    text+="\n".join(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин. · 🔥 ~{recipe['kcal_per_serving']} ккал" for i,recipe in enumerate(page,start))
    markup=all_catalog_keyboard(page,offset,end<len(recipes))
    if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
    else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

async def main():
    global db
    config=load_config(); db=Database(config.database_path)
    session=AiohttpSession(proxy=os.getenv("TELEGRAM_PROXY") or None)
    bot=Bot(config.bot_token,session=session); dp=Dispatcher()

    def get_shared_dish():
        rid=db.shared_dish_today()
        if not rid:
            candidates=db.recipes()
            if not candidates: return None
            recipe=random.choice(candidates); db.set_shared_dish_today(recipe["id"]); rid=recipe["id"]
        return db.get_recipe(rid)

    def plus_ready():
        return bool(config.ai_api_key and config.plus_monthly_stars and config.admin_telegram_id)

    def advisor_access(uid):
        return db.plus_active(uid) or bool(db.plus_key_access(uid)) or bool(config.ai_api_key and config.admin_telegram_id==uid)

    async def show_plus(message, uid, edit=False):
        row=db.plus_subscription(uid); active=db.plus_active(uid); key_expiry=db.plus_key_access(uid)
        expires=datetime.fromtimestamp(row[0],timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M") if row else None
        test_access=bool(not active and config.ai_api_key and config.admin_telegram_id==uid)
        if test_access:
            text=("🧪 <b>Тестовый доступ владельца</b>\n\n"
                  "Можешь проверять ИИ-советчика без подписки. Для остальных пользователей Dishly Plus откроется после настройки цены и оплаты.")
            markup=advisor_test_keyboard()
        elif key_expiry and not active:
            expires=datetime.fromtimestamp(key_expiry,timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
            text=(f"🎟 <b>Доступ к ИИ-шефу активирован</b> до {expires}.\n\n"
                  f"Доступно до {config.advisor_daily_limit} обращений в день. Подписка и каталог Dishly остаются отдельными разделами.")
            markup=advisor_test_keyboard()
        elif active:
            auto="Автопродление отключено." if row[2] else "Подписка продлевается автоматически раз в месяц."
            text=(f"👩‍🍳 <b>Dishly Plus активен</b> до {expires}.\n{auto}\n\n"
                  f"Доступно до {config.advisor_daily_limit} обращений к советчику в день.")
            markup=plus_keyboard(active,db.plus_terms_accepted(uid),plus_ready(),bool(row and row[2]))
        else:
            text=("✨ <b>Dishly Plus</b>\n\n"
                  "Личный ИИ-советчик поможет выбрать блюдо и подобрать подходящие рецепты из каталога, учитывая твои настройки.\n\n"
                  "Бесплатный каталог, фильтры и план на 3 дня останутся доступны всем.\n"
                  "Есть код доступа? Отправь <code>/activate КОД</code>.")
            if config.plus_monthly_stars:
                text+=f"\n\nЦена: {config.plus_monthly_stars} ⭐ в месяц."
            if not config.ai_api_key:
                text+="\n\nПока не настроен ключ AI API."
            if not config.plus_monthly_stars:
                text+="\nПока не задана цена подписки в Stars."
            if not config.admin_telegram_id:
                text+="\nНе настроен контакт поддержки платежей."
            markup=plus_keyboard(active,db.plus_terms_accepted(uid),plus_ready(),bool(row and row[2]))
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

    async def show_plus_terms(message, uid, access_code=False):
        if access_code:
            text=("📄 <b>Условия ИИ-шефа</b>\n\n"
                  "🎟 Доступ активирован кодом и действует указанный срок. За этот код бот не списывает Stars.\n"
                  "🔐 Текст запроса, число порций, ограничения питания, доступная техника и подходящие рецепты отправляются настроенному AI-провайдеру и выбранной модели. Telegram ID и имя не передаются.\n"
                  "⚠️ Ответы ИИ могут содержать ошибки и не заменяют рекомендации врача. При аллергиях Dishly отбирает рецепты локально, но всегда проверяй состав и упаковку продуктов.\n\n"
                  "Нажимая кнопку ниже, ты подтверждаешь, что прочитал(а) условия и согласен(на) на обработку текста запроса AI-провайдером и выбранной моделью.")
            await message.answer(text,parse_mode="HTML",reply_markup=advisor_terms_keyboard())
            return
        price_text=f"{config.plus_monthly_stars} Telegram Stars" if config.plus_monthly_stars else "цена будет показана перед оплатой после настройки"
        text=("📄 <b>Условия Dishly Plus</b>\n\n"
              f"• Цена: {price_text} в месяц. Подписка продлевается автоматически раз в 30 дней.\n"
              "• Отключить автопродление можно в разделе Dishly Plus; доступ сохранится до конца оплаченного периода.\n"
              "• Советчик отправляет текст запроса, число порций, ограничения питания, доступную технику и подходящие рецепты через настроенного AI-провайдера и выбранную модель. Telegram ID и имя туда не передаются.\n"
              "• Ответы ИИ могут содержать ошибки и не заменяют рекомендации врача. При аллергиях Dishly исключает рецепты локально, но всегда проверяй состав и упаковку продуктов.\n"
              "• По вопросам оплаты используй команду /paysupport. Вопросы по возврату рассматриваются индивидуально согласно правилам Telegram.\n\n"
              "Нажимая кнопку ниже, ты подтверждаешь, что прочитал условия и согласен на обработку текста запроса AI-провайдером и выбранной моделью.")
        await message.answer(text,parse_mode="HTML",reply_markup=plus_terms_keyboard())

    async def send_plus_invoice(message, uid):
        if not plus_ready():
            await show_plus(message,uid)
            return
        if not db.plus_terms_accepted(uid):
            await show_plus_terms(message,uid)
            return
        if db.plus_active(uid):
            await show_plus(message,uid)
            return
        await message.answer_invoice(
            title="Dishly Plus — ИИ-советчик",
            description="Доступ к личному кулинарному советчику на 30 дней. Автопродление можно отключить в боте.",
            payload="dishly_plus_monthly_v1",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Dishly Plus · 30 дней",amount=config.plus_monthly_stars)],
            subscription_period=2592000,
        )

    async def advisor_answer(message, uid, question):
        if not advisor_access(uid):
            advisor_sessions.pop(uid,None)
            await message.answer("🔒 Для ИИ-шефа нужен Dishly Plus или код доступа. Если у тебя есть код, отправь <code>/activate КОД</code>. Каталог и остальные функции остаются бесплатными.",parse_mode="HTML",reply_markup=main_menu())
            return
        if not db.plus_terms_accepted(uid):
            advisor_sessions.pop(uid,None)
            await show_plus_terms(message,uid,access_code=bool(db.plus_key_access(uid)) or uid==config.admin_telegram_id)
            return
        if len(question)>1200:
            await message.answer("Вопрос слишком длинный. Сократи его до 1200 символов.",reply_markup=advisor_cancel_keyboard())
            return
        if not db.consume_advisor_request(uid,config.advisor_daily_limit):
            await message.answer("На сегодня лимит вопросов закончился. Попробуй завтра 🕒",reply_markup=advisor_cancel_keyboard())
            return
        settings=db.settings(uid); query=parse_query(question)
        exclusions=set(user_restrictions(settings))|set(query.excluded)
        hidden=db.not_suggested_recipe_ids(uid)
        available=[r for r in db.recipes() if r["id"] not in hidden and not blocked(r,exclusions) and suitable_for_equipment(r,settings["equipment"])]
        if query.understood:
            ranked=rank_recipes(available,query,exclusions,limit=8,liked_recipe_ids=db.liked_recipe_ids(uid),recently_cooked_recipe_ids=db.recently_cooked_recipe_ids(uid))
            candidates=[row[1] for row in ranked]
        else:
            candidates=random.sample(available,min(8,len(available))) if available else []
        compact=[{"id":r["id"],"title":r["title"],"minutes":r["minutes"],"kcal":r["kcal_per_serving"],"ingredients":[i["name"] for i in r["ingredients"] if not i.get("optional",False)]} for r in candidates]
        system=("Ты — личный ИИ-шеф Dishly. Отвечай по-русски тепло, живо и подробно, но без воды. "
                "Оформляй ответ ярко и легко для чтения: используй уместные эмодзи в заголовках и разделах (примерно 1–3 на абзац), "
                "короткие смысловые блоки, списки и выделение **жирным** для названий блюд, времени и важных советов. Не делай ответ скудным или телеграфным. "
                "Если просят рецепт — подробно распиши ингредиенты и шаги приготовления; если просят идею или выбор, объясни вкус, удобство и почему блюдо подходит. "
                "Подбирай только из переданного списка recipes. Не выдумывай блюда, ингредиенты, калории или факты о безопасности. "
                "Если подходящего блюда нет, задай уточняющий вопрос или объясни это. Не предлагай ничего из excluded; список candidates уже отфильтрован, не пытайся его расширить. "
                "Не давай медицинских советов и не обещай безопасность для аллергиков; напоминай проверять этикетки при вопросах об аллергии. "
                "Верни только JSON вида {\"answer\":\"текст\",\"recipe_ids\":[\"id\"]}; recipe_ids должны быть только из переданного списка, не более трёх.")
        user_payload={"question":question,"servings":settings["servings"],"excluded":sorted(exclusions),"equipment":settings["equipment"],"recipes":compact}
        history=advisor_sessions.setdefault(uid,[])
        messages=[{"role":"system","content":system},*history,{"role":"user","content":json.dumps(user_payload,ensure_ascii=False)}]
        try:
            timeout=aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as client:
                async with client.post(
                    f"{config.ai_base_url}/chat/completions",
                    headers={"Authorization":f"Bearer {config.ai_api_key}","Content-Type":"application/json"},
                    json={"model":config.ai_model,"messages":messages,"response_format":{"type":"json_object"},"max_tokens":900,"temperature":0.55},
                    proxy=config.ai_proxy or None,
                ) as response:
                    if response.status!=200:
                        logging.error("AI API returned HTTP %s",response.status)
                        await message.answer("Советчик сейчас не ответил. Попробуй чуть позже.",reply_markup=advisor_cancel_keyboard())
                        return
                    result=await response.json()
            content=result["choices"][0]["message"]["content"]
            parsed=json.loads(content)
            answer=str(parsed.get("answer","")).strip()[:3500] or "Не получилось сформулировать совет — попробуй уточнить запрос."
            allowed={r["id"]:r for r in candidates}
            selected=[]
            for rid in parsed.get("recipe_ids",[]):
                if rid in allowed and rid not in {r["id"] for r in selected}:
                    selected.append(allowed[rid])
                if len(selected)==3: break
            history.extend([{"role":"user","content":json.dumps(user_payload,ensure_ascii=False)},{"role":"assistant","content":content}])
            advisor_sessions[uid]=history[-8:]
            safe_answer=html.escape(answer)
            safe_answer=re.sub(r"\*\*(.+?)\*\*",r"<b>\1</b>",safe_answer,flags=re.S)
            await message.answer(f"👩‍🍳 <b>Совет шефа Dishly</b>\n\n{safe_answer}",parse_mode="HTML",reply_markup=advisor_recipes_keyboard(selected) if selected else advisor_cancel_keyboard())
        except (aiohttp.ClientError,asyncio.TimeoutError,KeyError,IndexError,TypeError,ValueError) as exc:
            logging.warning("DeepSeek advisor request failed: %s",type(exc).__name__)
            await message.answer("Не смог связаться с советчиком. Попробуй позже.",reply_markup=advisor_cancel_keyboard())

    async def show_home(message,uid,first_name="",edit=False):
        greetings=[
            "Сегодня на кухне пахнет чем-то вкусным 😋",
            "Новый день — новый повод приготовить что-нибудь классное ✨",
            "Заглянем в холодильник и придумаем вкусный план? 🥕",
            "Кулинарное вдохновение уже здесь! 👩‍🍳",
            "Что сегодня будет на тарелке? Давай выберем 🍽️",
            "Пора устроить маленький праздник на кухне 🎉",
            "Привет с кухни Dishly! Выбирай идею и готовь с удовольствием 💛",
        ]
        greeting=greetings[date.today().toordinal()%len(greetings)]
        name=f" {html.escape(first_name)}" if first_name else ""
        settings=db.settings(uid); recipe=get_shared_dish()
        lines=[f"👋 <b>Привет{name}!</b>",greeting,"",f"📚 В каталоге уже <b>{len(db.recipes())}</b> идей для готовки."]
        if recipe:
            if recipe["id"] in db.not_suggested_recipe_ids(uid):
                lines.append("🍲 Общее блюдо дня выбрано для всех. Ты попросил не предлагать его — личные подборки его пропустят.")
            elif blocked(recipe,user_restrictions(settings)) or not suitable_for_equipment(recipe,settings["equipment"]):
                lines.append("🍲 Блюдо дня выбрано для всех, а я учту твои ограничения и технику и предложу подходящие рецепты.")
            else:
                lines.append(f"🍲 Блюдо дня: <b>{html.escape(recipe['title'])}</b> · ⏱ {recipe['minutes']} мин. · 🔥 ~{recipe['kcal_per_serving']} ккал/порц.")
        restrictions=user_restrictions(settings)
        if restrictions:
            visible=", ".join(restrictions[:4])
            more=f" и ещё {len(restrictions)-4}" if len(restrictions)>4 else ""
            lines.append(f"🛡️ Учту твои ограничения: {html.escape(visible)}{more}.")
        lines += ["","💬 Просто напиши, что есть или чего хочется:","🥚 «есть яйца и помидоры»","🍫 «хочу чего-нибудь сладкого»","⚡ «быстрый ужин без духовки»","","👇 Или выбери раздел в меню ниже."]
        text="\n".join(lines)
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=main_menu())
        elif HOME_BANNER.is_file():
            await message.answer_photo(FSInputFile(HOME_BANNER),caption=text,parse_mode="HTML",reply_markup=main_menu())
        else:
            await message.answer(text,parse_mode="HTML",reply_markup=main_menu())

    @dp.message(CommandStart())
    async def start(message: Message):
        pantry_mode.discard(message.from_user.id)
        pantry_results.discard(message.from_user.id)
        is_new_user = db.ensure_user(message.from_user.id)
        if is_new_user:
            name = html.escape(message.from_user.first_name or "")
            greeting = f"👋 Привет, {name}!" if name else "👋 Привет!"
            text = (f"{greeting}\n\n"
                    "Я помогу выбрать, что приготовить 🥘\n"
                    "Перед началом можно указать порции, аллергии, продукты-исключения и доступную технику.\n\n"
                    "Это необязательно: настройки можно пропустить и изменить позже в разделе «Ещё» → «Настройки».")
            await message.answer(text,reply_markup=first_start_keyboard())
            return
        await show_home(message,message.from_user.id,message.from_user.first_name or "")

    @dp.message(Command("help"))
    async def help_cmd(message):
        await message.answer("💡 Напиши продукты или пожелания обычным текстом: «сытное из курицы без духовки». Ещё можно искать через фильтры, листать каталог, сохранять любимые рецепты и собирать план на 3 дня ⭐",reply_markup=main_menu())

    @dp.message(Command("plus"))
    async def plus_cmd(message):
        await show_plus(message,message.from_user.id)

    @dp.message(Command("admin"))
    async def admin_cmd(message):
        if not config.admin_telegram_id or message.from_user.id!=config.admin_telegram_id:
            await message.answer("Команда доступна только администратору бота.")
            return
        await message.answer("🛠 <b>Админ-панель Dishly</b>\n\nУправление доступом к ИИ-шефу. Каталог и остальные функции бота доступны всем.",parse_mode="HTML",reply_markup=admin_access_keyboard())

    @dp.message(Command("activate"))
    async def activate_ai_access(message):
        parts=(message.text or "").split(maxsplit=1)
        if len(parts)!=2 or not parts[1].strip():
            await message.answer("🎟 Чтобы активировать доступ к ИИ-шефу, отправь код так: <code>/activate КОД</code>",parse_mode="HTML")
            return
        expires=db.redeem_plus_access_key(parts[1].strip(),message.from_user.id)
        if not expires:
            await message.answer("⚠️ Код не найден, уже использован или отозван. Проверь его и попробуй ещё раз.")
            return
        when=datetime.fromtimestamp(expires,timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
        await message.answer(f"🎉 Код активирован! Доступ к ИИ-шефу открыт до {when}.\n\nСначала ознакомься с условиями обработки запросов:")
        await show_plus_terms(message,message.from_user.id,access_code=True)

    @dp.message(Command("terms"))
    async def terms_cmd(message):
        await show_plus_terms(message,message.from_user.id)

    @dp.message(Command("paysupport"))
    async def paysupport_cmd(message):
        payment_support_mode.add(message.from_user.id)
        await message.answer("Напиши, с какой проблемой по оплате или подписке столкнулся. Перешлю сообщение администратору. Напиши /cancel, чтобы отменить.")

    @dp.message(Command("pluspayments"))
    async def plus_payments_cmd(message):
        if not config.admin_telegram_id or message.from_user.id!=config.admin_telegram_id:
            await message.answer("Команда доступна только администратору бота."); return
        parts=message.text.split()
        if len(parts)!=2 or not parts[1].isdigit():
            await message.answer("Формат: /pluspayments USER_ID"); return
        payments=db.plus_payments(int(parts[1]))
        if not payments:
            await message.answer("Платежей Dishly Plus для этого пользователя нет."); return
        for payment in payments:
            status="возвращён" if payment[4] else "не возвращён"
            await message.answer(f"Платёж {payment[3]} · {payment[1]} ⭐ · {status}\nCharge ID: <code>{html.escape(payment[0])}</code>",parse_mode="HTML")

    @dp.message(Command("refund"))
    async def plus_refund_cmd(message):
        if not config.admin_telegram_id or message.from_user.id!=config.admin_telegram_id:
            await message.answer("Команда доступна только администратору бота."); return
        parts=message.text.split(maxsplit=2)
        if len(parts)!=3 or not parts[1].isdigit():
            await message.answer("Формат: /refund USER_ID CHARGE_ID. Сначала найди платёж через /pluspayments USER_ID."); return
        uid=int(parts[1]); charge_id=parts[2].strip()
        payment=db.plus_payment(uid,charge_id)
        if not payment:
            await message.answer("Не нашёл этот платёж для указанного пользователя."); return
        if payment[0]:
            await message.answer("Этот платёж уже отмечен как возвращённый."); return
        subscription=db.plus_subscription(uid)
        if subscription and db.plus_active(uid) and not subscription[2]:
            try:
                await bot.edit_user_star_subscription(user_id=uid,telegram_payment_charge_id=subscription[1],is_canceled=True)
                db.cancel_plus_renewal(uid)
            except TelegramAPIError:
                logging.exception("Could not cancel subscription before refund for user %s",uid)
                await message.answer("Не удалось отключить автопродление; возврат не отправлял."); return
        try:
            await bot.refund_star_payment(user_id=uid,telegram_payment_charge_id=charge_id)
            db.mark_plus_payment_refunded(uid,charge_id)
            if subscription and db.plus_active(uid):
                db.revoke_plus_subscription(uid)
            await message.answer("Возврат отправлен через Telegram Stars.")
        except TelegramAPIError:
            logging.exception("Could not refund Dishly Plus payment for user %s",uid)
            await message.answer("Telegram не выполнил возврат. Проверь charge ID и попробуй позже.")

    @dp.message(Command("id"))
    async def id_cmd(message):
        await message.answer(f"Твой Telegram user ID: <code>{message.from_user.id}</code>\nУкажи его в .env в строке ADMIN_TELEGRAM_ID, чтобы получать сообщения о проблемах с рецептами.",parse_mode="HTML")

    @dp.message(Command("reports"))
    async def reports_cmd(message):
        if not config.admin_telegram_id or message.from_user.id != config.admin_telegram_id:
            await message.answer("Команда доступна только администратору бота.")
            return
        reports=db.pending_recipe_reports()
        if not reports:
            await message.answer("Неразосланных сообщений о рецептах нет.")
            return
        for report in reports:
            recipe=db.get_recipe(report[2]); title=recipe["title"] if recipe else report[2]
            body=(f"⚠️ <b>Сообщение #{report[0]}</b> · {report[4]}\n"
                  f"Рецепт: <b>{html.escape(title)}</b>\n"
                  f"От пользователя: <code>{report[1]}</code>\n\n{html.escape(report[3])}")
            await message.answer(body,parse_mode="HTML")

    @dp.message(F.text)
    async def text_handler(message: Message):
        text=message.text.strip()
        uid=message.from_user.id
        if uid in report_mode:
            if text.casefold() in {"отмена","/cancel"}:
                report_mode.pop(uid,None)
                await message.answer("Сообщение о проблеме отменено.",reply_markup=main_menu())
                return
            if len(text)>1000:
                await message.answer("Сообщение слишком длинное. Опиши проблему в пределах 1000 символов или нажми «Отмена».",reply_markup=report_cancel_keyboard())
                return
            rid=report_mode.pop(uid)
            recipe=db.get_recipe(rid)
            if not recipe:
                await message.answer("Не нашёл этот рецепт. Открой карточку снова и попробуй ещё раз.",reply_markup=main_menu())
                return
            report_id=db.add_recipe_report(uid,rid,text)
            if config.admin_telegram_id:
                body=(f"⚠️ <b>Проблема с рецептом #{report_id}</b>\n"
                      f"Рецепт: <b>{html.escape(recipe['title'])}</b> (<code>{rid}</code>)\n"
                      f"От пользователя: <code>{uid}</code>\n\n{html.escape(text)}")
                try:
                    await bot.send_message(config.admin_telegram_id,body,parse_mode="HTML")
                    db.mark_recipe_report_delivered(report_id)
                except TelegramAPIError:
                    logging.warning("Could not deliver recipe report %s to configured admin",report_id)
            await message.answer("Спасибо! Сохранил сообщение о проблеме с рецептом 📝",reply_markup=main_menu())
            return
        if uid in payment_support_mode:
            if text.casefold() in {"отмена","/cancel"}:
                payment_support_mode.discard(uid)
                await message.answer("Обращение отменено.",reply_markup=main_menu())
                return
            if not config.admin_telegram_id:
                payment_support_mode.discard(uid)
                await message.answer("Поддержка оплаты пока не настроена. Попробуй позже.",reply_markup=main_menu())
                return
            body=(f"💳 <b>Вопрос по оплате Dishly Plus</b>\nПользователь: <code>{uid}</code>\n\n{html.escape(text[:3000])}")
            try:
                await bot.send_message(config.admin_telegram_id,body,parse_mode="HTML")
                payment_support_mode.discard(uid)
                await message.answer("Обращение отправлено администратору. Спасибо!",reply_markup=main_menu())
            except TelegramAPIError:
                logging.warning("Could not deliver payment support message from user %s",uid)
                await message.answer("Не получилось отправить обращение. Попробуй ещё раз позже.")
            return
        if uid in advisor_sessions:
            if text.casefold() in {"отмена","/cancel","готово","завершить"}:
                advisor_sessions.pop(uid,None)
                await message.answer("Консультация завершена. Бесплатные рецепты доступны в меню 🍲",reply_markup=main_menu())
                return
            await advisor_answer(message,uid,text)
            return
        if text=="👩‍🍳 ИИ-советчик":
            await show_plus(message,uid)
            return
        if text=="🧺 Из моих продуктов":
            pantry_mode.add(uid); pantry_results.discard(uid)
            await message.answer("🧺 Перечисли продукты, которые у тебя есть, через запятую. Например: курица, рис, морковь.\n\nПокажу блюда, где используются эти продукты, и отмечу, что ещё понадобится. Необязательные соль и вода указывать не нужно.",reply_markup=pantry_prompt_keyboard())
            return
        if text in MENU_TEXTS:
            pantry_mode.discard(uid); pantry_results.discard(uid)
        if text in {"🍳 Подобрать блюдо","Найти рецепт","🔎 Найти рецепт"}:
            await message.answer("🍳 Напиши продукты или настроение, например: «есть яйца и помидоры» или «что-нибудь сладкое до 20 минут»."); return
        if text in {"📚 Каталог","Все рецепты"}:
            await show_all_catalog(message); return
        if text in {"🔎 Фильтры","Фильтры"}:
            await show_filter_home(message,message.from_user.id); return
        if text in {"🍲 Блюдо дня","Блюдо дня"}:
            await dish_day(message); return
        if text=="✨ Ещё":
            await message.answer("🧰 Дополнительные разделы Dishly",reply_markup=more_menu()); return
        if text=="📅 План на 3 дня":
            await show_meal_plan(message,uid); return
        if text=="🏠 Главное меню":
            await show_home(message,message.from_user.id,message.from_user.first_name or ""); return
        if text in {"⭐ Избранное","Избранное"}:
            await show_list(message,"⭐ Избранное",db.favorites(message.from_user.id)); return
        if text in {"🕘 История","История"}:
            await show_list(message,"🕘 Недавно просмотренные",db.history(message.from_user.id)); return
        if text in {"⚙️ Настройки","Настройки"}:
            await show_settings(message); return
        if text=="❔ Помощь":
            await help_cmd(message); return
        if uid in pantry_mode:
            if text.casefold() in {"отмена","отменить","стоп"}:
                pantry_mode.discard(uid)
                await message.answer("Подбор по продуктам отменён.",reply_markup=main_menu())
                return
            if len(text)>MAX_INPUT:
                await message.answer(f"Список слишком длинный. Сократи его до {MAX_INPUT} символов.",reply_markup=pantry_prompt_keyboard()); return
            query=parse_query(text)
            if not query.ingredients:
                await message.answer("Не распознал продукты. Напиши основные ингредиенты через запятую, например: яйца, картофель, сыр. Или отправь «Отмена».",reply_markup=pantry_prompt_keyboard()); return
            settings=db.settings(uid)
            hidden=db.not_suggested_recipe_ids(uid)
            available=[recipe for recipe in db.recipes() if recipe["id"] not in hidden and suitable_for_equipment(recipe,settings["equipment"])]
            results=rank_pantry_recipes(available,query.ingredients,set(user_restrictions(settings))|set(query.excluded))
            if not results:
                await message.answer("Не нашёл подходящих рецептов с этими продуктами и твоими настройками. Попробуй указать меньше продуктов или отправь «Отмена».",reply_markup=pantry_prompt_keyboard()); return
            pantry_mode.discard(uid); pantry_results.add(uid); queries[uid]=(query,text)
            await show_search(message,user_id=uid)
            return
        if len(text)>MAX_INPUT:
            await message.answer(f"Запрос слишком длинный. Сократи его до {MAX_INPUT} символов."); return
        query=parse_query(text)
        if not query.understood:
            await message.answer("Не понял запрос. Напиши продукты или пожелание вроде «быстрое блюдо без духовки».",reply_markup=unknown_keyboard()); return
        pantry_results.discard(uid)
        queries[uid]=(query,text)
        await show_search(message)

    async def show_list(message,title,recipes):
        if not recipes: await message.answer(f"{title}: пока пусто.",reply_markup=main_menu()); return
        await message.answer(title+":",reply_markup=list_keyboard(recipes))

    async def show_meal_plan(message,uid,edit=False,regenerate=False):
        settings=db.settings(uid)
        hidden=db.not_suggested_recipe_ids(uid)
        allowed=[r for r in db.recipes() if r["id"] not in hidden and not blocked(r,user_restrictions(settings)) and suitable_for_equipment(r,settings["equipment"])]
        allowed_ids={r["id"] for r in allowed}
        previous_ids=db.meal_plan(uid)
        plan_ids=[] if regenerate else previous_ids
        plan=[db.get_recipe(rid) for rid in plan_ids]
        if len(plan)!=3 or any(not r or r["id"] not in allowed_ids for r in plan):
            if len(allowed)<3:
                text="Пока не получается собрать план на три дня с текущими ограничениями и техникой. Попробуй изменить настройки."
                if edit: await message.edit_text(text,reply_markup=meal_plan_unavailable_keyboard())
                else: await message.answer(text,reply_markup=main_menu())
                return
            recent={r["id"] for r in db.history(uid)} | db.recently_cooked_recipe_ids(uid)
            favorites={r["id"] for r in db.favorites(uid)} | db.liked_recipe_ids(uid)
            pool=[r for r in allowed if r["id"] not in recent and (not regenerate or r["id"] not in previous_ids)]
            if len(pool)<3 and regenerate:
                pool=[r for r in allowed if r["id"] not in previous_ids]
            if len(pool)<3: pool=allowed[:]
            random.shuffle(pool)
            plan=[]
            used_types=set()
            for _ in range(3):
                def plan_score(recipe):
                    kinds=set(recipe["tags"]) & {"мясное","рыбное","морепродукты","вегетарианское"}
                    return (bool(kinds & used_types),recipe["id"] not in favorites,random.random())
                chosen=min(pool,key=plan_score)
                plan.append(chosen)
                used_types.update(set(chosen["tags"]) & {"мясное","рыбное","морепродукты","вегетарианское"})
                pool.remove(chosen)
            db.set_meal_plan(uid,[r["id"] for r in plan])
        labels=("Сегодня","Завтра","Послезавтра")
        lines=["📅 <b>План на ближайшие 3 дня</b>","По одной идее на день. Учитываю твои аллергии, исключения и доступную технику.",""]
        for index,recipe in enumerate(plan):
            plan_date=date.today()+timedelta(days=index)
            lines.append(f"<b>{labels[index]} · {plan_date:%d.%m}</b>")
            lines.append(f"🍽 {html.escape(recipe['title'])} · {recipe['minutes']} мин. · 🔥 ~{recipe['kcal_per_serving']} ккал/порц.")
        markup=meal_plan_keyboard(plan)
        text="\n".join(lines)
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

    async def show_shopping_list(message,uid,edit=False):
        plan_ids=db.meal_plan(uid)
        recipes=[db.get_recipe(rid) for rid in plan_ids]
        settings=db.settings(uid)
        hidden=db.not_suggested_recipe_ids(uid)
        if len(recipes)!=3 or any(not recipe or recipe["id"] in hidden or blocked(recipe,user_restrictions(settings)) or not suitable_for_equipment(recipe,settings["equipment"]) for recipe in recipes):
            await show_meal_plan(message,uid,edit=edit)
            return
        totals={}
        for recipe in recipes:
            ratio=settings["servings"]/recipe["servings"]
            for ingredient in recipe["ingredients"]:
                if ingredient.get("optional"):
                    continue
                name=ingredient["name"].strip()
                unit={"листа":"лист"}.get(ingredient["unit"],ingredient["unit"])
                key=(name.casefold(),unit)
                if key not in totals:
                    totals[key]=[name,0.0]
                totals[key][1]+=ingredient["amount"]*ratio
        lines=["🛒 <b>Список покупок на 3 дня</b>",f"Порций на каждое блюдо: {settings['servings']}.",""]
        for (_,unit),(name,amount) in sorted(totals.items(),key=lambda item:russian_sort_key(item[1][0])):
            rounded=scaled_ingredient_amount(amount,1,unit)
            lines.append(f"• {html.escape(name)} — {rounded:g} {unit}")
        lines.extend(["","Необязательные ингредиенты в список не включены."])
        text="\n".join(lines)
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=shopping_list_keyboard())
        else: await message.answer(text,parse_mode="HTML",reply_markup=shopping_list_keyboard())

    async def show_settings(message, edit=False):
        s=db.settings(message.from_user.id)
        info=[]
        info.append("Аллергии: "+(", ".join(alphabetize(s["allergies"])) or "не указаны"))
        info.append("Не ем: "+(", ".join(alphabetize(s["excluded"])) or "ничего не исключено"))
        info.append("Техника: "+(", ".join(alphabetize(s["equipment"])) or "подбор не ограничен"))
        text="⚙️ Настройки\n"+"\n".join(info)
        if edit: await message.edit_text(text,reply_markup=settings_keyboard(s))
        else: await message.answer(text,reply_markup=settings_keyboard(s))

    @dp.callback_query(F.data.startswith("firststart:"))
    async def first_start_action(call):
        action=call.data.split(":",1)[1]
        if action=="settings":
            await show_settings(call.message,edit=True)
        else:
            await show_home(call.message,call.from_user.id,call.from_user.first_name or "",edit=True)
        await call.answer()

    async def show_restrictions(message,uid,category,page=0):
        category=normalize_restriction_category(category)
        s=db.settings(uid)
        if category=="allergies":
            selected=set(s["allergies"]); options=prioritize_selected(ALLERGY_OPTIONS,selected)
            title="Выбери аллергены. Рецепты с ними будут исключены по составу и аллергенам каталога. Возможные следы аллергенов каталог не описывает."
        else:
            selected=set(s["excluded"]); options=prioritize_selected(set(ingredient_filter_options())|{"молочное","глютен","мясо"},selected)
            title="Отметь продукты, которые не хочешь видеть в рецептах."
        await message.edit_text(title+"\nОтмечено: "+(", ".join(alphabetize(selected)) or "ничего"),reply_markup=restriction_keyboard(category,options,selected,page))

    def get_filter_state(uid):
        return filter_states.setdefault(uid,{"ingredients":set(),"methods":set(),"moods":set(),"max_minutes":None})

    def ingredient_filter_options():
        return sorted({canonical(item["name"]) for recipe in db.recipes() for item in recipe["ingredients"] if not item.get("optional",False)})

    def filter_options(category,uid=None):
        if category=="ingredients": options=ingredient_filter_options()
        elif category=="methods": options=FILTER_METHODS
        elif category=="moods": options=FILTER_MOODS
        else: return []
        selected=get_filter_state(uid)[category] if uid is not None else set()
        return prioritize_selected(options,selected)

    async def show_filter_home(message,uid,edit=False):
        state=get_filter_state(uid)
        selected=[]
        for key,title in (("ingredients","продукты"),("methods","способ"),("moods","пожелания")):
            if state[key]:
                values=["Полезное / ПП" if value=="полезное" else value for value in sorted(state[key])]
                selected.append(title+": "+", ".join(values))
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
            options=filter_options(category,uid)
            selected=state[category]
            selected_labels=["Полезное / ПП" if value=="полезное" else value for value in sorted(selected)]
            text=titles[category]+f"\nВыбрано: {', '.join(selected_labels) if selected else 'ничего'}"
            markup=filter_options_keyboard(category,options,selected,page)
        await message.edit_text(text,reply_markup=markup)

    async def show_filtered_results(message,uid,offset=0,edit=True):
        state=get_filter_state(uid); settings=db.settings(uid)
        hidden=db.not_suggested_recipe_ids(uid)
        available=[recipe for recipe in db.recipes() if recipe["id"] not in hidden and suitable_for_equipment(recipe,settings["equipment"])]
        recipes=filter_recipes(available,state["ingredients"],state["methods"]|state["moods"],state["max_minutes"],user_restrictions(settings))
        filter_results[uid]=[recipe["id"] for recipe in recipes]
        if not recipes:
            text="По всем выбранным условиям рецептов не нашлось. Попробуй убрать один из фильтров."
            if edit: await message.edit_text(text,reply_markup=filter_home_keyboard(state))
            else: await message.answer(text,reply_markup=filter_home_keyboard(state))
            return
        ids=filter_results[uid][offset:offset+5]
        page=[db.get_recipe(rid) for rid in ids]
        text=f"📚 <b>Рецепты по фильтрам</b> · {offset+1}–{offset+len(page)} из {len(recipes)}\n\n"
        text+="\n".join(f"<b>{i}. {recipe['title']}</b> · {recipe['minutes']} мин. · 🔥 ~{recipe['kcal_per_serving']} ккал" for i,recipe in enumerate(page,offset+1))
        markup=filtered_results_keyboard(page,offset,offset+len(page)<len(recipes))
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

    async def dish_day(message, user_id=None, edit=False):
        uid=user_id or message.from_user.id; settings=db.settings(uid)
        recipe=get_shared_dish()
        if not recipe: return
        rid=recipe["id"]; db.add_history(uid,rid)
        hidden=rid in db.not_suggested_recipe_ids(uid)
        if blocked(recipe,user_restrictions(settings)) or not suitable_for_equipment(recipe,settings["equipment"]) or hidden:
            text=(f"🍲 <b>Блюдо дня для всех</b>\n\n<b>{recipe['title']}</b> · {recipe['minutes']} мин.\n"
                  "Это блюдо не подходит под твои настройки или отмечено «Не предлагать». Нажми «Другой вариант» — подберу личную альтернативу.")
        else:
            text="🍲 <b>Блюдо дня для всех</b>\n\n"+recipe_text(recipe,settings["servings"])
        markup=dish_day_keyboard(recipe["id"],recipe in db.favorites(uid),db.recipe_feedback(uid,recipe["id"]))
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=markup)
        else: await message.answer(text,parse_mode="HTML",reply_markup=markup)

    async def show_another_dish(message, user_id, edit=True):
        settings=db.settings(user_id)
        daily_id=db.shared_dish_today()
        seen=db.user_alternatives_today(user_id)
        hidden=db.not_suggested_recipe_ids(user_id)
        recently_cooked=db.recently_cooked_recipe_ids(user_id)
        candidates=[r for r in db.recipes() if r["id"] != daily_id and r["id"] not in seen and r["id"] not in hidden and r["id"] not in recently_cooked and not blocked(r,user_restrictions(settings)) and suitable_for_equipment(r,settings["equipment"])]
        if not candidates:
            text="На сегодня больше подходящих вариантов нет. Общее блюдо дня осталось прежним."
            if edit: await message.edit_text(text,reply_markup=None)
            else: await message.answer(text,reply_markup=main_menu())
            return
        recipe=random.choice(candidates); db.mark_user_alternative(user_id,recipe["id"]); db.add_history(user_id,recipe["id"])
        saved=any(r["id"]==recipe["id"] for r in db.favorites(user_id))
        text="🍽 <b>Другой вариант для тебя</b>\n\n"+recipe_text(recipe,settings["servings"])
        feedback=db.recipe_feedback(user_id,recipe["id"])
        if edit: await message.edit_text(text,parse_mode="HTML",reply_markup=dish_alternative_keyboard(recipe["id"],saved,feedback))
        else: await message.answer(text,parse_mode="HTML",reply_markup=dish_alternative_keyboard(recipe["id"],saved,feedback))

    @dp.callback_query(F.data=="daymore")
    async def daymore_handler(call):
        await call.answer()
        await show_another_dish(call.message,call.from_user.id)

    @dp.callback_query(F.data=="dayhome")
    async def back_to_shared_dish(call):
        await call.answer("Общее блюдо дня не менялось")
        await dish_day(call.message,call.from_user.id,edit=True)

    @dp.callback_query(F.data.startswith("altfav:"))
    async def alternative_favorite(call):
        rid=call.data.split(":",1)[1]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=dish_alternative_keyboard(rid,saved,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("dayfav:"))
    async def shared_dish_favorite(call):
        rid=call.data.split(":",1)[1]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=dish_day_keyboard(rid,saved,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("catalogopen:"))
    async def open_catalog_recipe(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        recipe=db.get_recipe(rid)
        if not recipe: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        saved=any(x["id"]==rid for x in db.favorites(call.from_user.id))
        available=queries.get(call.from_user.id,(None,""))[0].ingredients if call.from_user.id in pantry_results and call.from_user.id in queries else None
        await call.message.edit_text(recipe_text(recipe,settings["servings"],available,user_restrictions(settings)),parse_mode="HTML",reply_markup=catalog_card_keyboard(rid,offset,saved,db.recipe_feedback(call.from_user.id,rid)))
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
        await call.message.edit_reply_markup(reply_markup=catalog_card_keyboard(rid,offset,saved,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("allcatalogopen:"))
    async def open_all_catalog_recipe(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        recipe=db.get_recipe(rid)
        if not recipe: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        saved=any(x["id"]==rid for x in db.favorites(call.from_user.id))
        await call.message.edit_text(recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=all_catalog_card_keyboard(rid,offset,saved,db.recipe_feedback(call.from_user.id,rid)))
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
        await call.message.edit_reply_markup(reply_markup=all_catalog_card_keyboard(rid,offset,saved,db.recipe_feedback(call.from_user.id,rid)))
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
        index=int(index); options=filter_options(category,call.from_user.id)
        if index<0 or index>=len(options): await call.answer("Фильтр не найден",show_alert=True); return
        value=options[index]; selected=get_filter_state(call.from_user.id)[category]
        if value in selected: selected.remove(value)
        else:
            if category=="methods": selected.clear()
            selected.add(value)
        await show_filter_category(call.message,call.from_user.id,category,0)
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
        await call.message.edit_text(recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=filtered_card_keyboard(rid,offset,saved,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer()

    @dp.callback_query(F.data.startswith("filterfav:"))
    async def filtered_favorite(call):
        _,offset,rid=call.data.split(":",2); offset=int(offset)
        saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=filtered_card_keyboard(rid,offset,saved,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("recipe:"))
    async def open_recipe(call):
        rid=call.data.split(":",1)[1]; r=db.get_recipe(rid)
        if not r: await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,rid); settings=db.settings(call.from_user.id)
        fav=any(x["id"]==rid for x in db.favorites(call.from_user.id))
        await call.message.answer(recipe_text(r,settings["servings"]),parse_mode="HTML",reply_markup=recipe_keyboard(rid,fav,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer()

    @dp.callback_query(F.data.startswith("fav:"))
    async def favorite(call):
        rid=call.data.split(":",1)[1]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")
        await call.message.edit_reply_markup(reply_markup=recipe_keyboard(rid,saved,db.recipe_feedback(call.from_user.id,rid)))

    @dp.callback_query(F.data.startswith("cooked:"))
    async def cooked(call):
        rid=call.data.split(":",1)[1]
        db.mark_recipe_cooked(call.from_user.id,rid)
        db.add_history(call.from_user.id,rid)
        markup=call.message.reply_markup
        if markup:
            for row in markup.inline_keyboard:
                for button in row:
                    if button.callback_data==f"cooked:{rid}": button.text="✅ Приготовил"
            await call.message.edit_reply_markup(reply_markup=markup)
        await call.answer("Отметил в истории приготовленного 🍳")

    @dp.callback_query(F.data.startswith("feedback:"))
    async def recipe_feedback(call):
        _,field,rid=call.data.split(":",2)
        if field not in {"liked","not_suggest"}:
            await call.answer("Неизвестный тип оценки",show_alert=True); return
        enabled=db.toggle_recipe_feedback(call.from_user.id,rid,field)
        markup=call.message.reply_markup
        callback_data=f"feedback:{field}:{rid}"
        if markup:
            for row in markup.inline_keyboard:
                for button in row:
                    if button.callback_data==callback_data:
                        if field=="liked": button.text="👍 Понравилось ✓" if enabled else "👍 Понравилось"
                        else: button.text="↩️ Вернуть в подбор" if enabled else "🚫 Не предлагать"
            await call.message.edit_reply_markup(reply_markup=markup)
        if field=="liked":
            answer="Буду учитывать, что тебе понравилось 👍" if enabled else "Оценку убрал"
        else:
            answer="Блюдо исключено из рекомендаций" if enabled else "Блюдо вернулось в рекомендации"
        await call.answer(answer)

    @dp.callback_query(F.data.startswith("plus:"))
    async def plus_action(call):
        action=call.data.split(":",1)[1]
        uid=call.from_user.id
        if action=="home":
            await show_plus(call.message,uid,edit=True)
        elif action=="terms":
            await show_plus_terms(call.message,uid)
        elif action=="accept":
            if db.plus_active(uid) or db.plus_key_access(uid) or (config.ai_api_key and uid==config.admin_telegram_id):
                db.accept_plus_terms(uid)
                await show_plus(call.message,uid,edit=True)
                await call.answer("Условия приняты")
                return
            if not plus_ready():
                await call.answer("Dishly Plus ещё не настроен",show_alert=True)
                return
            db.accept_plus_terms(uid)
            await send_plus_invoice(call.message,uid)
        elif action=="subscribe":
            await send_plus_invoice(call.message,uid)
        elif action=="refresh":
            await show_plus(call.message,uid,edit=True)
        elif action=="cancel":
            row=db.plus_subscription(uid)
            if not row or not db.plus_active(uid):
                await call.answer("Активная подписка не найдена",show_alert=True)
                await show_plus(call.message,uid,edit=True)
                return
            if row[2]:
                await call.answer("Автопродление уже отключено")
                return
            try:
                await bot.edit_user_star_subscription(user_id=uid,telegram_payment_charge_id=row[1],is_canceled=True)
                db.cancel_plus_renewal(uid)
                await call.answer("Автопродление отключено")
                await show_plus(call.message,uid,edit=True)
            except TelegramAPIError:
                logging.exception("Could not cancel Dishly Plus subscription for user %s",uid)
                await call.answer("Не удалось отключить автопродление. Напиши /paysupport",show_alert=True)

    @dp.callback_query(F.data.startswith("admin:"))
    async def admin_access_action(call):
        uid=call.from_user.id
        if not config.admin_telegram_id or uid!=config.admin_telegram_id:
            await call.answer("Только для администратора",show_alert=True)
            return
        parts=call.data.split(":")
        action=parts[1]
        if action=="home":
            await call.message.edit_text("🛠 <b>Админ-панель Dishly</b>\n\nУправление доступом к ИИ-шефу. Каталог и остальные функции бота доступны всем.",parse_mode="HTML",reply_markup=admin_access_keyboard())
        elif action=="key" and len(parts)==3 and parts[2] in {"7","30","90"}:
            days=int(parts[2]); code=secrets.token_urlsafe(9).replace("-","").replace("_","").upper()
            db.create_plus_access_key(code,days,uid)
            await call.message.answer(f"🎟 Код на {days} дн. создан. Он одноразовый, действует сразу после активации и продлевает уже имеющийся доступ.\n\n<code>{code}</code>\n\nСкопируй и отправь его пользователю. Бот хранит только хэш кода, повторно показать его нельзя.",parse_mode="HTML")
            await call.answer("Код выпущен")
        elif action=="keys":
            rows=db.unused_plus_access_keys()
            if rows:
                body="🗂 <b>Неиспользованные коды</b> (последние 20)\n\n"+"\n".join(f"• …{row[0]} — {row[1]} дн., создан {datetime.fromtimestamp(row[2],timezone.utc).astimezone().strftime('%d.%m %H:%M')}" for row in rows)
            else:
                body="🗂 Неиспользованных кодов пока нет. Полные коды повторно не хранятся, поэтому показаны только последние 4 символа."
            await call.message.edit_text(body,parse_mode="HTML",reply_markup=admin_access_keyboard())
        elif action=="users":
            rows=db.active_plus_key_users()
            if not rows:
                await call.message.edit_text("👥 Сейчас нет активных доступов, выданных кодами.",reply_markup=admin_access_keyboard())
            else:
                users={row[0]:datetime.fromtimestamp(row[1],timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M") for row in rows}
                body="👥 <b>Активные доступы к ИИ-шефу по кодам</b>\n\n"+"\n".join(f"• <code>{user_id}</code> до {expiry}" for user_id,expiry in users.items())
                await call.message.edit_text(body,parse_mode="HTML",reply_markup=admin_access_users_keyboard(users))
        elif action=="revoke" and len(parts)==3 and parts[2].isdigit():
            target=int(parts[2]); count=db.revoke_plus_key_access(target)
            await call.answer("Доступ по коду отозван" if count else "Активный доступ по коду не найден",show_alert=True)
            rows=db.active_plus_key_users()
            users={row[0]:datetime.fromtimestamp(row[1],timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M") for row in rows}
            if users:
                body="👥 <b>Активные доступы к ИИ-шефу по кодам</b>\n\n"+"\n".join(f"• <code>{user_id}</code> до {expiry}" for user_id,expiry in users.items())
                await call.message.edit_text(body,parse_mode="HTML",reply_markup=admin_access_users_keyboard(users))
            else:
                await call.message.edit_text("👥 Активных доступов по кодам нет.",reply_markup=admin_access_keyboard())
        else:
            await call.answer("Неизвестное действие",show_alert=True)

    @dp.callback_query(F.data=="advisor:terms_accept")
    async def advisor_terms_accept(call):
        uid=call.from_user.id
        if not advisor_access(uid):
            await call.answer("Сначала активируй код или подписку",show_alert=True)
            return
        db.accept_plus_terms(uid)
        await show_plus(call.message,uid,edit=True)
        await call.answer("Условия приняты")

    @dp.callback_query(F.data=="advisor:start")
    async def advisor_start(call):
        uid=call.from_user.id
        if not advisor_access(uid):
            advisor_sessions.pop(uid,None)
            await show_plus(call.message,uid)
            await call.answer("Нужен Plus или код доступа")
            return
        if not db.plus_terms_accepted(uid):
            await show_plus_terms(call.message,uid,access_code=bool(db.plus_key_access(uid)) or uid==config.admin_telegram_id)
            await call.answer("Сначала прочитай условия",show_alert=True)
            return
        advisor_sessions.setdefault(uid,[])
        await call.message.answer("👩‍🍳 Напиши, что хочется приготовить или какие продукты есть. Учитываю настройки профиля.",reply_markup=ReplyKeyboardRemove())
        await call.message.answer("Когда закончишь, нажми кнопку:",reply_markup=advisor_cancel_keyboard())
        await call.answer()

    @dp.callback_query(F.data=="advisor:stop")
    async def advisor_stop(call):
        advisor_sessions.pop(call.from_user.id,None)
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer("Консультация завершена. Бесплатные рецепты доступны в меню 🍲",reply_markup=main_menu())
        await call.answer("Консультация завершена")

    @dp.pre_checkout_query()
    async def plus_pre_checkout(query):
        valid=(query.invoice_payload=="dishly_plus_monthly_v1" and query.currency=="XTR" and
               query.total_amount==config.plus_monthly_stars and plus_ready() and
               db.plus_terms_accepted(query.from_user.id) and not db.plus_active(query.from_user.id))
        if valid:
            await query.answer(ok=True)
        else:
            await query.answer(ok=False,error_message="Не удалось подтвердить Dishly Plus. Открой раздел Plus и попробуй снова.")

    @dp.message(F.successful_payment)
    async def plus_successful_payment(message):
        payment=message.successful_payment
        if payment.invoice_payload!="dishly_plus_monthly_v1":
            return
        if payment.currency!="XTR" or payment.total_amount<1:
            logging.error("Dishly Plus payment currency/amount invalid for user %s",message.from_user.id)
            await message.answer("Платёж получен, но не удалось автоматически активировать подписку. Напиши /paysupport.")
            return
        now=int(datetime.now(timezone.utc).timestamp())
        expires=payment.subscription_expiration_date or now+2592000
        recorded=db.record_plus_payment(message.from_user.id,payment.total_amount,payment.currency,payment.telegram_payment_charge_id,expires,now)
        if recorded:
            await message.answer("🎉 Dishly Plus активирован! Открой «Ещё» → «ИИ-советчик». Автопродление можно отключить командой /plus.")

    @dp.callback_query(F.data.startswith("report:start:"))
    async def start_recipe_report(call):
        rid=call.data.split(":",2)[2]
        recipe=db.get_recipe(rid)
        if not recipe:
            await call.answer("Рецепт не найден",show_alert=True); return
        report_mode[call.from_user.id]=rid
        await call.message.answer(f"⚠️ Что не так с рецептом «{html.escape(recipe['title'])}»? Опиши ошибку или что стоит поправить. До 1000 символов.",parse_mode="HTML",reply_markup=report_cancel_keyboard())
        await call.answer()

    @dp.callback_query(F.data=="report:cancel")
    async def cancel_recipe_report(call):
        report_mode.pop(call.from_user.id,None)
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("Отменено")

    @dp.callback_query(F.data=="menu")
    async def menu(call):
        pantry_mode.discard(call.from_user.id)
        pantry_results.discard(call.from_user.id)
        await show_home(call.message,call.from_user.id,call.from_user.first_name or "")
        await call.answer()

    @dp.callback_query(F.data=="pantry:cancel")
    async def cancel_pantry(call):
        pantry_mode.discard(call.from_user.id)
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.edit_text("Подбор по продуктам отменён.")
        await call.answer("Отменено")

    @dp.callback_query(F.data.startswith("hint:"))
    async def hint(call):
        prompt="Напиши продукты через запятую, например: яйца, помидоры." if call.data.endswith("ingredients") else "Напиши пожелание, например: быстрое, сытное или без духовки."
        await call.message.answer(prompt); await call.answer()

    @dp.callback_query(F.data.startswith("mealplan:open:"))
    async def open_meal_plan_recipe(call):
        index=int(call.data.rsplit(":",1)[1]); plan=db.meal_plan(call.from_user.id)
        if index not in range(len(plan)):
            await call.answer("План устарел. Открой его заново.",show_alert=True); return
        recipe=db.get_recipe(plan[index])
        if not recipe:
            await call.answer("Рецепт не найден",show_alert=True); return
        db.add_history(call.from_user.id,recipe["id"])
        settings=db.settings(call.from_user.id)
        saved=any(r["id"]==recipe["id"] for r in db.favorites(call.from_user.id))
        markup=meal_plan_recipe_keyboard(index,recipe["id"],saved,db.recipe_feedback(call.from_user.id,recipe["id"]))
        await call.message.edit_text(recipe_text(recipe,settings["servings"]),parse_mode="HTML",reply_markup=markup)
        await call.answer()

    @dp.callback_query(F.data=="mealplan:back")
    async def meal_plan_back(call):
        await show_meal_plan(call.message,call.from_user.id,edit=True)
        await call.answer()

    @dp.callback_query(F.data=="mealplan:refresh")
    async def refresh_meal_plan(call):
        await show_meal_plan(call.message,call.from_user.id,edit=True,regenerate=True)
        await call.answer("План обновлён")

    @dp.callback_query(F.data=="mealplan:shopping")
    async def meal_plan_shopping(call):
        await show_shopping_list(call.message,call.from_user.id,edit=True)
        await call.answer()

    @dp.callback_query(F.data.startswith("mealplan:fav:"))
    async def meal_plan_favorite(call):
        index=int(call.data.rsplit(":",1)[1]); plan=db.meal_plan(call.from_user.id)
        if index not in range(len(plan)):
            await call.answer("План устарел. Открой его заново.",show_alert=True); return
        rid=plan[index]; saved=db.toggle_favorite(call.from_user.id,rid)
        await call.message.edit_reply_markup(reply_markup=meal_plan_recipe_keyboard(index,rid,saved,db.recipe_feedback(call.from_user.id,rid)))
        await call.answer("Добавлено в избранное" if saved else "Убрано из избранного")

    @dp.callback_query(F.data.startswith("settings:"))
    async def settings_action(call):
        action=call.data.split(":")[1]; s=db.settings(call.from_user.id)
        if action in ("servings",): await call.message.edit_text("Выбери число порций:",reply_markup=servings_keyboard())
        elif action in ("exclude","allergies"): await show_restrictions(call.message,call.from_user.id,action)
        elif action=="equipment": await show_equipment(call.message,call.from_user.id)
        elif action=="restart_setup":
            text=("🔄 <b>Пройти первичную настройку заново?</b>\n\n"
                  "Сбросятся число порций, аллергии, исключённые продукты и доступная техника.\n"
                  "Избранное и история сохранятся.")
            await call.message.edit_text(text,parse_mode="HTML",reply_markup=setup_reset_keyboard())
        elif action=="clear":
            db.set_excluded(call.from_user.id,[]); db.set_allergies(call.from_user.id,[])
            await call.message.edit_text("Аллергии и исключённые продукты сброшены.",reply_markup=settings_keyboard(db.settings(call.from_user.id)))
        elif action=="back":
            info=("⚙️ Настройки\nАллергии: "+(", ".join(alphabetize(s["allergies"])) or "не указаны")+
                  "\nНе ем: "+(", ".join(alphabetize(s["excluded"])) or "ничего не исключено")+
                  "\nТехника: "+(", ".join(alphabetize(s["equipment"])) or "подбор не ограничен"))
            await call.message.edit_text(info,reply_markup=settings_keyboard(s))
        await call.answer()

    @dp.callback_query(F.data.startswith("setupreset:"))
    async def setup_reset_action(call):
        action=call.data.split(":",1)[1]
        if action=="confirm":
            db.reset_settings(call.from_user.id)
            name=html.escape(call.from_user.first_name or "")
            greeting=f"👋 Привет, {name}!" if name else "👋 Привет!"
            text=(f"{greeting}\n\n"
                  "Я помогу выбрать, что приготовить 🥘\n"
                  "Укажи порции, аллергии, продукты-исключения и доступную технику.\n\n"
                  "Любой шаг можно пропустить; настройки потом доступны в разделе «Ещё» → «Настройки».")
            await call.message.edit_text(text,reply_markup=first_start_keyboard())
            await call.answer("Настройки сброшены")
        else:
            await show_settings(call.message,edit=True)
            await call.answer("Сброс отменён")

    async def show_equipment(message,uid):
        selected=set(db.settings(uid)["equipment"])
        text=("🍳 Выбери технику, которая у тебя есть. Рецепты с другими способами приготовления будут исключены из подбора.\n"
              "Плита подходит для блюд в кастрюле и на сковороде; блюда без готовки останутся доступны.\n\n"
              "Если ничего не отметить, подбор не будет ограничен техникой.\n"
              "Доступно: "+(", ".join(alphabetize(selected)) or "не ограничиваю"))
        await message.edit_text(text,reply_markup=equipment_keyboard(EQUIPMENT_OPTIONS,selected))

    @dp.callback_query(F.data.startswith("equipment:"))
    async def toggle_equipment(call):
        index=int(call.data.split(":",1)[1])
        if index<0 or index>=len(EQUIPMENT_OPTIONS):
            await call.answer("Техника не найдена",show_alert=True); return
        selected=set(db.settings(call.from_user.id)["equipment"])
        item=EQUIPMENT_OPTIONS[index]
        if item in selected: selected.remove(item)
        else: selected.add(item)
        db.set_equipment(call.from_user.id,alphabetize(selected))
        await show_equipment(call.message,call.from_user.id)
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
        s=db.settings(call.from_user.id)
        if category=="allergies": options=prioritize_selected(ALLERGY_OPTIONS,s["allergies"])
        elif category=="excluded": options=prioritize_selected(set(ingredient_filter_options())|{"молочное","глютен","мясо"},s["excluded"])
        else: await call.answer("Раздел не найден",show_alert=True); return
        if index<0 or index>=len(options): await call.answer("Пункт не найден",show_alert=True); return
        field="allergies" if category=="allergies" else "excluded"
        values=set(s[field]); value=options[index]
        if value in values: values.remove(value)
        else: values.add(value)
        if field=="allergies": db.set_allergies(call.from_user.id,sorted(values))
        else: db.set_excluded(call.from_user.id,sorted(values))
        await show_restrictions(call.message,call.from_user.id,category,0); await call.answer()

    @dp.errors()
    async def errors(event):
        logging.exception("Unhandled bot error: %s",type(event.exception).__name__)

    try:
        while True:
            try:
                logging.info("Dishly polling starting")
                await dp.start_polling(bot, close_bot_session=False)
                break
            except TelegramNetworkError:
                logging.exception("Telegram API is unreachable; retrying in 30 seconds")
                await asyncio.sleep(30)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

