import json
import sqlite3
from datetime import date

from .data.recipes import RECIPES
from .data.nutrition import estimate_kcal_per_serving

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
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, servings INTEGER NOT NULL DEFAULT 2, excluded TEXT NOT NULL DEFAULT '[]', allergies TEXT NOT NULL DEFAULT '[]', equipment TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), PRIMARY KEY(user_id,recipe_id));
        CREATE TABLE IF NOT EXISTS history(user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,recipe_id));
        CREATE TABLE IF NOT EXISTS dish_of_day(user_id INTEGER NOT NULL, day TEXT NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), PRIMARY KEY(user_id,day,recipe_id));
        CREATE TABLE IF NOT EXISTS shared_dish_of_day(day TEXT PRIMARY KEY, recipe_id TEXT NOT NULL REFERENCES recipes(id));
        CREATE TABLE IF NOT EXISTS user_dish_alternatives(user_id INTEGER NOT NULL, day TEXT NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), PRIMARY KEY(user_id,day,recipe_id));
        CREATE TABLE IF NOT EXISTS meal_plans(user_id INTEGER PRIMARY KEY, recipe_ids TEXT NOT NULL, plan_date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recipe_feedback(user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), cooked_at TEXT, liked INTEGER NOT NULL DEFAULT 0, not_suggest INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,recipe_id));
        CREATE TABLE IF NOT EXISTS recipe_reports(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL REFERENCES recipes(id), message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, delivered INTEGER NOT NULL DEFAULT 0);
        """)
        user_columns={row[1] for row in self.conn.execute("PRAGMA table_info(users)")}
        if "allergies" not in user_columns:
            self.conn.execute("ALTER TABLE users ADD COLUMN allergies TEXT NOT NULL DEFAULT '[]'")
        if "equipment" not in user_columns:
            self.conn.execute("ALTER TABLE users ADD COLUMN equipment TEXT NOT NULL DEFAULT '[]'")
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
        result["kcal_per_serving"] = estimate_kcal_per_serving(result)
        return result

    def get_recipe(self, rid):
        row = self.conn.execute("SELECT * FROM recipes WHERE id=?", (rid,)).fetchone()
        return self._dict(row) if row else None

    def ensure_user(self, uid):
        cursor = self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        self.conn.commit()
        return cursor.rowcount == 1

    def settings(self, uid):
        self.ensure_user(uid)
        r = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return {"servings": r["servings"], "excluded": json.loads(r["excluded"]), "allergies": json.loads(r["allergies"]), "equipment": json.loads(r["equipment"])}

    def set_servings(self, uid, n):
        self.ensure_user(uid); self.conn.execute("UPDATE users SET servings=? WHERE user_id=?", (n,uid)); self.conn.commit()

    def set_excluded(self, uid, values):
        self.ensure_user(uid); self.conn.execute("UPDATE users SET excluded=? WHERE user_id=?", (json.dumps(values,ensure_ascii=False),uid)); self.conn.commit()

    def set_allergies(self, uid, values):
        self.ensure_user(uid); self.conn.execute("UPDATE users SET allergies=? WHERE user_id=?", (json.dumps(values,ensure_ascii=False),uid)); self.conn.commit()

    def set_equipment(self, uid, values):
        self.ensure_user(uid); self.conn.execute("UPDATE users SET equipment=? WHERE user_id=?", (json.dumps(values,ensure_ascii=False),uid)); self.conn.commit()

    def reset_settings(self, uid):
        self.ensure_user(uid)
        self.conn.execute("UPDATE users SET servings=2, excluded='[]', allergies='[]', equipment='[]' WHERE user_id=?", (uid,))
        self.conn.commit()

    def favorites(self, uid):
        return [self.get_recipe(r[0]) for r in self.conn.execute("SELECT recipe_id FROM favorites WHERE user_id=? ORDER BY rowid DESC", (uid,))]

    def toggle_favorite(self, uid, rid):
        row = self.conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND recipe_id=?", (uid,rid)).fetchone()
        if row: self.conn.execute("DELETE FROM favorites WHERE user_id=? AND recipe_id=?", (uid,rid)); saved=False
        else: self.conn.execute("INSERT OR IGNORE INTO favorites VALUES(?,?)",(uid,rid)); saved=True
        self.conn.commit(); return saved

    def add_history(self, uid, rid):
        with self.conn:
            self.conn.execute("INSERT INTO history(user_id,recipe_id,viewed_at) VALUES(?,?,strftime('%Y-%m-%d %H:%M:%f','now')) ON CONFLICT(user_id,recipe_id) DO UPDATE SET viewed_at=strftime('%Y-%m-%d %H:%M:%f','now')",(uid,rid))
            self.conn.execute("DELETE FROM history WHERE user_id=? AND recipe_id NOT IN (SELECT recipe_id FROM history WHERE user_id=? ORDER BY viewed_at DESC,rowid DESC LIMIT 10)",(uid,uid))

    def history(self, uid):
        return [self.get_recipe(r[0]) for r in self.conn.execute("SELECT recipe_id FROM history WHERE user_id=? ORDER BY viewed_at DESC,rowid DESC LIMIT 10",(uid,))]

    def meal_plan(self, uid):
        row=self.conn.execute("SELECT recipe_ids,plan_date FROM meal_plans WHERE user_id=?",(uid,)).fetchone()
        if not row or row[1]!=date.today().isoformat(): return []
        return json.loads(row[0])

    def set_meal_plan(self, uid, recipe_ids):
        with self.conn:
            self.conn.execute("INSERT INTO meal_plans(user_id,recipe_ids,plan_date) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET recipe_ids=excluded.recipe_ids,plan_date=excluded.plan_date",(uid,json.dumps(recipe_ids),date.today().isoformat()))

    def recipe_feedback(self, uid, rid):
        row=self.conn.execute("SELECT cooked_at,liked,not_suggest FROM recipe_feedback WHERE user_id=? AND recipe_id=?",(uid,rid)).fetchone()
        return {"cooked":bool(row and row[0]),"liked":bool(row and row[1]),"not_suggest":bool(row and row[2])}

    def mark_recipe_cooked(self, uid, rid):
        with self.conn:
            self.conn.execute("INSERT INTO recipe_feedback(user_id,recipe_id,cooked_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,recipe_id) DO UPDATE SET cooked_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP",(uid,rid))

    def toggle_recipe_feedback(self, uid, rid, field):
        if field not in {"liked","not_suggest"}:
            raise ValueError("Unsupported recipe feedback field")
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO recipe_feedback(user_id,recipe_id) VALUES(?,?)",(uid,rid))
            row=self.conn.execute(f"SELECT {field} FROM recipe_feedback WHERE user_id=? AND recipe_id=?",(uid,rid)).fetchone()
            value=not bool(row[0])
            self.conn.execute(f"UPDATE recipe_feedback SET {field}=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND recipe_id=?",(int(value),uid,rid))
        return value

    def not_suggested_recipe_ids(self, uid):
        return {row[0] for row in self.conn.execute("SELECT recipe_id FROM recipe_feedback WHERE user_id=? AND not_suggest=1",(uid,))}

    def liked_recipe_ids(self, uid):
        return {row[0] for row in self.conn.execute("SELECT recipe_id FROM recipe_feedback WHERE user_id=? AND liked=1",(uid,))}

    def recently_cooked_recipe_ids(self, uid, days=7):
        modifier=f"-{int(days)} days"
        return {row[0] for row in self.conn.execute("SELECT recipe_id FROM recipe_feedback WHERE user_id=? AND cooked_at>=datetime('now',?)",(uid,modifier))}

    def add_recipe_report(self, uid, rid, message):
        with self.conn:
            cursor=self.conn.execute("INSERT INTO recipe_reports(user_id,recipe_id,message) VALUES(?,?,?)",(uid,rid,message))
        return cursor.lastrowid

    def pending_recipe_reports(self, limit=10):
        return self.conn.execute("SELECT id,user_id,recipe_id,message,created_at FROM recipe_reports WHERE delivered=0 ORDER BY id DESC LIMIT ?",(limit,)).fetchall()

    def mark_recipe_report_delivered(self, report_id):
        with self.conn:
            self.conn.execute("UPDATE recipe_reports SET delivered=1 WHERE id=?",(report_id,))

    def shown_today(self, uid):
        return {r[0] for r in self.conn.execute("SELECT recipe_id FROM dish_of_day WHERE user_id=? AND day=?",(uid,date.today().isoformat()))}

    def mark_today(self, uid, rid):
        self.conn.execute("INSERT OR IGNORE INTO dish_of_day VALUES(?,?,?)",(uid,date.today().isoformat(),rid)); self.conn.commit()

    def shared_dish_today(self):
        row = self.conn.execute("SELECT recipe_id FROM shared_dish_of_day WHERE day=?",(date.today().isoformat(),)).fetchone()
        return row[0] if row else None

    def set_shared_dish_today(self, rid):
        day=date.today().isoformat()
        with self.conn:
            self.conn.execute("INSERT INTO shared_dish_of_day(day,recipe_id) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET recipe_id=excluded.recipe_id",(day,rid))

    def user_alternatives_today(self, uid):
        return {r[0] for r in self.conn.execute("SELECT recipe_id FROM user_dish_alternatives WHERE user_id=? AND day=?",(uid,date.today().isoformat()))}

    def mark_user_alternative(self, uid, rid):
        self.conn.execute("INSERT OR IGNORE INTO user_dish_alternatives(user_id,day,recipe_id) VALUES(?,?,?)",(uid,date.today().isoformat(),rid))
        self.conn.commit()

