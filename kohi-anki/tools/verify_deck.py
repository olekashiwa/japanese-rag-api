#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_deck.py — проверка собранной колоды Anki.

Запуск из корня проекта kohi-anki интерпретатором Anki:

    "C:\\Users\\<user>\\AppData\\Local\\AnkiProgramFiles\\.venv\\Scripts\\python.exe"
    tools\\verify_deck.py

Что делает:
  1. пересобирает колоду (build_deck.build) — чтобы отчёт отвечал текущим данным;
  2. создаёт ВРЕМЕННУЮ коллекцию в tools/_ankitest/verify/ и импортирует туда
     .apkg через Collection.import_anki_package(...);
  3. проверяет типы заметок, порядок полей, шаблоны, колоды, числа заметок и
     карточек, отсутствие пустых Term/Text, наличие/отсутствие карточки
     «03 Контекст» в зависимости от ExampleMasked, детерминированность GUID,
     идемпотентность повторного импорта;
  4. рендерит несколько карточек в HTML и складывает их в отчёт;
  5. пишет tools/report_deck.txt и возвращает 0 (проверка пройдена) или 1.

Реальная коллекция пользователя (%APPDATA%\\Anki2) не открывается и не изменяется —
это дополнительно контролируется снимком файлов до и после работы.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

try:
    import anki.collection  # noqa: F401  (первым: в пакете anki циклические импорты)
    from anki.collection import Collection
    import anki.import_export_pb2 as ie_pb
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        f"ОШИБКА: не удалось импортировать пакет 'anki' ({exc}).\n"
        "Запустите скрипт интерпретатором Python из Anki:\n"
        '  "%LOCALAPPDATA%\\AnkiProgramFiles\\.venv\\Scripts\\python.exe" tools\\verify_deck.py\n'
    )
    raise SystemExit(2)

import build_deck as bd  # noqa: E402

ROOT = bd.ROOT
VERIFY_DIR = os.path.join(ROOT, "tools", "_ankitest", "verify")
VERIFY_COL_1 = os.path.join(VERIFY_DIR, "verify_col_1.anki2")
VERIFY_COL_2 = os.path.join(VERIFY_DIR, "verify_col_2.anki2")
RUN1_APKG = os.path.join(VERIFY_DIR, "run1.apkg")
RUN2_APKG = os.path.join(VERIFY_DIR, "run2.apkg")
REPORT_PATH = bd.REPORT_PATH

STYLE_RE = re.compile(r"<style.*?</style>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


# --------------------------------------------------------------------------
# Вспомогательное
# --------------------------------------------------------------------------
def visible_text(markup: str) -> str:
    text = STYLE_RE.sub("", markup or "")
    text = text.replace("&nbsp;", " ").replace("&#160;", " ")
    text = TAG_RE.sub("", text)
    return text.strip()


class Checker:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, bool(ok), detail))
        return bool(ok)

    @property
    def failed(self) -> list[tuple[str, bool, str]]:
        return [r for r in self.results if not r[1]]

    def render(self) -> str:
        lines = []
        for name, ok, detail in self.results:
            lines.append("  [%s] %s" % ("OK " if ok else "ОШИБКА", name))
            if detail:
                for chunk in str(detail).splitlines():
                    if chunk.strip():
                        lines.append("          %s" % chunk)
        return "\n".join(lines)


def snapshot_real_collection() -> dict:
    """Снимок файлов реальной коллекции Anki (только чтение метаданных)."""
    appdata = os.environ.get("APPDATA", "")
    base = os.path.join(appdata, "Anki2") if appdata else ""
    snap = {"base": base, "exists": bool(base) and os.path.isdir(base), "files": {}}
    if not snap["exists"]:
        return snap
    candidates = [os.path.join(base, "prefs21.db")]
    try:
        for entry in sorted(os.listdir(base)):
            candidates.append(os.path.join(base, entry, "collection.anki2"))
    except OSError:
        pass
    for path in candidates:
        try:
            st = os.stat(path)
            snap["files"][path] = (st.st_size, int(st.st_mtime))
        except OSError:
            snap["files"][path] = None
    return snap


