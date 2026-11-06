import re
from dataclasses import dataclass

from .data.vocabulary import INGREDIENTS, TAGS

@dataclass
class ParsedQuery:
    ingredients: set[str]
    tags: set[str]
    excluded: set[str]
    max_minutes: int | None
    raw: str

    @property
    def understood(self):
        return bool(self.ingredients or self.tags or self.excluded or self.max_minutes)


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    return re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE).strip()


def parse_query(text: str) -> ParsedQuery:
    norm = normalize(text)
    ingredients, tags, excluded = set(), set(), set()
    # Negated ingredient phrases are removed from positive matching and retained as exclusions.
    for canonical, variants in INGREDIENTS.items():
        for variant in variants:
            v = normalize(variant)
            if re.search(rf"\bбез\s+{re.escape(v)}\b", norm):
                excluded.add(canonical)
            elif re.search(rf"\bне\s+{re.escape(v)}\b", norm):
                excluded.add(canonical)
            elif re.search(rf"\b{re.escape(v)}\b", norm):
                ingredients.add(canonical)
    if re.search(r"\bбез\s+молочн\w*\b", norm): excluded.add("молочное")
    if re.search(r"\bбез\s+глютен\w*\b", norm): excluded.add("глютен")
    if re.search(r"\b(?:не\s+остр\w*|без\s+остр\w*)\b", norm): excluded.add("острое")
    for tag, variants in TAGS.items():
        if any(re.search(rf"\b{re.escape(normalize(v))}\b", norm) for v in variants): tags.add(tag)
    m = re.search(r"(?:до|не более|меньше)\s*(\d{1,3})\s*минут", norm)
    max_minutes = int(m.group(1)) if m else (20 if "быстро" in tags else None)
    ingredients -= excluded
    return ParsedQuery(ingredients, tags, excluded, max_minutes, text[:500])

