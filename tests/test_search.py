import unittest

from dishly.parser import parse_query
from dishly.search import rank_recipes
from dishly.data.recipes import RECIPES
from dishly.database import Database
from dishly.keyboards import all_catalog_keyboard

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

    def test_colloquial_sweet_and_tasty(self):
        q=parse_query("хочу чото вкусненького и сладкого")
        self.assertIn("вкусное",q.tags)
        self.assertIn("сладкое",q.tags)

    def test_local_filters_understand_colloquial_request(self):
        q=parse_query("хочу чего-нибудь сладенького")
        self.assertIn("сладкое",q.tags)

class SearchTests(unittest.TestCase):
    def test_ingredient_match_ranks_first(self):
        q=parse_query("яйца помидоры")
        rows=rank_recipes(RECIPES,q,limit=5)
        self.assertTrue(rows)
        self.assertEqual(rows[0][1]["id"],"omelet-tomato")

    def test_user_exclusion_filters(self):
        q=parse_query("сытное")
        rows=rank_recipes(RECIPES,q,user_exclusions=["лук"],limit=100)
        self.assertNotIn("chicken-rice",[row[1]["id"] for row in rows])

    def test_cutlets_and_muffins_have_search_facets(self):
        cutlet=parse_query("макароны с котлетами")
        muffin=parse_query("хочу маффины, что-нибудь вкусненькое сладкое")
        cutlet_rows=rank_recipes(RECIPES,cutlet,limit=5)
        muffin_rows=rank_recipes(RECIPES,muffin,limit=5)
        self.assertEqual(cutlet_rows[0][1]["id"],"pasta-cutlets")
        self.assertEqual(muffin_rows[0][1]["id"],"apple-muffins")

class SharedDishTests(unittest.TestCase):
    def test_daily_dish_is_shared_and_variants_do_not_repeat(self):
        database=Database(":memory:")
        database.set_shared_dish_today("omelet-tomato")
        database.mark_user_alternative(123,"apple-muffins")
        self.assertEqual(database.shared_dish_today(),"omelet-tomato")
        self.assertEqual(database.user_alternatives_today(123),{"apple-muffins"})
        self.assertEqual(database.shared_dish_today(),"omelet-tomato")
        database.conn.close()

class CatalogTests(unittest.TestCase):
    def test_catalog_has_new_detailed_recipes_and_two_way_paging(self):
        self.assertGreaterEqual(len(RECIPES),30)
        soup=next(recipe for recipe in RECIPES if recipe["id"]=="chicken-noodle-soup")
        self.assertGreaterEqual(len(soup["steps"]),4)
        keyboard=all_catalog_keyboard(RECIPES[5:10],offset=5,has_more=True)
        callbacks=[button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("allcatalog:0",callbacks)
        self.assertIn("allcatalog:10",callbacks)

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