def open_fresh_collection(path: str) -> Collection:
    """Создаёт пустую временную коллекцию внутри проекта."""
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(ROOT) + os.sep):
        raise RuntimeError(
            "Отказ: временная коллекция вне каталога проекта: %s" % real
        )
    bd.remove_collection_files(path)
    return Collection(path)


def import_package(col: Collection, apkg: str):
    request = ie_pb.ImportAnkiPackageRequest(package_path=apkg)
    return col.import_anki_package(request)


def deck_cards_map(col: Collection) -> dict:
    """{имя колоды: {"notes": set, "cards": n, "by_ord": {...}}}"""
    names = {d["id"]: d["name"] for d in col.decks.all()}
    out: dict = {}
    for nid in col.find_notes(""):
        note = col.get_note(nid)
        for cid in note.card_ids():
            card = col.get_card(cid)
            dname = names.get(card.did, "?")
            entry = out.setdefault(dname, {"notes": set(), "cards": 0, "by_ord": {}})
            entry["notes"].add(nid)
            entry["cards"] += 1
            entry["by_ord"]["ord%d" % card.ord] = (
                entry["by_ord"].get("ord%d" % card.ord, 0) + 1
            )
    return out


def expected_deck_layout(novel: bd.Novel) -> dict:
    """Независимый расчёт ожидаемых заметок/карточек по листовым колодам."""
    layout: dict = {}
    for cid in novel.chapter_order:
        chapter = novel.chapters[cid]
        base = "%s::%s" % (novel.root_deck_name, bd.chapter_label(chapter))
        for leaf in (bd.DECK_VOCAB, bd.DECK_GRAMMAR, bd.DECK_PHRASES):
            layout["%s::%s" % (base, leaf)] = {"notes": 0, "cards": 0}
    for item in novel.items_list:
        base = "%s::%s" % (
            novel.root_deck_name,
            bd.chapter_label(novel.chapters[item["chapterId"]]),
        )
        leaf = bd.KIND_TO_DECK.get(item.get("kind", ""), bd.DECK_VOCAB)
        key = "%s::%s" % (base, leaf)
        examples = item.get("examples") or []
        example = (examples[0].get("jp") or "").strip() if examples else ""
        masked = bool(bd.make_example_masked(example, (item.get("term") or "").strip()))
        layout[key]["notes"] += 1
        layout[key]["cards"] += 3 if masked else 2
    for fragment in novel.fragments_list:
        base = "%s::%s" % (
            novel.root_deck_name,
            bd.chapter_label(novel.chapters[fragment["chapterId"]]),
        )
        key = "%s::%s" % (base, bd.DECK_PHRASES)
        layout[key]["notes"] += 1
        layout[key]["cards"] += 1
    return layout


