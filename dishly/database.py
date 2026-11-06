import json
import sqlite3
from datetime import date

from .data.recipes import RECIPES

class Database:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.init()

    def init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,minutes INTEGER NOT NULL,difficulty TEXT NOT NULL,servings INTEGER NOT NULL,tags TEXT NOT NULL,method TEXT NOT NULL,allergens TEXT NOT NULL,ingredients TEXT NOT NULL,steps TEXT NOT NULL,source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, servings INTEGER NOT NULL DEFAULT 2, excluded TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), PRIMARY KEY(user_id,recipe_id));
        CREATE TABLE IF NOT EXISTS history(user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,recipe_id));
        CREATE TABLE IF NOT EXISTS dish_of_day(user_id INTEGER NOT NULL, day TEXT NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), PRIMARY KEY(user_id,day,recipe_id));
        """)
        self.conn.executemany("""
            INSERT INTO recipes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,description=excluded.description,
            minutes=excluded.minutes,difficulty=excluded.difficulty,servings=excluded.servings,
            tags=excluded.tags,method=excluded.method,allergens=excluded.allergens,
            ingredients=excluded.ingredients,steps=excluded.steps,source=excluded.source
        """, [self._row(r) for r in RECIPES])
        self.conn.commit()

    @staticmethod
    def _row(r):
        return (r["id"],r["title"],r["description"],r["minutes"],r["difficulty"],r["servings"],json.dumps(r["tags"],ensure_ascii=False),r["method"],json.dumps(r["allergens"],ensure_ascii=False),json.dumps(r["ingredients"],ensure_ascii=False),json.dumps(r["steps"],ensure_ascii=False),r["source"])

    def recipes(self):
        return [self._dict(row) for row in self.conn.execute("SELECT * FROM recipes")]

    @staticmethod
    def _dict(row):
        result = dict(row)
        for key in ("tags", "allergens", "ingredients", "steps"):
            result[key] = json.loads(result[key])
        return result

    def get_recipe(self, rid):
        row = self.conn.execute("SELECT * FROM recipes WHERE id=?", (rid,)).fetchone()
        return self._dict(row) if row else None

    def ensure_user(self, uid):
        self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,)); self.conn.commit()

    def settings(self, uid):
        self.ensure_user(uid)
        r = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return {"servings": r["servings"], "excluded": json.loads(r["excluded"])}

    def set_servings(self, uid, n):
        self.ensure_user(uid); self.conn.execute("UPDATE users SET servings=? WHERE user_id=?", (n,uid)); self.conn.commit()

    def set_excluded(self, uid, values):
        self.ensure_user(uid); self.conn.execute("UPDATE users SET excluded=? WHERE user_id=?", (json.dumps(values,ensure_ascii=False),uid)); self.conn.commit()

    def favorites(self, uid):
        return [self.get_recipe(r[0]) for r in self.conn.execute("SELECT recipe_id FROM favorites WHERE user_id=? ORDER BY rowid DESC", (uid,))]

    def toggle_favorite(self, uid, rid):
        row = self.conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND recipe_id=?", (uid,rid)).fetchone()
        if row: self.conn.execute("DELETE FROM favorites WHERE user_id=? AND recipe_id=?", (uid,rid)); saved=False
        else: self.conn.execute("INSERT OR IGNORE INTO favorites VALUES(?,?)",(uid,rid)); saved=True
        self.conn.commit(); return saved

    def add_history(self, uid, rid):
        self.conn.execute("INSERT INTO history(user_id,recipe_id,viewed_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,recipe_id) DO UPDATE SET viewed_at=CURRENT_TIMESTAMP",(uid,rid)); self.conn.commit()

    def history(self, uid):
        return [self.get_recipe(r[0]) for r in self.conn.execute("SELECT recipe_id FROM history WHERE user_id=? ORDER BY viewed_at DESC LIMIT 20",(uid,))]

    def shown_today(self, uid):
        return {r[0] for r in self.conn.execute("SELECT recipe_id FROM dish_of_day WHERE user_id=? AND day=?",(uid,date.today().isoformat()))}

    def mark_today(self, uid, rid):
        self.conn.execute("INSERT OR IGNORE INTO dish_of_day VALUES(?,?,?)",(uid,date.today().isoformat(),rid)); self.conn.commit()

