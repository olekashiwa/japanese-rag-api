#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_deck.py — сборка готовой колоды Anki (.apkg) для тренажёра слов и фраз
романа «コーヒーが冷めないうちに» (川口俊和).

Запуск из корня проекта kohi-anki интерпретатором Anki:

    "C:\\Users\\<user>\\AppData\\Local\\AnkiProgramFiles\\.venv\\Scripts\\python.exe"
    tools\\build_deck.py

Что делает:
  * читает src/data/novel.json (число заметок берётся из данных, ничего не зашито);
  * создаёт/обновляет два типа заметок: «Kohi Novel Card» и «Kohi Novel Phrase»;
  * создаёт иерархию колод コーヒーが冷めないうちに::<глава>::<Слова|Грамматика|Фразы>;
  * заливает по одной заметке на элемент (items) и на фрагмент (fragments)
    с детерминированными GUID;
  * экспортирует всё в anki/kohi_コーヒーが冷めないうちに.apkg.

ВАЖНО ПРО ИДЕМПОТЕНТНОСТЬ.
Anki сам присваивает типам заметок и колодам идентификаторы по текущему времени,
и повлиять на них через публичный API нельзя. Поэтому сборка идёт через
постоянную «рабочую коллекцию» anki/_build/kohi_build.anki2:
типы заметок, поля, шаблоны и колоды создаются в ней один раз, а при повторных
запусках переиспользуются. Благодаря этому id типов заметок и колод стабильны,
а GUID заметок детерминированы — повторный импорт .apkg обновляет/пропускает
существующие заметки, а не плодит дубликаты.
Рабочая коллекция лежит рядом с результатом (anki/_build/), а не во временной
папке tools/_ankitest/, и в .gitignore не исключена — её нельзя удалять,
иначе id типов заметок изменятся и повторный импорт создаст дубликаты
типов заметок вида «Kohi Novel Card+».

Реальная коллекция пользователя (%APPDATA%\\Anki2) НЕ затрагивается.
"""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re
import shutil
import stat
import sys

# --- вывод в консоль без падений на cp1251 -------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

ANKI_PY = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "AnkiProgramFiles",
    ".venv",
    "Scripts",
    "python.exe",
)

try:
    # anki.collection обязательно импортировать первым: в пакете anki
    # циклические импорты (anki.notes -> anki.cards -> anki.collection).
    import anki.collection  # noqa: F401
    from anki.collection import Collection
    import anki.import_export_pb2 as ie_pb
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        f"ОШИБКА: не удалось импортировать пакет 'anki' ({exc}).\n"
        "Запустите скрипт интерпретатором Python из Anki:\n"
        '  "%LOCALAPPDATA%\\AnkiProgramFiles\\.venv\\Scripts\\python.exe" tools\\build_deck.py\n'
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------
# Пути
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "src", "data", "novel.json")
OUT_DIR = os.path.join(ROOT, "anki")
# Рабочая коллекция сборки. Лежит рядом с результатом и НЕ во временной папке:
# её удаление меняет id типов заметок (см. пояснение в докстринге).
WORK_DIR = os.path.join(OUT_DIR, "_build")
WORK_COL = os.path.join(WORK_DIR, "kohi_build.anki2")
APKG_NAME = "kohi_コーヒーが冷めないうちに.apkg"
APKG_PATH = os.path.join(OUT_DIR, APKG_NAME)
REPORT_PATH = os.path.join(ROOT, "tools", "report_deck.txt")

SCHEMA_CONFIG_KEY = "kohiBuildSchemaFingerprint"


# --------------------------------------------------------------------------
# Имена типов заметок, полей, колод
# --------------------------------------------------------------------------
CARD_NT = "Kohi Novel Card"
PHRASE_NT = "Kohi Novel Phrase"

CARD_FIELDS = [
    "Term",
    "Reading",
    "Meaning",
    "Example",
    "ExampleMasked",
    "Translation",
    "Romaji",
    "Chapter",
    "Level",
    "Kind",
    "Note",
    "Source",
]

PHRASE_FIELDS = ["Text", "Romaji", "Translation", "Chapter", "Heading", "KeyVocab"]

DECK_VOCAB = "Слова"
DECK_GRAMMAR = "Грамматика"
DECK_PHRASES = "Фразы"

KIND_TO_DECK = {
    "vocab": DECK_VOCAB,
    "onomatopoeia": DECK_VOCAB,
    "grammar": DECK_GRAMMAR,
}

TAG_ROOT = "kohi"
TAG_AUTO_READING = "kohi::auto-reading"

TEMPLATE_CARD_1 = "01 Распознавание"
TEMPLATE_CARD_2 = "02 Воспроизведение"
TEMPLATE_CARD_3 = "03 Контекст"
TEMPLATE_PHRASE = "01 Фраза"


# --------------------------------------------------------------------------
# CSS шаблонов (один и тот же базовый блок для обоих типов заметок)
# --------------------------------------------------------------------------
SHARED_CSS = """\
/* ============================================================
   Kohi Novel — оформление карточек.
   Светлая тема задана в .card, тёмная — в .card.night_mode.
   Anki вешает класс night_mode/nightMode на body, а body в
   режиме повторения сам имеет класс .card, поэтому работает
   и .card.night_mode, и .night_mode .card (на всякий случай).
   ============================================================ */