# --------------------------------------------------------------------------
# Основная проверка
# --------------------------------------------------------------------------
def run_verification() -> int:
    os.makedirs(VERIFY_DIR, exist_ok=True)
    real_before = snapshot_real_collection()

    print("1/6 Пересборка колоды из src/data/novel.json ...")
    stats = bd.build(verbose=False)
    apkg = stats["apkg_path"]
    print("    готово: %s (%d байт)" % (apkg, stats["apkg_size"]))

    # Копия сборки №1 — понадобится для проверки повторяемости сборки.
    shutil.copy2(apkg, RUN1_APKG)

    novel = bd.Novel(bd.load_novel())
    layout_expected = expected_deck_layout(novel)

    ck = Checker()
    rendered: list[tuple[str, str, str]] = []

    print("2/6 Импорт .apkg во временную коллекцию №1 ...")
    col1 = open_fresh_collection(VERIFY_COL_1)
    try:
        import_package(col1, apkg)  # ImportLog не используется, важен сам импорт
        notes_after_first = len(col1.find_notes(""))
        cards_after_first = len(col1.find_cards(""))

        # ---------------- типы заметок ------------------------------------
        nt_card = col1.models.by_name(bd.CARD_NT)
        nt_phrase = col1.models.by_name(bd.PHRASE_NT)
        ck.check(
            "Тип заметки «%s» создан" % bd.CARD_NT,
            nt_card is not None,
        )
        ck.check(
            "Тип заметки «%s» создан" % bd.PHRASE_NT,
            nt_phrase is not None,
        )
        if nt_card is None or nt_phrase is None:
            raise SystemExit("Нет типов заметок — дальнейшие проверки невозможны")

        ck.check(
            "«%s»: порядок полей" % bd.CARD_NT,
            [f["name"] for f in nt_card["flds"]] == bd.CARD_FIELDS,
            "фактически: %s" % [f["name"] for f in nt_card["flds"]],
        )
        ck.check(
            "«%s»: порядок полей" % bd.PHRASE_NT,
            [f["name"] for f in nt_phrase["flds"]] == bd.PHRASE_FIELDS,
            "фактически: %s" % [f["name"] for f in nt_phrase["flds"]],
        )
        ck.check(
            "«%s»: 3 шаблона с нужными именами" % bd.CARD_NT,
            [t["name"] for t in nt_card["tmpls"]]
            == [bd.TEMPLATE_CARD_1, bd.TEMPLATE_CARD_2, bd.TEMPLATE_CARD_3],
            "фактически: %s" % [t["name"] for t in nt_card["tmpls"]],
        )
        ck.check(
            "«%s»: шаблон «%s»" % (bd.PHRASE_NT, bd.TEMPLATE_PHRASE),
            [t["name"] for t in nt_phrase["tmpls"]] == [bd.TEMPLATE_PHRASE],
            "фактически: %s" % [t["name"] for t in nt_phrase["tmpls"]],
        )
        ck.check(
            "Оба типа заметок обычные (не cloze)",
            nt_card["type"] == 0 and nt_phrase["type"] == 0,
        )
        ck.check(
            "CSS карточек записан в оба типа заметок без искажений",
            nt_card["css"] == bd.SHARED_CSS and nt_phrase["css"] == bd.SHARED_CSS,
        )
        ck.check(
            "«03 Контекст» условно зависит только от ExampleMasked",
            nt_card["req"][2][2] == [bd.CARD_FIELDS.index("ExampleMasked")]
            if len(nt_card["req"]) > 2
            else False,
            "req = %s" % json.dumps(nt_card["req"], ensure_ascii=False),
        )

        # ---------------- колоды ------------------------------------------
        deck_names = {d["name"] for d in col1.decks.all()}
        missing = []
        for cid in novel.chapter_order:
            chapter = novel.chapters[cid]
            base = "%s::%s" % (novel.root_deck_name, bd.chapter_label(chapter))
            for name in (novel.root_deck_name, base):
                if name not in deck_names:
                    missing.append(name)
        for name in layout_expected:
            if name not in deck_names:
                missing.append(name)
        ck.check(
            "Все ожидаемые колоды существуют (%d листовых + 5 глав + корень)"
            % len(layout_expected),
            not missing,
            "отсутствуют: %s" % missing if missing else "",
        )
        unexpected_leaves = [
            n
            for n in deck_names
            if n.startswith(novel.root_deck_name + "::")
            and n not in layout_expected
            and n.count("::") > 1
        ]
        ck.check(
            "Лишних подколод нет",
            not unexpected_leaves,
            "лишние: %s" % unexpected_leaves if unexpected_leaves else "",
        )

        # ---------------- числа заметок -----------------------------------
        n_card_notes = len(col1.models.nids(nt_card["id"]))
        n_phrase_notes = len(col1.models.nids(nt_phrase["id"]))
        ck.check(
            "Заметок «%s» = %d" % (bd.CARD_NT, len(novel.items_list)),
            n_card_notes == len(novel.items_list),
            "фактически: %d" % n_card_notes,
        )
        ck.check(
            "Заметок «%s» = %d" % (bd.PHRASE_NT, len(novel.fragments_list)),
            n_phrase_notes == len(novel.fragments_list),
            "фактически: %d" % n_phrase_notes,
        )
        ck.check(
            "Всего заметок = %d" % stats["notes_total"],
            notes_after_first == stats["notes_total"],
            "фактически: %d" % notes_after_first,
        )
        ck.check(
            "Всего карточек = %d" % stats["cards_total"],
            cards_after_first == stats["cards_total"],
            "фактически: %d" % cards_after_first,
        )

        # ---------------- заметки/карточки по колодам ---------------------
        actual_decks = deck_cards_map(col1)
        deck_problems = []
        for dname, exp in sorted(layout_expected.items()):
            got = actual_decks.get(dname, {"notes": set(), "cards": 0})
            got_notes = len(got["notes"])
            if got_notes != exp["notes"] or got["cards"] != exp["cards"]:
                deck_problems.append(
                    "%s: заметок %d (ожидалось %d), карточек %d (ожидалось %d)"
                    % (dname, got_notes, exp["notes"], got["cards"], exp["cards"])
                )
        ck.check(
            "Заметки и карточки по каждой подколоде совпадают с ожидаемыми",
            not deck_problems,
            "\n".join(deck_problems),
        )

        # ---------------- пустые Term/Text, содержимое карточек -----------
        empty_term = []
        empty_text = []
        masked_ok = True
        masked_problems = []
        empty_questions = []
        guid_problems = []
        tag_problems = []

        expected_guids = set()
        for spec in bd.build_notes(novel, _DummyDecks()):
            expected_guids.add(spec["guid"])
        actual_guids = set()

        for nid in col1.find_notes(""):
            note = col1.get_note(nid)
            actual_guids.add(note.guid)
            is_card_nt = note.mid == nt_card["id"]
            if is_card_nt:
                term = note["Term"].strip()
                if not term:
                    empty_term.append(nid)
                has_mask = bool(note["ExampleMasked"].strip())
                ords = sorted(col1.get_card(c).ord for c in note.card_ids())
                if has_mask:
                    if ords != [0, 1, 2]:
                        masked_ok = False
                        masked_problems.append(
                            "%s: ExampleMasked непустой, но карточки %s" % (term, ords)
                        )
                else:
                    if ords != [0, 1]:
                        masked_ok = False
                        masked_problems.append(
                            "%s: ExampleMasked пустой, но карточки %s" % (term, ords)
                        )
                if bd.TAG_ROOT not in note.tags:
                    tag_problems.append("%s: нет тега %s" % (term, bd.TAG_ROOT))
                item = novel.items.get(term)
                if item is not None and item["chapterId"] not in note.tags:
                    tag_problems.append(
                        "%s: нет тега главы %s" % (term, item["chapterId"])
                    )
                if item is not None:
                    want_auto = bool((item.get("readingRomaji") or "").strip()) and (
                        item.get("source") == "guide"
                    )
                    if (bd.TAG_AUTO_READING in note.tags) != want_auto:
                        tag_problems.append(
                            "%s: тег %s не соответствует правилу" % (term, bd.TAG_AUTO_READING)
                        )
            else:
                if not note["Text"].strip():
                    empty_text.append(nid)

            for cid in note.card_ids():
                question = col1.get_card(cid).question()
                if not visible_text(question):
                    empty_questions.append((nid, col1.get_card(cid).ord))

        if actual_guids != expected_guids:
            guid_problems.append(
                "лишних/несовпадающих GUID: %d, отсутствующих: %d"
                % (len(actual_guids - expected_guids), len(expected_guids - actual_guids))
            )
        if len(actual_guids) != notes_after_first:
            guid_problems.append("GUID не уникальны")
        if any(len(g) < 10 for g in actual_guids):
            guid_problems.append("найден слишком короткий GUID")

        ck.check(
            "Ни у одной заметки «%s» не пустой Term" % bd.CARD_NT,
            not empty_term,
            "пустых: %d" % len(empty_term),
        )
        ck.check(
            "Ни у одной заметки «%s» не пустой Text" % bd.PHRASE_NT,
            not empty_text,
            "пустых: %d" % len(empty_text),
        )
        ck.check(
            "Карточка «03 Контекст» есть ровно при непустом ExampleMasked",
            masked_ok,
            "\n".join(masked_problems[:20]),
        )
        ck.check(
            "Карточек «%s» ровно %d (по числу непустых ExampleMasked)"
            % (bd.TEMPLATE_CARD_3, stats["masked_items"]),
            stats["cards_by_ord"]["card"].get("ord2", 0) == stats["masked_items"],
            "фактически: %d" % stats["cards_by_ord"]["card"].get("ord2", 0),
        )
        ck.check(
            "Ни у одной карточки нет пустой лицевой стороны",
            not empty_questions,
            "пустых: %d" % len(empty_questions),
        )
        ck.check(
            "GUID заметок детерминированы и уникальны (%d шт.)" % len(expected_guids),
            not guid_problems,
            "\n".join(guid_problems),
        )
        ck.check(
            "Теги проставлены по правилам",
            not tag_problems,
            "\n".join(tag_problems[:20]),
        )

        # ---------------- идемпотентность повторного импорта ---------------
        import_package(col1, apkg)
        notes_after_second = len(col1.find_notes(""))
        cards_after_second = len(col1.find_cards(""))
        ck.check(
            "Повторный импорт того же .apkg не добавляет заметки",
            notes_after_second == notes_after_first,
            "было %d, стало %d" % (notes_after_first, notes_after_second),
        )
        ck.check(
            "Повторный импорт того же .apkg не добавляет карточки",
            cards_after_second == cards_after_first,
            "было %d, стало %d" % (cards_after_first, cards_after_second),
        )
        dup_notetypes = [
            nt["name"]
            for nt in col1.models.all()
            if nt["name"].startswith((bd.CARD_NT, bd.PHRASE_NT))
            and nt["name"] not in (bd.CARD_NT, bd.PHRASE_NT)
        ]
        ck.check(
            "Повторный импорт не создаёт дубликатов типов заметок",
            not dup_notetypes,
            "дубликаты: %s" % dup_notetypes if dup_notetypes else "",
        )

        # ---------------- алгоритм маскирования ---------------------------
        mask_problems = []
        for term, sentence, expected in MASK_REFERENCE_CASES:
            found = bd.find_term(sentence, term)
            got = sentence[found[0]:found[1]] if found else None
            if got != expected:
                mask_problems.append(
                    "%s: ожидалось «%s», получено «%s»" % (term, expected, got)
                )
        ck.check(
            "Маскирование повторяет src/lib/dataset.ts на эталонных словоформах (%d шт.)"
            % len(MASK_REFERENCE_CASES),
            not mask_problems,
            "\n".join(mask_problems),
        )
        # само поле ExampleMasked в импортированной коллекции непусто ровно там,
        # где алгоритм находит слово
        expected_masked = sum(
            1
            for item in novel.items_list
            if bd.make_example_masked(
                ((item.get("examples") or [{}])[0].get("jp") or "")
                if item.get("examples")
                else "",
                item.get("term", ""),
            )
        )
        ck.check(
            "Непустой ExampleMasked у %d элементов (совпадает с расчётом по данным)"
            % expected_masked,
            expected_masked == stats["masked_items"],
            "в коллекции: %d" % stats["masked_items"],
        )

        # ---------------- рендер карточек ---------------------------------
        print("3/6 Рендер карточек в HTML ...")
        rendered = collect_rendered_cards(col1, novel, nt_card, nt_phrase)
        ck.check(
            "Удалось отрендерить карточки для отчёта (%d шт.)" % len(rendered),
            len(rendered) >= 4,
            "rendered=%d" % len(rendered),
        )
        card3 = next(
            (r for r in rendered if r["template"] == "card3"), None
        )
        ck.check(
            "В карточке «03 Контекст» целевое слово заменено на пропуск ［　］",
            card3 is not None
            and '<span class="blank">［　］</span>' in card3["question"]
            and card3["term"] not in visible_text(card3["question"])
            and card3["term"] in visible_text(card3["answer"]),
            "лицевая: %s" % (card3["question"] if card3 else "карточка не найдена"),
        )
    finally:
        col1.close()

    # ---------------- повторяемость сборки --------------------------------
    print("4/6 Повторная сборка и импорт в коллекцию №2 (проверка идемпотентности) ...")
    stats2 = bd.build(verbose=False)
    shutil.copy2(stats2["apkg_path"], RUN2_APKG)
    col2 = open_fresh_collection(VERIFY_COL_2)
    try:
        import_package(col2, RUN2_APKG)
        nt_card2 = col2.models.by_name(bd.CARD_NT)
        nt_phrase2 = col2.models.by_name(bd.PHRASE_NT)
        ck.check(
            "Id типа заметки «%s» не меняется между сборками" % bd.CARD_NT,
            nt_card2["id"] == stats["notetype_ids"][bd.CARD_NT],
            "было %s, стало %s"
            % (stats["notetype_ids"][bd.CARD_NT], nt_card2["id"]),
        )
        ck.check(
            "Id типа заметки «%s» не меняется между сборками" % bd.PHRASE_NT,
            nt_phrase2["id"] == stats["notetype_ids"][bd.PHRASE_NT],
            "было %s, стало %s"
            % (stats["notetype_ids"][bd.PHRASE_NT], nt_phrase2["id"]),
        )
        guids2 = {col2.get_note(nid).guid for nid in col2.find_notes("")}
        guids1 = {bd.make_guid("item", i["id"]) for i in novel.items_list}
        guids1 |= {bd.make_guid("phrase", f["id"]) for f in novel.fragments_list}
        ck.check(
            "Состав GUID одинаков во всех сборках",
            guids2 == guids1,
        )
        ck.check(
            "Повторная сборка даёт те же числа заметок/карточек",
            len(col2.find_notes("")) == stats["notes_total"]
            and len(col2.find_cards("")) == stats["cards_total"],
            "заметок %d, карточек %d"
            % (len(col2.find_notes("")), len(col2.find_cards(""))),
        )
    finally:
        col2.close()

    # ---------------- реальная коллекция ----------------------------------
    print("5/6 Контроль неприкосновенности реальной коллекции Anki ...")
    real_after = snapshot_real_collection()
    if not real_before["exists"]:
        ck.check(
            "Реальная коллекция Anki (%APPDATA%\\Anki2) не затрагивалась",
            True,
            "каталог %s отсутствует — трогать было нечего" % real_before["base"],
        )
    else:
        changed = [
            p
            for p, v in real_before["files"].items()
            if real_after["files"].get(p) != v
        ]
        ck.check(
            "Реальная коллекция Anki (%APPDATA%\\Anki2) не затрагивалась",
            not changed,
            "изменились: %s" % changed if changed else "файлы не изменялись",
        )

    # ---------------- отчёт ------------------------------------------------
    print("6/6 Формирование отчёта ...")
    passed = not ck.failed
    report = build_report(stats, ck, rendered, layout_expected, stats2)
    bd.write_report(report)

    print("")
    print(ck.render())
    print("")
    print("ИТОГ: %s" % ("ПРОВЕРКА ПРОЙДЕНА" if passed else "ПРОВЕРКА НЕ ПРОЙДЕНА"))
    print("Отчёт: %s" % REPORT_PATH)
    return 0 if passed else 1


