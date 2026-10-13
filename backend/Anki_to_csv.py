import csv

terms = [
    {"ru": "переменная", "en": "variable", "jp": "変数", "jp_furigana": "へんすう"},
    {"ru": "функция", "en": "function", "jp": "関数", "jp_furigana": "かんすう"},
    {"ru": "цикл", "en": "loop", "jp": "ループ", "jp_furigana": "るーぷ"},
    {"ru": "условие", "en": "condition", "jp": "条件", "jp_furigana": "じょうけん"},
    {"ru": "массив", "en": "array", "jp": "配列", "jp_furigana": "はいれつ"},
    {
        "ru": "объект",
        "en": "object",
        "jp": "オブジェクト",
        "jp_furigana": "おぶじぇくと",
    },
    {"ru": "класс", "en": "class", "jp": "クラス", "jp_furigana": "くらす"},
    {
        "ru": "интерфейс",
        "en": "interface",
        "jp": "インターフェース",
        "jp_furigana": "いんたーふぇーす",
    },
    {
        "ru": "наследование",
        "en": "inheritance",
        "jp": "継承",
        "jp_furigana": "けいしょう",
    },
    {
        "ru": "полиморфизм",
        "en": "polymorphism",
        "jp": "多態性",
        "jp_furigana": "たたいせい",
    },
    {
        "ru": "инкапсуляция",
        "en": "encapsulation",
        "jp": "カプセル化",
        "jp_furigana": "かぷせるか",
    },
    {
        "ru": "алгоритм",
        "en": "algorithm",
        "jp": "アルゴリズム",
        "jp_furigana": "あるごりずむ",
    },
    {
        "ru": "структура данных",
        "en": "data structure",
        "jp": "データ構造",
        "jp_furigana": "でーたこうぞう",
    },
    {"ru": "отладка", "en": "debugging", "jp": "デバッグ", "jp_furigana": "でばっぐ"},
    {
        "ru": "компиляция",
        "en": "compilation",
        "jp": "コンパイル",
        "jp_furigana": "こんぱいる",
    },
]

with open("anki_terms.tsv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=["ru", "en", "jp", "jp_furigana"], delimiter="\t"
    )
    writer.writeheader()
    writer.writerows(terms)

print("TSV создан: anki_terms.tsv")