.card {
  font-family: "Yu Gothic", "YuGothic", "Meiryo", "MS Gothic",
               "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
  font-size: 20px;
  line-height: 1.75;
  text-align: center;
  padding: 16px 14px 24px;
  box-sizing: border-box;

  --kohi-fg: #1f2328;
  --kohi-bg: #fbf9f5;
  --kohi-term: #14395e;
  --kohi-accent: #a8843f;
  --kohi-muted: #6b7280;
  --kohi-panel: rgba(0, 0, 0, 0.045);
  --kohi-line: rgba(0, 0, 0, 0.16);
  --kohi-note: #3f6b4a;
  --kohi-blank: #b0003a;

  color: var(--kohi-fg);
  background-color: var(--kohi-bg);
}

.card.night_mode,
.card.nightMode,
.night_mode .card,
.nightMode .card {
  --kohi-fg: #e9e9ec;
  --kohi-bg: #22252b;
  --kohi-term: #9fd0ff;
  --kohi-accent: #d0a76a;
  --kohi-muted: #9aa0aa;
  --kohi-panel: rgba(255, 255, 255, 0.07);
  --kohi-line: rgba(255, 255, 255, 0.20);
  --kohi-note: #93c9a1;
  --kohi-blank: #ff8aa8;
}

.term {
  font-size: 46px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--kohi-term);
  margin: 6px 0 14px;
  word-break: break-word;
}
.term.small { font-size: 34px; margin: 0 0 8px; }

.reading {
  font-size: 22px;
  color: var(--kohi-accent);
  margin: 4px 0 8px;
}

.romaji {
  font-size: 14px;
  font-style: italic;
  color: var(--kohi-muted);
  margin: 0 0 10px;
}

.meaning {
  font-size: 25px;
  font-weight: 600;
  margin: 10px 0;
}
.meaning.big { font-size: 30px; }

.example {
  font-size: 19px;
  text-align: left;
  background: var(--kohi-panel);
  border-left: 4px solid var(--kohi-accent);
  border-radius: 6px;
  padding: 10px 14px;
  margin: 12px 0;
}
.example.masked { font-size: 22px; line-height: 2.1; }

.translation {
  font-size: 17px;
  color: var(--kohi-muted);
  text-align: left;
  margin: 10px 0;
}

.note {
  font-size: 15px;
  color: var(--kohi-note);
  text-align: left;
  margin: 10px 0;
}

.level {
  display: inline-block;
  font-size: 13px;
  letter-spacing: 0.08em;
  color: var(--kohi-muted);
  border: 1px solid currentColor;
  border-radius: 10px;
  padding: 0 9px;
  margin-top: 8px;
}

.hint {
  font-size: 14px;
  letter-spacing: 0.04em;
  color: var(--kohi-muted);
  margin-top: 10px;
}

.chapter {
  font-size: 13px;
  letter-spacing: 0.06em;
  color: var(--kohi-muted);
  margin-top: 16px;
}

.blank {
  text-decoration: underline;
  text-decoration-thickness: 2px;
  text-underline-offset: 4px;
  font-weight: 700;
  color: var(--kohi-blank);
  padding: 0 4px;
}

.keyvocab {
  font-size: 15px;
  color: var(--kohi-note);
  text-align: left;
  margin: 10px 0;
}

