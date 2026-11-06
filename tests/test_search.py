import unittest

from dishly.parser import parse_query
from dishly.search import rank_recipes
from dishly.data.recipes import RECIPES

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

if __name__=="__main__": unittest.main()

