import unittest
import sqlite3
import tempfile
import os

from dishly.parser import parse_query
from dishly.search import rank_recipes, filter_recipes, blocked, recipe_ingredients
from dishly.data.recipes import RECIPES
from dishly.database import Database
from dishly.keyboards import all_catalog_keyboard, filter_options_keyboard, main_menu, more_menu
from dishly.bot import normalize_restriction_category
from dishly.bot import prioritize_selected

class ParserTests(unittest.TestCase):
    def test_mixed_query(self):
        q=parse_query("Есть яйца, помидоры, хочу быстрое")
        self.assertEqual(q.ingredients,{"яйца","помидоры"})
        self.assertIn("быстро",q.tags)
        self.assertEqual(q.max_minutes,20)

    def test_exclusion(self):
        q=parse_query("сытное без лука")
        self.assertIn("лук",q.excluded)
        self.assertNotIn("лук",q.ingredients)

    def test_unrecognized(self):
        self.assertFalse(parse_query("привет, расскажи анекдот").understood)

    def test_product_exclusion_screen_uses_supported_category_key(self):
        self.assertEqual(normalize_restriction_category("exclude"),"excluded")
        self.assertEqual(normalize_restriction_category("allergies"),"allergies")

    def test_colloquial_sweet_and_tasty(self):
        q=parse_query("хочу чото вкусненького и сладкого")
        self.assertIn("вкусное",q.tags)
        self.assertIn("сладкое",q.tags)

    def test_local_filters_understand_colloquial_request(self):
        q=parse_query("хочу чего-нибудь сладенького")
        self.assertIn("сладкое",q.tags)

    def test_device_and_vessel_word_forms_use_one_canonical_filter(self):
        for phrase in ("готовь в микроволновке", "поставь у микроволновки", "разогрей в микроволновую печь"):
            self.assertEqual(parse_query(phrase).tags,{"микроволновка"})
        self.assertEqual(parse_query("сделай в аерогриле").tags,{"аэрогриль"})
        self.assertEqual(parse_query("приготовь в кастрюле").tags,{"кастрюля"})

class SearchTests(unittest.TestCase):
    def test_ingredient_match_ranks_first(self):
        q=parse_query("яйца помидоры")
        rows=rank_recipes(RECIPES,q,limit=5)
        self.assertTrue(rows)
        self.assertEqual(rows[0][1]["id"],"omelet-tomato")

    def test_ingredient_query_hides_recipes_missing_that_ingredient(self):
        rows=rank_recipes(RECIPES,parse_query("макароны"),limit=100)
        self.assertTrue(rows)
        self.assertTrue(all("макароны" in recipe_ingredients(row[1]) for row in rows))

    def test_user_exclusion_filters(self):
        q=parse_query("сытное")
        rows=rank_recipes(RECIPES,q,user_exclusions=["лук"],limit=100)
        self.assertNotIn("chicken-rice",[row[1]["id"] for row in rows])

    def test_cooking_method_filters_return_recipes_for_that_method(self):
        microwave=rank_recipes(RECIPES,parse_query("в микроволновке"),limit=100)
        airfryer=rank_recipes(RECIPES,parse_query("в аерогриле"),limit=100)
        pots=rank_recipes(RECIPES,parse_query("в кастрюле"),limit=100)
        self.assertEqual({row[1]["id"] for row in microwave},{"microwave-oatmeal","microwave-mug-cake"})
        self.assertEqual({row[1]["id"] for row in airfryer},{"airfryer-potatoes","airfryer-chicken"})
        self.assertIn("chicken-noodle-soup",{row[1]["id"] for row in pots})

    def test_interactive_filters_require_every_selected_condition(self):
        rows=filter_recipes(RECIPES,ingredients=["банан"],tags=["микроволновка"],max_minutes=10)
        self.assertEqual([recipe["id"] for recipe in rows],["microwave-oatmeal"])
        none=filter_recipes(RECIPES,ingredients=["банан","курица"])
        self.assertEqual(none,[])

    def test_equipment_filters_include_every_recipe_using_that_method(self):
        for method in ("микроволновка","аэрогриль","кастрюля","сковорода","духовка","без готовки"):
            with self.subTest(method=method):
                actual={recipe["id"] for recipe in filter_recipes(RECIPES,tags=[method])}
                expected={recipe["id"] for recipe in RECIPES if recipe["method"]==method}
                self.assertTrue(expected.issubset(actual))

    def test_allergy_and_excluded_ingredients_filter_recipes(self):
        omelet=next(recipe for recipe in RECIPES if recipe["id"]=="omelet-tomato")
        self.assertNotIn(omelet,filter_recipes(RECIPES,user_exclusions=["яйца"]))
        self.assertNotIn(omelet,filter_recipes(RECIPES,user_exclusions=["молочное"]))
        self.assertIn(omelet,filter_recipes(RECIPES,user_exclusions=["грибы"]))
        hummus=next(recipe for recipe in RECIPES if recipe["id"]=="hummus")
        shrimp=next(recipe for recipe in RECIPES if recipe["id"]=="shrimp-pasta")
        self.assertTrue(blocked(hummus,["кунжут"]))
        self.assertTrue(blocked(shrimp,["морепродукты"]))
        self.assertTrue(blocked(shrimp,["молочное"]))
        barley=next(recipe for recipe in RECIPES if any(i["name"]=="перловка" for i in recipe["ingredients"]))
        self.assertTrue(blocked(barley,["глютен"]))

    def test_meat_exclusion_and_vegetarian_tag_remove_meat_fish_and_seafood(self):
        meat_terms={"мясо","курица","фарш","котлеты","говядина","свинина","индейка","баранина","бекон","сосиски","колбаса"}
        fish_terms={"рыба","тунец","лосось","сельдь","креветки","креветка","мидии","краб","кальмар"}
        meat_free=filter_recipes(RECIPES,user_exclusions=["мясо"])
        vegetarian=filter_recipes(RECIPES,tags=["вегетарианское"])
        self.assertTrue(all(not ({i["name"] for i in recipe["ingredients"]}&meat_terms) for recipe in meat_free))
        self.assertTrue(all(not ({i["name"] for i in recipe["ingredients"]}&(meat_terms|fish_terms)) for recipe in vegetarian))

    def test_baking_filter_finds_pastries_and_bakes(self):
        ids={recipe["id"] for recipe in filter_recipes(RECIPES,tags=["выпечка"])}
        self.assertTrue({"apple-muffins","curd-casserole","potato-cheese-bake","lavash-pizza","pear-cake"}.issubset(ids))
        self.assertNotIn("chicken-potato-bake",ids)

    def test_soup_and_salad_titles_have_the_matching_filter_tag(self):
        for recipe in RECIPES:
            title=recipe["title"].casefold()
            if "суп" in title: self.assertIn("суп",recipe["tags"],recipe["id"])
            if "салат" in title: self.assertIn("салат",recipe["tags"],recipe["id"])

    def test_selected_filter_options_are_first(self):
        ordered=prioritize_selected(["сыр","курица","макароны","яйца"],{"макароны","яйца"})
        self.assertEqual(ordered[:2],["макароны","яйца"])

    def test_cutlets_and_muffins_have_search_facets(self):
        cutlet=parse_query("макароны с котлетами")
        muffin=parse_query("хочу маффины, что-нибудь вкусненькое сладкое")
        cutlet_rows=rank_recipes(RECIPES,cutlet,limit=5)
        muffin_rows=rank_recipes(RECIPES,muffin,limit=5)
        self.assertEqual(cutlet_rows[0][1]["id"],"pasta-cutlets")
        self.assertIn(muffin_rows[0][1]["id"],{"apple-muffins","chocolate-cupcakes","blueberry-muffins","cherry-muffins"})