hr#answer {
  border: none;
  border-top: 1px solid var(--kohi-line);
  width: 60%;
  margin: 18px auto;
}
"""

# --------------------------------------------------------------------------
# Шаблоны карточек
# --------------------------------------------------------------------------
CARD_TEMPLATES = [
    (
        TEMPLATE_CARD_1,
        # лицевая: Term крупно + пример, если он есть
        '<div class="term">{{Term}}</div>\n'
        '{{#Example}}<div class="example">{{Example}}</div>{{/Example}}\n',
        # обратная: Reading, Meaning, Translation, Note и Level — при наличии
        "{{FrontSide}}\n"
        '<hr id="answer">\n'
        '<div class="reading">{{Reading}}</div>\n'
        '{{#Romaji}}<div class="romaji">{{Romaji}}</div>{{/Romaji}}\n'
        '<div class="meaning">{{Meaning}}</div>\n'
        '{{#Translation}}<div class="translation">{{Translation}}</div>{{/Translation}}\n'
        '{{#Note}}<div class="note">{{Note}}</div>{{/Note}}\n'
        '{{#Level}}<div><span class="level">{{Level}}</span></div>{{/Level}}\n'
        '<div class="chapter">{{Chapter}}{{#Source}} · {{Source}}{{/Source}}</div>\n',
    ),
    (
        TEMPLATE_CARD_2,
        # лицевая: Meaning + подсказка Kind/Level
        '<div class="meaning big">{{Meaning}}</div>\n'
        '<div class="hint">{{Kind}}{{#Level}} · {{Level}}{{/Level}}</div>\n',
        # обратная: Term, Reading, Example, Translation
        "{{FrontSide}}\n"
        '<hr id="answer">\n'
        '<div class="term small">{{Term}}</div>\n'
        '<div class="reading">{{Reading}}</div>\n'
        '{{#Romaji}}<div class="romaji">{{Romaji}}</div>{{/Romaji}}\n'
        '{{#Example}}<div class="example">{{Example}}</div>{{/Example}}\n'
        '{{#Translation}}<div class="translation">{{Translation}}</div>{{/Translation}}\n',
    ),
    (
        TEMPLATE_CARD_3,
        # лицевая: ТОЛЬКО ExampleMasked, обёрнутый в условную секцию.
        # Если поле пустое, секция не рендерится, а Anki не создаёт карточку
        # (проверено: req = [2, 'any', [ExampleMasked]]).
        "{{#ExampleMasked}}"
        '<div class="example masked">{{ExampleMasked}}</div>'
        "{{/ExampleMasked}}\n",
        # обратная: Term, Reading, Meaning, полный Example, Translation
        "{{FrontSide}}\n"
        '<hr id="answer">\n'
        '<div class="term small">{{Term}}</div>\n'
        '<div class="reading">{{Reading}}</div>\n'
        '<div class="meaning">{{Meaning}}</div>\n'
        '{{#Example}}<div class="example">{{Example}}</div>{{/Example}}\n'
        '{{#Translation}}<div class="translation">{{Translation}}</div>{{/Translation}}\n',
    ),
]

PHRASE_TEMPLATES = [
    (
        TEMPLATE_PHRASE,
        # лицевая: японская фраза + глава/заголовок
        '<div class="example">{{Text}}</div>\n'
        '<div class="chapter">{{Chapter}}{{#Heading}} · {{Heading}}{{/Heading}}</div>\n',
        # обратная: перевод, ромадзи, ключевые слова
        "{{FrontSide}}\n"
        '<hr id="answer">\n'
        '{{#Translation}}<div class="translation">{{Translation}}</div>{{/Translation}}\n'
        '{{#Romaji}}<div class="romaji">{{Romaji}}</div>{{/Romaji}}\n'
        '{{#KeyVocab}}<div class="keyvocab"><b>Ключевые слова:</b> '
        "{{KeyVocab}}</div>{{/KeyVocab}}\n",
    ),
]


# --------------------------------------------------------------------------
# Утилиты
# --------------------------------------------------------------------------
def esc(text: str) -> str:
    """HTML-экранирование значения поля + перевод переводов строк в <br>."""
    if not text:
        return ""
    return (
        html.escape(str(text), quote=False).replace("\r\n", "\n").replace("\n", "<br>")
    )


_WS_RE = re.compile(r"\s+", re.UNICODE)
_KANA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u30FC]")
_JAPANESE_RE = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]")
_LEADING_TILDE_RE = re.compile(r"^[〜~]")
_PLUS_SEP_RE = re.compile(r"\s*\+\s*")


def is_kana(ch: str) -> bool:
    """Кана (хирагана/катакана/ー) — аналог isKana() из src/lib/dataset.ts."""
    return bool(ch) and _KANA_RE.search(ch) is not None


def is_japanese(text: str) -> bool:
    """Есть ли в строке хотя бы один японский символ — аналог isJapanese()."""
    return bool(text) and _JAPANESE_RE.search(text) is not None


def searchable(term: str) -> str:
    """Убирает приметы грамматического шаблона.

    1:1 с searchable() из src/lib/dataset.ts: убираем ведущие «〜»/«~», вставки
    « + » вместе с окружающими пробелами и вообще все пробельные символы.
    """
    result = _LEADING_TILDE_RE.sub("", term, count=1)
    result = _PLUS_SEP_RE.sub("", result)
    result = _WS_RE.sub("", result)
    return result


def kana_suffix_length(term: str) -> int:
    """Сколько кана-символов стоит в конце слова — аналог kanaSuffixLength()."""
    count = 0
    for i in range(len(term) - 1, -1, -1):
        if not is_kana(term[i]):
            break
        count += 1
    return count


def term_candidates(term: str) -> list:
    """Варианты написания слова: полная форма и основа без окуриганы (望む → 望).

    1:1 с termCandidates() из src/lib/dataset.ts. Порядок: сначала полная форма,
    затем всё более короткие основы; дубликаты убираются с сохранением порядка.
    """
    out = []
    for base in (term, searchable(term)):
        if not base:
            continue
        out.append(base)
        stem = base
        while len(stem) > 1 and is_kana(stem[-1]):
            stem = stem[:-1]
            if is_japanese(stem):
                out.append(stem)
    return list(dict.fromkeys(out))


def expand_to_word(sentence: str, start: int, end: int, term: str):
    """Расширяет найденный фрагмент до целой словоформы (望 → 望んだ, 見 → 見上げて).

    1:1 с expandToWord() из src/lib/dataset.ts:
      * вправо — иероглифы, входящие в term, либо кана, но не более kanaLimit
        кана-символов, где kanaLimit = (конечных кана term > 0) ? конечных кана
        term + 1 : 0. То есть кану справа добираем ТОЛЬКО у слов с окуриганой;
        у слов, кончающихся иероглифом (努力, 先客, 都市伝説), — ничего, иначе
        в пропуск попадала частица («努力を» вместо «努力»);
      * влево — ТОЛЬКО иероглифы, входящие в term. Кану слева не захватываем
        вообще: иначе в пропуск попадали окончания соседних слов
        («…間だけ望んだ…» давало уродливое «け望んだ»).
    """
    base = searchable(term)
    in_term = set(base)
    suffix = kana_suffix_length(base)
    kana_limit = suffix + 1 if suffix > 0 else 0
    left = start
    right = end
    taken = 0
    while right < len(sentence):
        ch = sentence[right]
        if ch in in_term and not is_kana(ch):
            right += 1
            continue
        if is_kana(ch) and taken < kana_limit:
            right += 1
            taken += 1
            continue
        break
    while (
        left > 0 and not is_kana(sentence[left - 1]) and sentence[left - 1] in in_term
    ):
        left -= 1
    return left, right


def find_term(haystack: str, term: str):
    """Первое вхождение слова в любой словоформе; возвращает (start, end) или None.

    1:1 с findTerm() из src/lib/dataset.ts: обычный indexOf по кандидатам
    в порядке убывания полноты формы. Фрагмент короче 2 символов отбраковывается,
    причём следующие кандидаты уже НЕ перебираются — как в оригинале.
    """
    if not haystack or not term:
        return None
    for candidate in term_candidates(term):
        index = haystack.find(candidate)
        if index >= 0:
            span = expand_to_word(haystack, index, index + len(candidate), term)
            return span if span[1] - span[0] >= 2 else None
    return None


def make_example_masked(example_raw: str, term: str) -> str:
    """ExampleMasked: целевое слово (в любой словоформе) заменяем на «［　］».

    Алгоритм 1:1 повторяет maskTerm()/findTerm() из src/lib/dataset.ts, чтобы
    колода и веб-приложение давали одинаковый результат. Если слово не найдено —
    пустая строка (тогда карточка «03 Контекст» не создаётся).
    """
    if not example_raw:
        return ""
    found = find_term(example_raw, term)
    if not found:
        return ""
    start, end = found
    return (
        esc(example_raw[:start])
        + '<span class="blank">［　］</span>'
        + esc(example_raw[end:])
    )


def make_guid(kind: str, key: str) -> str:
    """Детерминированный GUID заметки (sha1, 16 hex-символов)."""
    return hashlib.sha1(("%s::%s" % (kind, key)).encode("utf-8")).hexdigest()[:16]


def sanitize_tag(tag: str) -> str:
    tag = (tag or "").strip().replace(" ", "_")
    return tag


def remove_collection_files(path: str) -> None:
    """Удаляем файлы и каталоги, которые Anki создаёт рядом с коллекцией.

    Именно так (а не одним os.remove) — потому что рядом с файлом коллекции
    Anki держит каталог '<имя>.media' и файл '<имя>.media.db2'.
    """
    base, _ = os.path.splitext(path)
    targets = [
        path,
        path + "-wal",
        path + "-shm",
        path + "-journal",
        base + ".media",
        base + ".media.db2",
    ]
    for candidate in targets:
        if not os.path.exists(candidate):
            continue
        try:
            if os.path.isdir(candidate):
                shutil.rmtree(candidate, ignore_errors=True)
            else:
                os.remove(candidate)
        except PermissionError:
            os.chmod(candidate, stat.S_IWRITE | stat.S_IREAD)
            os.remove(candidate)


def load_novel(path: str = DATA_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def data_fingerprint(path: str = DATA_PATH) -> dict:
    """sha1/размер/mtime входных данных — чтобы в отчёте было видно, ЧТО собрано."""
    with open(path, "rb") as fh:
        blob = fh.read()
    st = os.stat(path)
    return {
        "sha1": hashlib.sha1(blob).hexdigest(),
        "size": st.st_size,
        "mtime": datetime.datetime.fromtimestamp(st.st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }


def chapter_label(chapter: dict) -> str:
    return "%02d %s" % (int(chapter.get("number", 0)), chapter.get("titleJp", ""))


class Novel:
    """Разобранные входные данные."""

    def __init__(self, data: dict):
        self.data = data
        self.meta = data.get("meta", {})
        self.root_deck_name = self.meta.get("title") or "Kohi"
        self.chapters = {c["id"]: c for c in data.get("chapters", [])}
        self.chapter_order = [c["id"] for c in data.get("chapters", [])]
        self.fragments = {f["id"]: f for f in data.get("fragments", [])}
        self.items = {i["id"]: i for i in data.get("items", [])}
        self.items_list = list(data.get("items", []))
        self.fragments_list = list(data.get("fragments", []))

    def chapter_of_item(self, item: dict) -> str:
        return item.get("chapterId") or ""

    def deck_leaf_for_item(self, item: dict) -> str:
        return KIND_TO_DECK.get(item.get("kind", ""), DECK_VOCAB)


# --------------------------------------------------------------------------
# Работа с коллекцией
# --------------------------------------------------------------------------
def schema_fingerprint() -> str:
    payload = {
        "card_nt": CARD_NT,
        "card_fields": CARD_FIELDS,
        "card_templates": [[n, q, a] for n, q, a in CARD_TEMPLATES],
        "phrase_nt": PHRASE_NT,
        "phrase_fields": PHRASE_FIELDS,
        "phrase_templates": [[n, q, a] for n, q, a in PHRASE_TEMPLATES],
        "css": SHARED_CSS,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def open_work_collection() -> tuple[Collection, bool]:
    """Открывает рабочую коллекцию, при необходимости пересоздаёт её.

    Возвращает (коллекция, была_ли_пересоздана).
    """
    os.makedirs(WORK_DIR, exist_ok=True)
    fingerprint = schema_fingerprint()
    recreated = False
    if os.path.exists(WORK_COL):
        probe = Collection(WORK_COL)
        try:
            old = probe.get_config(SCHEMA_CONFIG_KEY, "")
        finally:
            probe.close()
        if old != fingerprint:
            remove_collection_files(WORK_COL)
            recreated = True
    else:
        recreated = True
    col = Collection(WORK_COL)
    return col, recreated


def ensure_notetype(
    col: Collection, name: str, fields: list, templates: list, css: str
):
    """Создаёт тип заметки, если его нет; иначе обновляет шаблоны и CSS."""
    nt = col.models.by_name(name)
    if nt is None:
        nt = col.models.new(name)
        if nt["name"] != name:
            # ensure_name_unique мог переименовать — значит имя занято
            raise RuntimeError("Не удалось создать тип заметки %r" % name)
        nt["flds"] = []
        for fname in fields:
            nt["flds"].append(col.models.new_field(fname))
        nt["tmpls"] = []
        for tname, qfmt, afmt in templates:
            tmpl = col.models.new_template(tname)
            tmpl["qfmt"] = qfmt
            tmpl["afmt"] = afmt
            nt["tmpls"].append(tmpl)
        nt["css"] = css
        nt["sortf"] = 0
        out = col.models.add_dict(nt)
        return col.models.get(out.id)

    # --- существующий тип заметки: приводим к спецификации -----------------
    current_fields = [f["name"] for f in nt["flds"]]
    if current_fields != fields:
        raise RuntimeError(
            "Тип заметки %r существует, но набор полей отличается:\n"
            "  в коллекции: %s\n  ожидается:   %s\n"
            "Удалите файл %s и запустите сборку заново (тип заметки будет создан заново)."
            % (name, current_fields, fields, WORK_COL)
        )
    changed = nt["css"] != css
    by_name = {t["name"]: t for t in nt["tmpls"]}
    for tname, qfmt, afmt in templates:
        tmpl = by_name.get(tname)
        if tmpl is None:
            tmpl = col.models.new_template(tname)
            tmpl["qfmt"] = qfmt
            tmpl["afmt"] = afmt
            col.models.add_template(nt, tmpl)
            changed = True
        elif tmpl["qfmt"] != qfmt or tmpl["afmt"] != afmt:
            tmpl["qfmt"] = qfmt
            tmpl["afmt"] = afmt
            changed = True
    nt["css"] = css
    if changed:
        col.models.update_dict(nt)
        nt = col.models.get(nt["id"])
    return nt


def ensure_decks(col: Collection, novel: Novel) -> dict:
    """Создаёт иерархию колод. Возвращает словарь {ключ: deck_id}."""
    decks = {}
    root_name = novel.root_deck_name
    decks["root"] = col.decks.id(root_name)
    for cid in novel.chapter_order:
        chapter = novel.chapters[cid]
        label = chapter_label(chapter)
        chapter_name = "%s::%s" % (root_name, label)
        decks[("chapter", cid)] = col.decks.id(chapter_name)
        for leaf in (DECK_VOCAB, DECK_GRAMMAR, DECK_PHRASES):
            decks[("leaf", cid, leaf)] = col.decks.id("%s::%s" % (chapter_name, leaf))
    return decks


def build_notes(novel: Novel, decks: dict):
    """Формирует список описаний заметок (без записи в коллекцию)."""
    specs = []

    # --- заметки-элементы -------------------------------------------------
    for item in novel.items_list:
        cid = novel.chapter_of_item(item)
        chapter = novel.chapters.get(cid, {})
        label = chapter_label(chapter) if chapter else cid

        examples = item.get("examples") or []
        first = examples[0] if examples else {}
        example_raw = (first.get("jp") or "").strip()
        translation_raw = (first.get("ru") or "").strip()
        term_raw = (item.get("term") or "").strip()

        tags = [TAG_ROOT]
        if cid:
            tags.append(sanitize_tag(cid))
        level = sanitize_tag(item.get("level", ""))
        if level:
            tags.append(level)
        kind = sanitize_tag(item.get("kind", ""))
        if kind:
            tags.append(kind)
        if (item.get("readingRomaji") or "").strip() and item.get("source") == "guide":
            tags.append(TAG_AUTO_READING)

        fields = {
            "Term": esc(term_raw),
            "Reading": esc(item.get("readingKana", "")),
            "Meaning": esc(item.get("meaning", "")),
            "Example": esc(example_raw),
            "ExampleMasked": make_example_masked(example_raw, term_raw),
            "Translation": esc(translation_raw),
            "Romaji": esc(item.get("readingRomaji", "")),
            "Chapter": esc(label),
            "Level": esc(item.get("level", "")),
            "Kind": esc(item.get("kind", "")),
            "Note": esc(item.get("note", "")),
            "Source": esc(item.get("source", "")),
        }
        specs.append(
            {
                "guid": make_guid("item", item["id"]),
                "notetype": CARD_NT,
                "fields": fields,
                "tags": tags,
                "deck_id": decks[("leaf", cid, novel.deck_leaf_for_item(item))],
                "origin": item["id"],
                "kind": "item",
                "has_mask": bool(fields["ExampleMasked"]),
            }
        )

    # --- заметки-фразы ----------------------------------------------------
    for fragment in novel.fragments_list:
        cid = fragment.get("chapterId", "")
        chapter = novel.chapters.get(cid, {})
        label = chapter_label(chapter) if chapter else cid

        key_vocab_parts = []
        for key in fragment.get("itemKeys", []):
            item = novel.items.get(key)
            if item is None:
                continue
            term = (item.get("term") or key).strip()
            kana = (item.get("readingKana") or "").strip()
            key_vocab_parts.append("%s — %s" % (term, kana) if kana else term)

        tags = [TAG_ROOT]
        if cid:
            tags.append(sanitize_tag(cid))
        tags.append("phrase")

        fields = {
            "Text": esc(fragment.get("original", "")),
            "Romaji": esc(fragment.get("romaji", "")),
            "Translation": esc(fragment.get("translation", "")),
            "Chapter": esc(label),
            "Heading": esc(fragment.get("heading", "")),
            "KeyVocab": esc(", ".join(key_vocab_parts)),
        }
        specs.append(
            {
                "guid": make_guid("phrase", fragment["id"]),
                "notetype": PHRASE_NT,
                "fields": fields,
                "tags": tags,
                "deck_id": decks[("leaf", cid, DECK_PHRASES)],
                "origin": fragment["id"],
                "kind": "phrase",
                "has_mask": False,
            }
        )

    return specs


def collect_stats(col: Collection, novel: Novel) -> dict:
    """Собирает фактические числа из коллекции."""
    nts = {nt["name"]: nt for nt in col.models.all()}
    card_nt = nts[CARD_NT]
    phrase_nt = nts[PHRASE_NT]

    deck_names = {d["id"]: d["name"] for d in col.decks.all()}

    stats = {
        "notes_by_type": {CARD_NT: 0, PHRASE_NT: 0},
        "cards_by_ord": {"card": {}, "phrase": {}},
        "cards_total": 0,
        "notes_total": 0,
        "leaves": {},  # имя колоды -> {"notes": n, "cards": n}
        "notetype_ids": {CARD_NT: card_nt["id"], PHRASE_NT: phrase_nt["id"]},
        "notetype_fields": {
            CARD_NT: [f["name"] for f in card_nt["flds"]],
            PHRASE_NT: [f["name"] for f in phrase_nt["flds"]],
        },
        "notetype_templates": {
            CARD_NT: [t["name"] for t in card_nt["tmpls"]],
            PHRASE_NT: [t["name"] for t in phrase_nt["tmpls"]],
        },
        "empty_examplemasked_items": 0,
        "masked_items": 0,
        "notetype_req": {},
        "deck_ids": {},
    }
    for name in (CARD_NT, PHRASE_NT):
        stats["notetype_req"][name] = json.dumps(nts[name]["req"], ensure_ascii=False)

    # инициализируем все листовые колоды
    for cid in novel.chapter_order:
        chapter = novel.chapters[cid]
        base = "%s::%s" % (novel.root_deck_name, chapter_label(chapter))
        for leaf in (DECK_VOCAB, DECK_GRAMMAR, DECK_PHRASES):
            full = "%s::%s" % (base, leaf)
            stats["leaves"][full] = {"notes": 0, "cards": 0}

    note_deck_cards = {}
    for nid in col.find_notes(""):
        note = col.get_note(nid)
        stats["notes_total"] += 1
        is_card_nt = note.mid == card_nt["id"]
        name = CARD_NT if is_card_nt else PHRASE_NT
        stats["notes_by_type"][name] += 1
        if is_card_nt:
            if note["ExampleMasked"].strip():
                stats["masked_items"] += 1
            else:
                stats["empty_examplemasked_items"] += 1
        bucket = "card" if is_card_nt else "phrase"
        for cid_card in note.card_ids():
            card = col.get_card(cid_card)
            key = "ord%d" % card.ord
            stats["cards_by_ord"][bucket][key] = (
                stats["cards_by_ord"][bucket].get(key, 0) + 1
            )
            stats["cards_total"] += 1
            dname = deck_names.get(card.did, "?")
            leaf_stat = stats["leaves"].get(dname)
            if leaf_stat is not None:
                leaf_stat["cards"] += 1
                note_deck_cards.setdefault(dname, set()).add(nid)

    for dname, nids in note_deck_cards.items():
        stats["leaves"][dname]["notes"] = len(nids)

    for cid in novel.chapter_order:
        chapter = novel.chapters[cid]
        base = "%s::%s" % (novel.root_deck_name, chapter_label(chapter))
        stats["deck_ids"][base] = col.decks.id(base, create=False)
        for leaf in (DECK_VOCAB, DECK_GRAMMAR, DECK_PHRASES):
            full = "%s::%s" % (base, leaf)
            stats["deck_ids"][full] = col.decks.id(full, create=False)
    stats["deck_ids"][novel.root_deck_name] = col.decks.id(
        novel.root_deck_name, create=False
    )
    return stats


# --------------------------------------------------------------------------
# Сборка
# --------------------------------------------------------------------------
def build(verbose: bool = True) -> dict:
    novel = Novel(load_novel())
    os.makedirs(OUT_DIR, exist_ok=True)

    col, recreated = open_work_collection()
    try:
        if verbose:
            print(
                "Рабочая коллекция: %s%s"
                % (WORK_COL, " (пересоздана)" if recreated else "")
            )

        ensure_notetype(col, CARD_NT, CARD_FIELDS, CARD_TEMPLATES, SHARED_CSS)
        ensure_notetype(col, PHRASE_NT, PHRASE_FIELDS, PHRASE_TEMPLATES, SHARED_CSS)

        decks = ensure_decks(col, novel)

        # Полная пересборка заметок: guid детерминированы, поэтому для
        # пользователя повторный импорт остаётся идемпотентным.
        stale = list(col.find_notes(""))
        if stale:
            col.remove_notes(stale)

        specs = build_notes(novel, decks)
        nt_cache = {nt["name"]: nt for nt in col.models.all()}
        for spec in specs:
            note = col.new_note(nt_cache[spec["notetype"]])
            note.guid = spec["guid"]
            for fname, value in spec["fields"].items():
                note[fname] = value
            note.tags = list(spec["tags"])
            col.add_note(note, spec["deck_id"])

        col.set_config(SCHEMA_CONFIG_KEY, schema_fingerprint())

        # --- экспорт ------------------------------------------------------
        if os.path.exists(APKG_PATH):
            os.remove(APKG_PATH)
        options = ie_pb.ExportAnkiPackageOptions(
            with_scheduling=True,
            with_deck_configs=True,
            with_media=True,
            legacy=False,
        )
        limit = ie_pb.ExportLimit(deck_id=decks["root"])
        exported = col.export_anki_package(
            out_path=APKG_PATH, options=options, limit=limit
        )

        stats = collect_stats(col, novel)
        stats["exported_notes_reported_by_api"] = exported
        stats["apkg_path"] = APKG_PATH
        stats["apkg_size"] = os.path.getsize(APKG_PATH)
        stats["data_path"] = DATA_PATH
        stats["data_fingerprint"] = data_fingerprint()
        stats["work_collection"] = WORK_COL
        stats["work_collection_recreated"] = recreated
        stats["root_deck"] = novel.root_deck_name
        stats["expected_items"] = len(novel.items_list)
        stats["expected_fragments"] = len(novel.fragments_list)
        stats["expected_chapters"] = len(novel.chapter_order)
        return stats
    finally:
        col.close()


# --------------------------------------------------------------------------
# Отчёт
# --------------------------------------------------------------------------
def render_build_report(stats: dict) -> str:
    lines = []
    add = lines.append
    add("=" * 78)
    add("КОЛОДА ANKI «%s» — ОТЧЁТ О СБОРКЕ" % stats["root_deck"])
    add("=" * 78)
    add(
        "Дата сборки       : %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    add("Входные данные    : %s" % stats["data_path"])
    fp = stats.get("data_fingerprint") or {}
    add("  sha1 / размер   : %s / %s байт" % (fp.get("sha1", "?"), fp.get("size", "?")))
    add("  изменён         : %s" % fp.get("mtime", "?"))
    add("Файл колоды       : %s" % stats["apkg_path"])
    add("Размер файла      : %s байт" % stats["apkg_size"])
    add(
        "Рабочая коллекция : %s%s"
        % (
            stats["work_collection"],
            " (пересоздана)" if stats["work_collection_recreated"] else "",
        )
    )
    add(
        "Реальная коллекция пользователя не затрагивалась (%APPDATA%\\Anki2 не открывалась)."
    )
    add("")
    add("-" * 78)
    add("ТИПЫ ЗАМЕТОК")
    add("-" * 78)
    for name in (CARD_NT, PHRASE_NT):
        add("%s (id=%s)" % (name, stats["notetype_ids"][name]))
        add("    поля      : %s" % ", ".join(stats["notetype_fields"][name]))
        add("    шаблоны   : %s" % ", ".join(stats["notetype_templates"][name]))
        add("    req       : %s" % stats["notetype_req"][name])
    add("")
    add("-" * 78)
    add("ЗАМЕТКИ И КАРТОЧКИ ПО КОЛОДАМ")
    add("-" * 78)
    add("%-52s %8s %8s" % ("Колода", "заметок", "карточек"))
    add("-" * 78)
    total_notes = 0
    total_cards = 0
    for dname in sorted(stats["leaves"]):
        st = stats["leaves"][dname]
        total_notes += st["notes"]
        total_cards += st["cards"]
        add("%-52s %8d %8d" % (dname, st["notes"], st["cards"]))
    add("-" * 78)
    add("%-52s %8d %8d" % ("ИТОГО по листовым колодам", total_notes, total_cards))
    add("")
    add("Заметок всего                     : %d" % stats["notes_total"])
    for name in (CARD_NT, PHRASE_NT):
        add("    %-29s : %d" % (name, stats["notes_by_type"][name]))
    add("Карточек всего                    : %d" % stats["cards_total"])
    add("Глав всего                        : %d" % stats["expected_chapters"])
    add("")
    add("-" * 78)
    add("РАСПРЕДЕЛЕНИЕ КАРТОЧЕК ПО ШАБЛОНАМ")
    add("-" * 78)
    card_ords = stats["cards_by_ord"]["card"]
    phrase_ords = stats["cards_by_ord"]["phrase"]
    add("  «%s»:" % CARD_NT)
    add("    %-24s : %d" % (TEMPLATE_CARD_1, card_ords.get("ord0", 0)))
    add("    %-24s : %d" % (TEMPLATE_CARD_2, card_ords.get("ord1", 0)))
    add("    %-24s : %d" % (TEMPLATE_CARD_3, card_ords.get("ord2", 0)))
    add("  «%s»:" % PHRASE_NT)
    add("    %-24s : %d" % (TEMPLATE_PHRASE, phrase_ords.get("ord0", 0)))
    for extra, value in sorted(phrase_ords.items()):
        if extra != "ord0":
            add("    %-24s : %d" % (extra, value))
    add("")
    add("Элементов с непустым ExampleMasked : %d" % stats["masked_items"])
    add("Элементов с пустым ExampleMasked   : %d" % stats["empty_examplemasked_items"])
    add("Ожидалось элементов                : %d" % stats["expected_items"])
    add("Ожидалось фраз                     : %d" % stats["expected_fragments"])
    add("")
    expected_cards = (
        stats["notes_by_type"][CARD_NT] * 2
        + stats["masked_items"]
        + stats["notes_by_type"][PHRASE_NT]
    )
    add("Ожидаемое число карточек:")
    add(
        "    Kohi Novel Card: элементы(%d) x шаблоны 01 и 02 + шаблон 03 при маске = %d"
        % (
            stats["notes_by_type"][CARD_NT],
            stats["notes_by_type"][CARD_NT] * 2 + stats["masked_items"],
        )
    )
    add("    Kohi Novel Phrase: %d" % stats["notes_by_type"][PHRASE_NT])
    add(
        "    ВСЕГО ожидается: %d, фактически: %d%s"
        % (
            expected_cards,
            stats["cards_total"],
            "" if expected_cards == stats["cards_total"] else "  <-- РАСХОЖДЕНИЕ!",
        )
    )
    add("")
    return "\n".join(lines)


def write_report(text: str, path: str = REPORT_PATH) -> None:
    # CRLF + UTF-8: отчёт должен нормально открываться и в «Блокноте», и в VS Code
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(text)


def main(argv=None) -> int:
    stats = build(verbose=True)
    report = render_build_report(stats)
    write_report(report)

    print("")
    print("Готово.")
    print("Файл колоды : %s" % stats["apkg_path"])
    print("Размер      : %s байт" % stats["apkg_size"])
    print(
        "Заметок     : %d (элементы %d + фразы %d)"
        % (
            stats["notes_total"],
            stats["notes_by_type"][CARD_NT],
            stats["notes_by_type"][PHRASE_NT],
        )
    )
    print("Карточек    : %d" % stats["cards_total"])
    print("Отчёт       : %s" % REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