class _DummyDecks(dict):
    def __missing__(self, key):
        return 0


# Эталонные словоформы: питоновский алгоритм маскирования обязан повторять
# findTerm()/expandToWord() из src/lib/dataset.ts. Ожидаемые фрагменты получены
# прогоном САМОГО dataset.ts под Node.js: tools/_ankitest/mask_ref_run.mjs
# транспилирует src/lib/dataset.ts пакетом typescript, tools/_ankitest/
# mask_ref_cases.mjs вызывает его функции. Значения вручную не подгонялись.
MASK_REFERENCE_CASES = [
    ("望む", "その席に座っている間だけ望んだ通り", "望んだ"),
    ("見上げる", "女は男の顔を見上げて怪訝", "見上げて"),
    ("飲み込む", "意味が飲み込めず、思わず", "飲み込めず"),
    ("注ぐ", "コーヒーをカップに注いでから", "注いで"),
    ("冷める", "コーヒーが冷める。", "冷める"),
    ("突き出す", "下唇を少し突き出した。", "突き出した"),
    ("苛立つ", "房木は苛立って手を振った", "苛立って"),
    ("謝る", "久美に謝りたいんだ", "謝りた"),
    ("努力", "どんな努力をしても", "努力"),
    ("先客", "席には先客がいる", "先客"),
]