class SharedDishTests(unittest.TestCase):
    def test_daily_dish_is_shared_and_variants_do_not_repeat(self):
        database=Database(":memory:")
        database.set_shared_dish_today("omelet-tomato")
        database.mark_user_alternative(123,"apple-muffins")
        self.assertEqual(database.shared_dish_today(),"omelet-tomato")
        self.assertEqual(database.user_alternatives_today(123),{"apple-muffins"})
        self.assertEqual(database.shared_dish_today(),"omelet-tomato")
        database.ensure_user(123)
        database.set_allergies(123,["яйца","молочное"])
        self.assertEqual(set(database.settings(123)["allergies"]),{"яйца","молочное"})
        database.conn.close()

    def test_existing_user_database_gets_allergy_column(self):
        handle=tempfile.NamedTemporaryFile(suffix=".sqlite3",delete=False)
        path=handle.name; handle.close()
        try:
            old=sqlite3.connect(path)
            old.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY, servings INTEGER NOT NULL DEFAULT 2, excluded TEXT NOT NULL DEFAULT '[]')")
            old.execute("INSERT INTO users(user_id) VALUES(789)"); old.commit(); old.close()
            database=Database(path)
            self.assertEqual(database.settings(789)["allergies"],[])
            database.conn.close()
        finally:
            os.unlink(path)

class CatalogTests(unittest.TestCase):
    def test_main_menu_keeps_primary_actions_visible_and_groups_secondary_actions(self):
        main={button.text for row in main_menu().keyboard for button in row}
        more={button.text for row in more_menu().keyboard for button in row}
        self.assertTrue({"🍳 Подобрать блюдо","🔎 Фильтры","📚 Каталог","🍲 Блюдо дня","✨ Ещё"}.issubset(main))
        self.assertTrue({"⭐ Избранное","🕘 История","⚙️ Настройки","❔ Помощь","🏠 Главное меню"}.issubset(more))

    def test_catalog_has_new_detailed_recipes_and_two_way_paging(self):
        self.assertEqual(len(RECIPES),100)
        self.assertEqual(len({recipe["id"] for recipe in RECIPES}),100)
        self.assertTrue(all(len(recipe["steps"])>=4 for recipe in RECIPES))
        soup=next(recipe for recipe in RECIPES if recipe["id"]=="chicken-noodle-soup")
        self.assertGreaterEqual(len(soup["steps"]),4)
        keyboard=all_catalog_keyboard(RECIPES[5:10],offset=5,has_more=True)
        callbacks=[button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("allcatalog:0",callbacks)
        self.assertIn("allcatalog:10",callbacks)
        option_kb=filter_options_keyboard("ingredients",[f"продукт {i}" for i in range(12)],set())
        self.assertTrue(all(len(row)<=2 for row in option_kb.inline_keyboard))

    def test_history_keeps_only_latest_ten(self):
        database=Database(":memory:")
        recipes=database.recipes()
        for recipe in recipes[:12]:
            database.add_history(456,recipe["id"])
        history=database.history(456)
        self.assertEqual(len(history),10)
        self.assertEqual(history[0]["id"],recipes[11]["id"])
        self.assertNotIn(recipes[0]["id"],[recipe["id"] for recipe in history])
        database.conn.close()

if __name__=="__main__": unittest.main()

