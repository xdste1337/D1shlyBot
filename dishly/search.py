from .data.vocabulary import EXCLUSION_GROUPS

ALIASES = {"сливочное масло":"масло"}

def canonical(name):
    return ALIASES.get(name, name)

def recipe_ingredients(recipe):
    return {canonical(i["name"]) for i in recipe["ingredients"] if not i.get("optional", False)}

def blocked(recipe, exclusions):
    terms = recipe_ingredients(recipe)
    allergens = set(recipe["allergens"])
    if "острое" in exclusions and "острое" in recipe["tags"]:
        return True
    for exclusion in exclusions:
        group = EXCLUSION_GROUPS.get(exclusion, [exclusion])
        if terms.intersection(group) or exclusion in allergens or any(x in allergens for x in group):
            return True
    return False

def rank_recipes(recipes, query, user_exclusions=(), offset=0, limit=5):
    ranked = []
    exclusions = set(query.excluded) | set(user_exclusions)
    for recipe in recipes:
        if blocked(recipe, exclusions): continue
        terms = recipe_ingredients(recipe)
        matched = terms & query.ingredients
        missing = query.ingredients - terms
        # Hard constraints in requests filter candidates; retain near matches when otherwise no exact hits.
        tag_overlap = set(recipe["tags"]) & query.tags
        time_ok = query.max_minutes is None or recipe["minutes"] <= query.max_minutes
        points = 0.0
        if query.ingredients:
            points += len(matched) / len(query.ingredients) * 10
            points -= min(len(missing), 3) * 1.4
        if query.tags: points += len(tag_overlap) * 3.0 - (len(query.tags-tag_overlap))*1.5
        if query.max_minutes: points += 2 if time_ok else -4
        if not query.ingredients and not query.tags and not query.max_minutes: continue
        # Surface imperfect results as such, without claiming failed conditions matched.
        ranked.append((points, recipe, sorted(matched), sorted(missing), time_ok, sorted(query.tags-tag_overlap)))
    # Enforce explicit time limits whenever at least one recipe satisfies them. If none do,
    # return the nearest slower options and label the mismatch in the result.
    if query.max_minutes and any(row[4] for row in ranked):
        ranked = [row for row in ranked if row[4]]
    if query.tags and any(not row[5] for row in ranked):
        ranked = [row for row in ranked if not row[5]]
    ranked.sort(key=lambda row: (-row[0], row[1]["minutes"], row[1]["title"]))
    return ranked[offset:offset+limit]

