#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собирает разбор романа «コーヒーが冷めないうちに» из Markdown-пособия
в структурированный датасет для тренажёра и генератора колод Anki.

Запуск:
    python tools/parse_sources.py
    python tools/parse_sources.py --guide <файл.md> --chapters <файл.md>

Вход:  Markdown-файлы пособия (см. tools/sources.json).
Выход: src/data/novel.json, tools/report_parse.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "tools", "sources.json")

KANA_RE = re.compile(r"^[\u3040-\u309F\u30A0-\u30FF\u30FC\u3005ー\s]+$")
ROMAJI_RE = re.compile(r"^[a-zA-Z\u0100-\u01FF\u1E00-\u1EFF'\-\.\s]+$")
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LEVEL_RE = re.compile(r"\((N[1-5](?:\s*[-–—]\s*N[1-5])?)\)")
DASH_RE = re.compile(r"\s+[—–]\s+|\s+-\s+")
CHAPTER_RE = re.compile(r"ГЛАВА\s*(\d+)")

CHAPTER_TITLES = {
    0: {"jp": "プロローグ", "ru": "Пролог"},
    1: {"jp": "恋人", "ru": "Любовник"},
    2: {"jp": "夫婦", "ru": "Супруги"},
    3: {"jp": "姉妹", "ru": "Сёстры"},
    4: {"jp": "親子", "ru": "Родители и дети"},
}

KIND_MAP = {
    "лексика": "vocab",
    "грамматика": "grammar",
    "ономатопея": "onomatopoeia",
    "выражения": "phrase",
    "фразы": "phrase",
    "кандзи": "kanji",
}

MARKER_RE = re.compile(
    r"^\*\*(Оригинал|Ромадзи|Перевод|Лингвистические комментарии)([^*]*)\*\*\s*$",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^(\s*)[\*\-]\s+(.*)$")
KIND_RE = re.compile(
    r"^\*\*(Лексика|Грамматика|Ономатопея|Выражения|Фразы|Кандзи)\s*(\([^)]*\))?\s*\:?\*\*\s*(.*)$",
    re.IGNORECASE,
)
GENERIC_LABEL_RE = re.compile(r"^\*\*(.+?)\s*\:?\*\*\s*(.*)$")
SEG_SPLIT_RE = re.compile(r"\s*[,、;]\s*(?![^()]*\))")
JAPANESE_RE = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]")
SENT_SPLIT_RE = re.compile(r"(?<=[。！？])")


