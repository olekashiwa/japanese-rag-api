/** Индексация датасета и генерация карточек. */

import raw from '../data/novel.json';
import type { CardDef, CardKind, Chapter, Dataset, Fragment, Item, ItemKind } from '../types';

export const dataset = raw as unknown as Dataset;

export const items: Item[] = dataset.items;
export const fragments: Fragment[] = dataset.fragments;
export const chapters: Chapter[] = dataset.chapters;

export const itemById = new Map<string, Item>(items.map((i) => [i.id, i]));
export const fragmentById = new Map<string, Fragment>(fragments.map((f) => [f.id, f]));
export const chapterById = new Map<string, Chapter>(chapters.map((c) => [c.id, c]));

export const KIND_LABELS: Record<ItemKind, string> = {
  vocab: 'Слова',
  grammar: 'Грамматика',
  onomatopoeia: 'Звукоподражания',
  phrase: 'Фразы',
};

export const CARD_KIND_LABELS: Record<CardKind, string> = {
  recog: 'Японский → значение',
  prod: 'Значение → японский',
  context: 'Слово в контексте',
  phrase: 'Фразы из романа',
  listen: 'Аудирование',
};

export const CHAPTER_LABELS: Record<string, string> = Object.fromEntries(
  chapters.map((c) => [c.id, c.number === 0 ? `${c.titleRu} (${c.titleJp})` : `Глава ${c.number}: ${c.titleRu} (${c.titleJp})`]),
);

/** Убирает приметы грамматического шаблона, чтобы найти слово в предложении. */
export function searchable(term: string): string {
  return term.replace(/^[〜~]/, '').replace(/\s*\+\s*/g, '').replace(/\s+/g, '');
}

function isKana(ch: string | undefined): boolean {
  if (!ch) return false;
  return /[\u3040-\u309F\u30A0-\u30FF\u30FC]/.test(ch);
}

function isJapanese(ch: string | undefined): boolean {
  if (!ch) return false;
  return /[\u3040-\u30FF\u4E00-\u9FFF]/.test(ch);
}

function kanaSuffixLength(term: string): number {
  let count = 0;
  for (let i = term.length - 1; i >= 0 && isKana(term[i]); i -= 1) count += 1;
  return count;
}

/** Варианты написания слова: полная форма и основа без окуриганы (望む → 望). */
export function termCandidates(term: string): string[] {
  const out: string[] = [];
  for (const base of [term, searchable(term)]) {
    if (!base) continue;
    out.push(base);
    let stem = base;
    while (stem.length > 1 && isKana(stem[stem.length - 1])) {
      stem = stem.slice(0, -1);
      if (isJapanese(stem)) out.push(stem);
    }
  }
  return Array.from(new Set(out));
}

/** Расширяет найденный фрагмент до целой словоформы (望 → 望んだ, 見 → 見上げて). */
function expandToWord(sentence: string, start: number, end: number, term: string): [number, number] {
  const base = searchable(term);
  const inTerm = new Set(Array.from(base));
  const suffix = kanaSuffixLength(base);
  // Кану справа добираем только у слов с окуриганой (望む → 望んだ).
  // Если слово кончается иероглифом (努力, 先客), частицу не захватываем.
  const kanaLimit = suffix > 0 ? suffix + 1 : 0;
  let left = start;
  let right = end;
  let taken = 0;
  while (right < sentence.length) {
    const ch = sentence[right];
    if (!isKana(ch) && inTerm.has(ch)) {
      right += 1;
      continue;
    }
    if (isKana(ch) && taken < kanaLimit) {
      right += 1;
      taken += 1;
      continue;
    }
    break;
  }
  // Влево — только иероглифы, входящие в само слово: кану слева не захватываем,
  // иначе в пропуск попадают частицы и окончания соседних слов.
  while (left > 0 && !isKana(sentence[left - 1]) && inTerm.has(sentence[left - 1])) {
    left -= 1;
  }
  return [left, right];
}

