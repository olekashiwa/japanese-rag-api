import csv

terms = [
    {"ru": "кофе", "en": "coffee", "jp": "コーヒー", "jp_furigana": "こーひー"},
    {"ru": "зерно", "en": "bean", "jp": "豆", "jp_furigana": "まめ"},
    {"ru": "обжарка", "en": "roast", "jp": "焙煎", "jp_furigana": "ばいせん"},
    {
        "ru": "экстракция",
        "en": "extraction",
        "jp": "抽出",
        "jp_furigana": "ちゅうしゅつ",
    },
    {"ru": "крепость", "en": "strength", "jp": "濃度", "jp_furigana": "のうど"},
    {"ru": "кислотность", "en": "acidity", "jp": "酸味", "jp_furigana": "さんみ"},
    {"ru": "тело", "en": "body", "jp": "ボディ", "jp_furigana": "ぼでぃ"},
    {"ru": "аромат", "en": "aroma", "jp": "香り", "jp_furigana": "かおり"},
    {"ru": "букет", "en": "bouquet", "jp": "香気", "jp_furigana": "こうき"},
    {"ru": "дегазация", "en": "degassing", "jp": "脱ガス", "jp_furigana": "だつがす"},
    {
        "ru": "эспрессо",
        "en": "espresso",
        "jp": "エスプレッソ",
        "jp_furigana": "えすぷれっそ",
    },
    {"ru": "турка", "en": "cezve/ibrik", "jp": "土瓶", "jp_furigana": "つぼ"},
    {"ru": "помол", "en": "grind", "jp": "粉砕", "jp_furigana": "ふんさい"},
    {"ru": "фильтр", "en": "filter", "jp": "フィルター", "jp_furigana": "ふぉるたー"},
    {"ru": "воронка", "en": "pour-over", "jp": "ドリップ", "jp_furigana": "どりっぷ"},
    {"ru": "TDS", "en": "TDS", "jp": "溶存固形分", "jp_furigana": "ようそんこせいぶん"},
    {
        "ru": "профиль обжарки",
        "en": "roast profile",
        "jp": "焙煎プロファイル",
        "jp_furigana": "ばいせんぷろふぁいる",
    },
    {
        "ru": "экстрактивность",
        "en": "extractability",
        "jp": "抽出性",
        "jp_furigana": "ちゅうしゅつせい",
    },
]

with open("coffee_terms.tsv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=["ru", "en", "jp", "jp_furigana"], delimiter="\t"
    )
    writer.writeheader()
    writer.writerows(terms)

print("TSV создан: coffee_terms.tsv")