def sha1_of(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_sources(config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    overrides = {"guide": args.guide, "chapters": args.chapters}
    for entry in config["sources"]:
        path = overrides.get(entry["role"]) or entry["path"]
        sources.append({"role": entry["role"], "path": path})
    if args.analysis:
        sources.append({"role": "analysis", "path": args.analysis})
    elif config.get("analysis"):
        sources.append({"role": "analysis", "path": config["analysis"]["path"]})
    for src in sources:
        if not os.path.exists(src["path"]):
            raise SystemExit(f"Не найден источник ({src['role']}): {src['path']}")
    return sources


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_reading(value: str) -> str:
    v = value.strip()
    if not v:
        return "none"
    if KANA_RE.match(v):
        return "kana"
    if ROMAJI_RE.match(v):
        return "romaji"
    return "note"


@dataclass
class Item:
    id: str
    kind: str
    term: str
    readingKana: str = ""
    readingRomaji: str = ""
    note: str = ""
    meaning: str = ""
    level: str = ""
    pattern: bool = False
    chapterId: str = ""
    fragmentIds: list[str] = field(default_factory=list)
    examples: list[dict[str, str]] = field(default_factory=list)
    source: str = "guide"
    needsReview: bool = False

    def key(self) -> str:
        return self.term


@dataclass
class Fragment:
    id: str
    chapterId: str
    index: int
    heading: str
    original: str = ""
    romaji: str = ""
    translation: str = ""
    notes: list[str] = field(default_factory=list)
    itemKeys: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list, repr=False)


# --------------------------------------------------------------------------
# Разбор элементов списка лексики/грамматики
# --------------------------------------------------------------------------

def split_parentheticals(text: str) -> tuple[str, list[str]]:
    """Возвращает (текст без скобок, список содержимых скобок)."""
    parts: list[str] = []

    def repl(match: re.Match[str]) -> str:
        parts.append(match.group(1).strip())
        return " "

    outer = re.sub(r"\(([^()]*)\)", repl, text)
    return clean(outer), parts


def _apply_parens(item: Item, text: str) -> str:
    """Раскладывает скобки из текста: чтения, уровни, пояснения. Возвращает текст без скобок."""
    clean_text, parens = split_parentheticals(text)
    for p in parens:
        cls = classify_reading(p)
        if LEVEL_RE.match(f"({p})"):
            item.level = item.level or clean(p).replace(" ", "")
        elif cls == "kana" and not item.readingKana:
            item.readingKana = p
        elif cls == "romaji" and not item.readingRomaji:
            item.readingRomaji = p
        else:
            if p and p not in item.note.split("; "):
                item.note = "; ".join(x for x in [item.note, p] if x)
    return clean_text


def _build_item(head: str, meaning: str, kind: str, chapter_id: str, level: str) -> Item | None:
    term, parens = split_parentheticals(head)
    term = clean(term).strip("。.,;:")
    if not term:
        return None

    item = Item(id="", kind=kind, term=term, level=level, chapterId=chapter_id)
    for p in parens:
        cls = classify_reading(p)
        if LEVEL_RE.match(f"({p})"):
            item.level = item.level or clean(p).replace(" ", "")
        elif cls == "kana" and not item.readingKana:
            item.readingKana = p
        elif cls == "romaji" and not item.readingRomaji:
            item.readingRomaji = p
        else:
            item.note = "; ".join(x for x in [item.note, p] if x)

    meaning_clean = _apply_parens(item, meaning)
    if not meaning_clean and item.note:
        cyr = [n for n in item.note.split("; ") if CYRILLIC_RE.search(n)]
        if cyr:
            meaning_clean = "; ".join(cyr)
            item.note = "; ".join(n for n in item.note.split("; ") if n not in cyr)

    # Термины с кириллицей — это комментарий, а не слово.
    if CYRILLIC_RE.search(term) or not JAPANESE_RE.search(term):
        item.kind = "note"
        item.meaning = meaning_clean or clean(meaning)
        return item

    if not item.readingKana:
        bare = term.lstrip("〜~")
        if KANA_RE.match(bare):
            item.readingKana = bare

    item.meaning = meaning_clean
    item.pattern = bool(re.search(r"[〜~]|^[VNA]d?j?[-+]|\+", term))
    return item


def _merge_extra(item: Item, extra: str) -> None:
    """Дописывает продолжение значения (`лязг, стук`) к элементу."""
    piece = _apply_parens(item, extra)
    if not piece:
        return
    item.meaning = clean(f"{item.meaning}, {piece}") if item.meaning else piece


def parse_item_line(raw: str, kind: str, chapter_id: str) -> list[Item]:
    """Разбирает строку вида `ガチャリ (gachari) — лязг, стук; びくり (bikuri) — вздрагивание.`

    Возвращает список элементов; элементы с kind == 'note' — это комментарии,
    а не словарные единицы.
    """
    text = clean(raw).rstrip("。.")
    if not text:
        return []

    line_level = ""
    m = LEVEL_RE.search(text)
    if m:
        line_level = clean(m.group(1)).replace(" ", "")
    text = clean(LEVEL_RE.sub(" ", text))

    items: list[Item] = []
    current: Item | None = None
    for segment in SEG_SPLIT_RE.split(text):
        segment = clean(segment).strip("。.,;:")
        if not segment:
            continue
        dash = DASH_RE.search(segment)
        if dash:
            head = clean(segment[: dash.start()]).rstrip("。.,;:")
            meaning = clean(segment[dash.end():])
            current = _build_item(head, meaning, kind, chapter_id, line_level)
            if current:
                items.append(current)
        elif current is None:
            current = _build_item(segment, "", kind, chapter_id, line_level)
            if current:
                items.append(current)
        else:
            _merge_extra(current, segment)
    return items


# --------------------------------------------------------------------------
# Разбор Markdown
# --------------------------------------------------------------------------

def chapter_from_title(title: str) -> tuple[str, str] | None:
    upper = title.upper()
    if "ПРОЛОГ" in upper:
        return "prologue", ""
    m = CHAPTER_RE.search(upper)
    if m:
        return f"ch{int(m.group(1))}", ""
    return None


def parse_section(
    lines: list[str],
    chapter_id: str,
    skip_headings: list[str] | None = None,
) -> tuple[list[Fragment], list[Item], list[str]]:
    fragments: list[Fragment] = []
    items: list[Item] = []
    problems: list[str] = []
    skip_headings = skip_headings or []

    # режем секцию на фрагменты по '### '
    chunk: list[str] = []
    heading = ""
    chunks: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("### "):
            if heading or chunk:
                chunks.append((heading, chunk))
            heading = clean(line[4:])
            chunk = []
        else:
            chunk.append(line)
    if heading or chunk:
        chunks.append((heading, chunk))

    index = 0
    for heading, body in chunks:
        if not heading:
            continue
        index += 1
        frag = Fragment(
            id=f"{chapter_id}-{index:02d}",
            chapterId=chapter_id,
            index=index,
            heading=heading,
        )
        current: str | None = None
        buffer: list[str] = []
        comments: list[str] = []

        def flush() -> None:
            nonlocal current, buffer
            if current is None:
                return
            text = clean(" ".join(buffer))
            if current == "original":
                frag.original = text
            elif current == "romaji":
                frag.romaji = text
            elif current == "translation":
                frag.translation = text
            current, buffer = None, []

        for line in body:
            m = MARKER_RE.match(line.strip())
            if m:
                flush()
                kind = m.group(1).lower()
                if kind.startswith("оригинал"):
                    current = "original"
                elif kind.startswith("ромадзи"):
                    current = "romaji"
                elif kind.startswith("перевод"):
                    current = "translation"
                else:
                    current = "comments"
                continue
            if current is None:
                continue
            if current == "comments":
                comments.append(line)
            else:
                buffer.append(line)
        flush()

        if not frag.original:
            continue
        if not any(marker.lower() in heading.lower() for marker in skip_headings):
            parse_comments(comments, frag)
        fragments.append(frag)
        items.extend(frag.items)

    return fragments, items, problems


def context_sentence(text: str, term: str) -> str:
    """Выделяет предложение с целевым словом, чтобы карточка не показывала весь абзац."""
    if not text:
        return ""
    candidates: list[str] = []
    for base in (term, searchable_term(term)):
        if not base:
            continue
        candidates.append(base)
        # Отсекаем окуригану: 望む → 望, 冷めて → 冷 (в тексте слово может быть в другой форме).
        stem = base
        while len(stem) > 1 and KANA_RE.match(stem[-1]):
            stem = stem[:-1]
            if JAPANESE_RE.search(stem):
                candidates.append(stem)
    for sentence in SENT_SPLIT_RE.split(text):
        sentence = sentence.strip().lstrip("」』）)。、！？ ")
        if not sentence:
            continue
        for candidate in candidates:
            if candidate and candidate in sentence:
                return sentence
    return ""


def searchable_term(term: str) -> str:
    return re.sub(r"\s*\+\s*", "", term.lstrip("〜~")).strip()


def _absorb(items: list[Item], frag: Fragment, kind_hint: str = "") -> None:
    for item in items:
        if item.kind == "note" or not item.term:
            text = clean(f"{item.term} — {item.meaning}" if item.meaning else item.term)
            if text:
                frag.notes.append(text)
            continue
        item.fragmentIds = [frag.id]
        snippet = context_sentence(frag.original, item.term) or frag.original
        item.examples = [
            {
                "jp": snippet,
                "jpFull": frag.original,
                "romaji": frag.romaji,
                "ru": frag.translation,
                "fragmentId": frag.id,
            }
        ]
        frag.itemKeys.append(item.key())
        frag.items.append(item)


def parse_comments(comments: list[str], frag: Fragment) -> None:
    pending_kind: str | None = None

    for line in comments:
        stripped = line.strip()
        if not stripped or stripped.startswith("---"):
            continue
        bullet = BULLET_RE.match(line)
        content = stripped
        if bullet:
            content = bullet.group(2).strip()
        elif not stripped.startswith("*"):
            continue

        kind_match = KIND_RE.match(content)
        if kind_match:
            label = kind_match.group(1).lower()
            kind = KIND_MAP.get(label, "vocab")
            inline = kind_match.group(3).strip()
            pending_kind = None
            if kind == "kanji":
                if inline:
                    frag.notes.append("Кандзи: " + clean(inline).rstrip("。."))
                else:
                    pending_kind = "kanji-raw"
                continue
            if not inline:
                pending_kind = kind
                continue
            _absorb(parse_item_line(inline, kind, frag.chapterId), frag)
            continue

        if pending_kind == "kanji-raw":
            frag.notes.append("Кандзи: " + clean(content).rstrip("。."))
            continue

        generic = GENERIC_LABEL_RE.match(content)
        if generic:
            label = clean(generic.group(1))
            rest = generic.group(2).strip()
            if DASH_RE.search(rest):
                _absorb(parse_item_line(rest, "grammar", frag.chapterId), frag)
            else:
                frag.notes.append(f"{label}: {clean(rest).rstrip('。.')}")
            continue

        if pending_kind:
            _absorb(parse_item_line(content, pending_kind, frag.chapterId), frag)
            continue

        frag.notes.append(clean(content).lstrip("*").strip())


def merge_items(all_items: list[Item]) -> list[Item]:
    """Склеивает одинаковые термины: объединяет фрагменты, дополняет поля."""
    merged: dict[str, Item] = {}
    order: list[str] = []
    for item in all_items:
        key = item.key()
        if key not in merged:
            merged[key] = item
            order.append(key)
            continue
        base = merged[key]
        for fid in item.fragmentIds:
            if fid not in base.fragmentIds:
                base.fragmentIds.append(fid)
        for ex in item.examples:
            if ex["fragmentId"] not in {e["fragmentId"] for e in base.examples}:
                base.examples.append(ex)
        base.readingKana = base.readingKana or item.readingKana
        base.readingRomaji = base.readingRomaji or item.readingRomaji
        base.meaning = base.meaning or item.meaning
        base.note = base.note or item.note
        base.level = base.level or item.level
    return [merged[k] for k in order]


ANALYSIS_HEAD_RE = re.compile(r"^#{3,4}\s*(?:\S+\s)*ГЛАВА\s*(\d+)", re.IGNORECASE)
ANALYSIS_VOCAB_RE = re.compile(r"^#{4}\s*Лексический минимум", re.IGNORECASE)
GROUP_RE = re.compile(r"^\*\*(.+?)\:\*\*\s*$")


def parse_analysis(lines: list[str], known: set[str], problems: list[str]) -> list[Item]:
    """Лексические минимумы из файла расширенного анализа (без примеров).

    `known` — множество уже известных терминов (по написанию, без учёта типа).
    """
    chapter_id = ""
    in_vocab = False
    group = ""
    items: list[Item] = []
    for line in lines:
        head = ANALYSIS_HEAD_RE.match(line)
        if head:
            chapter_id = f"ch{int(head.group(1))}"
            in_vocab = False
            group = ""
            continue
        if line.startswith("#### ") and not ANALYSIS_VOCAB_RE.match(line):
            in_vocab = False
            continue
        if ANALYSIS_VOCAB_RE.match(line):
            in_vocab = True
            continue
        if not in_vocab or not chapter_id:
            continue
        g = GROUP_RE.match(line.strip())
        if g:
            group = clean(g.group(1))
            continue
        b = BULLET_RE.match(line)
        if not b:
            continue
        parsed = parse_item_line(b.group(2), "vocab", chapter_id)
        for item in parsed:
            if item.kind == "note":
                continue
            item.source = "analysis"
            item.note = item.note or group
            if item.term in known:
                continue
            known.add(item.term)
            items.append(item)
    return items


# --------------------------------------------------------------------------
# Основной проход
# --------------------------------------------------------------------------

def split_chapters(lines: list[str]) -> list[tuple[str, list[str]]]:
    result: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    buffer: list[str] = []
    for line in lines:
        if line.startswith("## "):
            title = line[3:]
            found = chapter_from_title(title)
            if current_id and buffer:
                result.append((current_id, buffer))
            buffer = []
            current_id = found[0] if found else None
            continue
        if line.startswith("# "):
            continue
        if current_id:
            buffer.append(line)
    if current_id and buffer:
        result.append((current_id, buffer))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка датасета романа из Markdown-пособия")
    ap.add_argument("--guide")
    ap.add_argument("--chapters")
    ap.add_argument("--analysis")
    ap.add_argument("--config", default=CONFIG_PATH)
    args = ap.parse_args()

    config = json.load(open(args.config, encoding="utf-8"))
    sources = resolve_sources(config, args)

    problems: list[str] = []
    fragments: list[Fragment] = []
    items: list[Item] = []
    used: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}

    for src in sources:
        if src["role"] == "analysis":
            continue
        digest = sha1_of(src["path"])
        if digest in seen_hashes:
            problems.append(
                f"Пропущен дубликат файла: {os.path.basename(src['path'])} "
                f"(совпадает с {os.path.basename(seen_hashes[digest])})"
            )
            continue
        seen_hashes[digest] = src["path"]
        raw = open(src["path"], encoding="utf-8").read().replace("\r\n", "\n")
        lines = raw.split("\n")
        count_before = len(fragments)
        skip_headings = config.get('skipItemsInHeadings', [])
        for chapter_id, section_lines in split_chapters(lines):
            frags, found, probs = parse_section(section_lines, chapter_id, skip_headings)
            fragments.extend(frags)
            items.extend(found)
            problems.extend(probs)
        used.append(
            {
                "role": src["role"],
                "file": os.path.basename(src["path"]),
                "sha1": digest,
                "chapters": sorted({f.chapterId for f in fragments[count_before:]}),
                "fragments": len(fragments) - count_before,
            }
        )

    merged = merge_items(items)
    known = {i.term for i in merged}
    for src in sources:
        if src["role"] != "analysis":
            continue
        raw = open(src["path"], encoding="utf-8").read().replace("\r\n", "\n")
        extra = parse_analysis(raw.split("\n"), known, problems)
        merged.extend(extra)
        used.append(
            {
                "role": "analysis",
                "file": os.path.basename(src["path"]),
                "sha1": sha1_of(src["path"]),
                "chapters": sorted({i.chapterId for i in extra}),
                "fragments": 0,
            }
        )

    # Ручные чтения (кана) из data/readings.json имеют приоритет
    override_path = os.path.join(ROOT, config.get("readingsOverride", "data/readings.json"))
    overridden = 0
    if os.path.exists(override_path):
        overrides = json.load(open(override_path, encoding="utf-8"))
        by_term = {}
        for item in merged:
            by_term.setdefault(item.term, []).append(item)
        for term, reading in overrides.items():
            if term.startswith("_"):
                continue
            value = reading
            if re.search(r"[A-Za-z]", term):
                # Для шаблонов вида `Nの + ため` чтение берём из японской части термина.
                remnant = clean(
                    re.sub(r"[A-Za-z+]+", " ", term).replace("〜", "").replace("~", "")
                )
                if remnant and KANA_RE.match(remnant):
                    value = remnant
            for item in by_term.get(term, []):
                if value and value != item.readingKana:
                    item.readingKana = value
                    overridden += 1

    for item in merged:
        item.id = item.key()
        if not item.readingKana and item.readingRomaji:
            item.needsReview = True

    chapter_ids = sorted(
        {f.chapterId for f in fragments},
        key=lambda c: 0 if c == "prologue" else int(c[2:]),
    )
    chapters = []
    for cid in chapter_ids:
        num = 0 if cid == "prologue" else int(cid[2:])
        chapters.append(
            {
                "id": cid,
                "number": num,
                "titleJp": CHAPTER_TITLES.get(num, {}).get("jp", cid),
                "titleRu": CHAPTER_TITLES.get(num, {}).get("ru", cid),
                "fragmentIds": [f.id for f in fragments if f.chapterId == cid],
                "itemKeys": [i.key() for i in merged if i.chapterId == cid],
            }
        )

    dataset = {
        "meta": {
            "title": "コーヒーが冷めないうちに",
            "titleRu": "Пока не остыл кофе",
            "author": "川口俊和 (Кавагути Тосикадзу)",
            "level": "N3–N2",
            "sources": used,
            "counts": {
                "chapters": len(chapters),
                "fragments": len(fragments),
                "items": len(merged),
                "withKana": sum(1 for i in merged if i.readingKana),
                "needsReview": sum(1 for i in merged if i.needsReview),
                "overriddenReadings": overridden,
            },
        },
        "chapters": chapters,
        "fragments": [
            {k: v for k, v in asdict(f).items() if k != "items"} for f in fragments
        ],
        "items": [asdict(i) for i in merged],
        "problems": problems,
    }

    out_path = os.path.join(ROOT, config["outputDataset"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=1)

    counts = dataset["meta"]["counts"]
    report = [
        "Отчёт сборки датасета",
        "=" * 40,
        f"Глав: {counts['chapters']}",
        f"Фрагментов текста: {counts['fragments']}",
        f"Словарных единиц: {counts['items']}",
        f"С каной: {counts['withKana']}  (нужно проверить: {counts['needsReview']})",
        f"Чтений из data/readings.json: {counts['overriddenReadings']}",
        "",
        "По главам:",
    ]
    for ch in chapters:
        report.append(
            f"  {ch['id']:<9} {ch['titleJp']:<8} фрагментов: {len(ch['fragmentIds']):>3}"
            f"  единиц: {len(ch['itemKeys']):>3}"
        )
    kinds: dict[str, int] = {}
    for item in merged:
        kinds[item.kind] = kinds.get(item.kind, 0) + 1
    report.append("")
    report.append("По типам: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    if problems:
        report.append("")
        report.append(f"Замечания ({len(problems)}):")
        report.extend("  " + p for p in problems[:60])
    report_path = os.path.join(ROOT, config["outputReport"])
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"OK: {out_path}")
    print(f"OK: {report_path}")
    print("\n".join(report[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