/** Находит искомое слово (в любой словоформе) в предложении; возвращает [начало, конец). */
export function findTerm(haystack: string, term: string): [number, number] | null {
  for (const candidate of termCandidates(term)) {
    const index = haystack.indexOf(candidate);
    if (index >= 0) {
      const span = expandToWord(haystack, index, index + candidate.length, term);
      return span[1] - span[0] >= 2 ? span : null;
    }
  }
  return null;
}

/** Предложение с пропуском вместо целевого слова (для карточки «в контексте»). */
export function maskTerm(sentence: string, term: string): string | null {
  const found = findTerm(sentence, term);
  if (!found) return null;
  const [start, end] = found;
  return `${sentence.slice(0, start)}［　］${sentence.slice(end)}`;
}

/** Разбивает предложение на три части вокруг искомого слова. */
export function splitAroundTerm(sentence: string, term: string): [string, string, string] | null {
  const found = findTerm(sentence, term);
  if (!found) return null;
  const [start, end] = found;
  return [sentence.slice(0, start), sentence.slice(start, end), sentence.slice(end)];
}

export function itemsOfChapter(chapterId: string): Item[] {
  return items.filter((i) => i.chapterId === chapterId);
}

export function fragmentsOfChapter(chapterId: string): Fragment[] {
  return fragments.filter((f) => f.chapterId === chapterId);
}

export function primaryExample(item: Item): Item['examples'][number] | undefined {
  return item.examples[0];
}

/** Все карточки, которые можно построить по датасету, с учётом выбранных глав. */
export function buildCards(chapterIds: string[], cardKinds: CardKind[]): CardDef[] {
  const wantChapters = new Set(chapterIds);
  const wantKinds = new Set(cardKinds);
  const cards: CardDef[] = [];

  for (const item of items) {
    if (!wantChapters.has(item.chapterId)) continue;
    const tags = [item.chapterId, item.kind, ...(item.level ? [item.level] : [])];
    const example = primaryExample(item);
    const maskable = example ? maskTerm(example.jp, item.term) !== null : false;

    if (wantKinds.has('recog')) {
      cards.push({ id: `${item.id}::recog`, kind: 'recog', chapterId: item.chapterId, itemId: item.id, tags });
    }
    if (wantKinds.has('prod') && item.meaning) {
      cards.push({ id: `${item.id}::prod`, kind: 'prod', chapterId: item.chapterId, itemId: item.id, tags });
    }
    if (wantKinds.has('context') && maskable) {
      cards.push({ id: `${item.id}::context`, kind: 'context', chapterId: item.chapterId, itemId: item.id, tags });
    }
    if (wantKinds.has('listen')) {
      cards.push({ id: `${item.id}::listen`, kind: 'listen', chapterId: item.chapterId, itemId: item.id, tags });
    }
  }

  if (wantKinds.has('phrase')) {
    for (const fragment of fragments) {
      if (!wantChapters.has(fragment.chapterId)) continue;
      if (!fragment.translation) continue;
      cards.push({
        id: `frag:${fragment.id}::phrase`,
        kind: 'phrase',
        chapterId: fragment.chapterId,
        fragmentId: fragment.id,
        tags: [fragment.chapterId, 'phrase'],
      });
    }
  }

  return cards;
}

export function cardKeyTerms(fragment: Fragment): Item[] {
  return fragment.itemKeys.map((k) => itemById.get(k)).filter((x): x is Item => Boolean(x));
}

export function stats() {
  const byChapter = chapters.map((c) => ({
    chapter: c,
    items: c.itemKeys.length,
    fragments: c.fragmentIds.length,
  }));
  const byLevel: Record<string, number> = {};
  const byKind: Record<string, number> = {};
  for (const item of items) {
    byLevel[item.level || '—'] = (byLevel[item.level || '—'] ?? 0) + 1;
    byKind[item.kind] = (byKind[item.kind] ?? 0) + 1;
  }
  return { byChapter, byLevel, byKind, totalItems: items.length, totalFragments: fragments.length };
}