def collect_rendered_cards(col: Collection, novel: bd.Novel, nt_card, nt_phrase):
    """Возвращает список словарей с одной отрендеренной карточкой каждого шаблона.

    Для наглядности выбираются заметки с КОРОТКИМ, но осмысленным примером:
    примеры-абзацы раздувают отчёт, а примеры в 2-3 символа ничего не показывают.
    """
    MIN_EXAMPLE = 8
    MAX_EXAMPLE = 120
    MASK_TOKEN = '<span class="blank">［　］</span>'

    candidates = []
    for nid in col.find_notes(""):
        note = col.get_note(nid)
        if note.mid != nt_card["id"]:
            continue
        cards = {col.get_card(c).ord: col.get_card(c) for c in note.card_ids()}
        length = len(note["Example"])
        if MIN_EXAMPLE <= length <= MAX_EXAMPLE:
            rank = 0
        elif length:
            rank = 1
        else:
            rank = 2
        # для карточки «03 Контекст» пропуск не должен съедать весь пример
        mask_context = len(visible_text(note["ExampleMasked"]).replace(MASK_TOKEN, ""))
        candidates.append((rank, length, -mask_context, note, cards))

    candidates.sort(key=lambda x: (x[0], x[1], x[2]))

    picked: dict = {}
    for rank, _length, _ctx, note, cards in candidates:
        has_mask = bool(note["ExampleMasked"].strip())
        if 0 in cards and "card1" not in picked:
            picked["card1"] = (note, cards[0])
        if 1 in cards and "card2" not in picked:
            picked["card2"] = (note, cards[1])
        if has_mask and 2 in cards and "card3" not in picked and rank == 0:
            picked["card3"] = (note, cards[2])
        if len(picked) == 3:
            break

    out = []
    labels = {
        "card1": "Шаблон «%s»" % bd.TEMPLATE_CARD_1,
        "card2": "Шаблон «%s»" % bd.TEMPLATE_CARD_2,
        "card3": "Шаблон «%s»" % bd.TEMPLATE_CARD_3,
    }
    for key in ("card1", "card2", "card3"):
        if key not in picked:
            continue
        note, card = picked[key]
        out.append(
            {
                "template": key,
                "title": "%s — заметка «%s»" % (labels[key], note["Term"]),
                "term": note["Term"],
                "question": STYLE_RE.sub("", card.question()).strip(),
                "answer": STYLE_RE.sub("", card.answer()).strip(),
            }
        )

    phrase_notes = [
        col.get_note(nid)
        for nid in col.find_notes("")
        if col.get_note(nid).mid == nt_phrase["id"]
    ]
    if phrase_notes:
        note = min(phrase_notes, key=lambda n: len(n["Text"]))
        card = col.get_card(note.card_ids()[0])
        out.append(
            {
                "template": "phrase",
                "title": "Шаблон «%s» (фраза) — %s"
                % (bd.TEMPLATE_PHRASE, note["Chapter"]),
                "term": note["Text"][:40],
                "question": STYLE_RE.sub("", card.question()).strip(),
                "answer": STYLE_RE.sub("", card.answer()).strip(),
            }
        )
    return out


def build_report(stats, ck, rendered, layout_expected, stats2) -> str:
    stats_css = bd.SHARED_CSS
    lines = [bd.render_build_report(stats)]
    add = lines.append
    add("")
    add("=" * 78)
    add("ПРОВЕРКА КОЛОДЫ (tools/verify_deck.py)")
    add("=" * 78)
    add("Дата проверки          : %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    add("Проверяемый файл       : %s" % stats["apkg_path"])
    add("Временная коллекция №1 : %s" % VERIFY_COL_1)
    add("Временная коллекция №2 : %s" % VERIFY_COL_2)
    add("Метод импорта          : Collection.import_anki_package(ImportAnkiPackageRequest)")
    add("Реальная коллекция     : %s" % (snapshot_real_collection()["base"] or "не найдена"))
    add("")
    add("-" * 78)
    add("РЕЗУЛЬТАТЫ ПРОВЕРОК")
    add("-" * 78)
    add(ck.render())
    add("")
    add("-" * 78)
    add("ЗАМЕТКИ И КАРТОЧКИ ПО КОЛОДАМ")
    add("-" * 78)
    add("%-50s %15s %15s" % ("Колода", "заметок", "карточек"))
    add("%-50s %15s %15s" % ("", "ожид./факт.", "ожид./факт."))
    add("-" * 78)
    total_notes = 0
    total_cards = 0
    leaf_stats = stats["leaves"]
    for dname in sorted(layout_expected):
        exp = layout_expected[dname]
        got = leaf_stats.get(dname, {"notes": 0, "cards": 0})
        total_notes += exp["notes"]
        total_cards += exp["cards"]
        mark = " " if (exp["notes"] == got["notes"] and exp["cards"] == got["cards"]) else "!"
        short = dname.replace(stats["root_deck"] + "::", "")
        add(
            "%s%-49s %6d/%-6d %6d/%-6d"
            % (mark, short, exp["notes"], got["notes"], exp["cards"], got["cards"])
        )
    add("-" * 78)
    add("%-50s %6d/%-6d %6d/%-6d"
        % ("ИТОГО", total_notes, stats["notes_total"], total_cards, stats["cards_total"]))
    add("")
    add("Глав всего: %d (00 プロローグ, 01 恋人, 02 夫婦, 03 姉妹, 04 親子)" % stats["expected_chapters"])
    add("Карточек по шаблонам «%s»: %s"
        % (bd.CARD_NT, ", ".join(
            "%s=%d" % (name, stats["cards_by_ord"]["card"].get("ord%d" % i, 0))
            for i, name in enumerate(
                (bd.TEMPLATE_CARD_1, bd.TEMPLATE_CARD_2, bd.TEMPLATE_CARD_3)
            )
        )))
    add("Карточек по шаблону «%s»: %d"
        % (bd.PHRASE_NT, stats["cards_by_ord"]["phrase"].get("ord0", 0)))
    add("")
    add("-" * 78)
    add("ОТРЕНДЕРЕННЫЕ КАРТОЧКИ (HTML из импортированной коллекции, без блока <style>)")
    add("-" * 78)
    for item in rendered:
        add("")
        add("### %s" % item["title"])
        add("--- ЛИЦЕВАЯ СТОРОНА ---")
        add(item["question"])
        add("--- ОБРАТНАЯ СТОРОНА ---")
        add(item["answer"])
    add("")
    add("-" * 78)
    add("CSS ТИПОВ ЗАМЕТОК (общий блок для обоих типов)")
    add("-" * 78)
    add(stats_css)
    add("")
    add("=" * 78)
    add("ИТОГ ПРОВЕРКИ: %s" % ("ПРОВЕРКА ПРОЙДЕНА" if not ck.failed else "ПРОВЕРКА НЕ ПРОЙДЕНА"))
    add("Всего проверок: %d, провалено: %d" % (len(ck.results), len(ck.failed)))
    add("=" * 78)
    return "\n".join(lines)


def main(argv=None) -> int:
    return run_verification()


if __name__ == "__main__":
    raise SystemExit(main())
