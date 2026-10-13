/** Экспорт карточек в форматы, которые понимает Anki (TSV/CSV с файловыми заголовками),
 *  а также в JSON для генератора .apkg (tools/build_deck.py). */

import { cardKeyTerms, fragmentById, itemById, items, fragments, maskTerm, splitAroundTerm } from './dataset';
import type { CardDef, Item } from '../types';

export const VOCAB_FIELDS = [
  'Term',
  'Reading',
  'Meaning',
  'Example',
  'ExampleMasked',
  'Translation',
  'Romaji',
  'Chapter',
  'Level',
  'Kind',
  'Note',
  'Source',
] as const;

export const PHRASE_FIELDS = ['Text', 'Romaji', 'Translation', 'Chapter', 'Heading', 'KeyVocab'] as const;

export const VOCAB_NOTETYPE = 'Kohi Novel Card';
export const PHRASE_NOTETYPE = 'Kohi Novel Phrase';
export const ROOT_DECK = 'コーヒーが冷めないうちに';

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Подсвечивает целевое слово в предложении (для экспорта и просмотра). */
export function highlightTerm(sentence: string, term: string): string {
  const parts = splitAroundTerm(sentence, term);
  if (!parts) return escapeHtml(sentence);
  const [before, found, after] = parts;
  return `${escapeHtml(before)}<b class="kohi-term">${escapeHtml(found)}</b>${escapeHtml(after)}`;
}

export function chapterLabel(chapterId: string): string {
  const numbers: Record<string, string> = { prologue: '00 プロローグ', ch1: '01 恋人', ch2: '02 夫婦', ch3: '03 姉妹', ch4: '04 親子' };
  return numbers[chapterId] ?? chapterId;
}

export function deckFor(chapterId: string, kind: 'vocab' | 'grammar' | 'phrase'): string {
  const sub = kind === 'grammar' ? 'Грамматика' : kind === 'phrase' ? 'Фразы' : 'Слова';
  return `${ROOT_DECK}::${chapterLabel(chapterId)}::${sub}`;
}

export function kindGroup(item: Item): 'vocab' | 'grammar' {
  return item.kind === 'grammar' ? 'grammar' : 'vocab';
}

export function tagsFor(item: Item): string[] {
  const tags = ['kohi', item.chapterId, item.kind];
  if (item.level) tags.push(item.level);
  if (item.source === 'analysis') tags.push('из-разбора');
  if (item.readingRomaji && !item.readingKana) tags.push('чтение-проверить');
  return tags;
}

export interface ExportSelection {
  chapterIds: string[];
  /** Если задано — экспортируем только эти элементы (id заметок). */
  onlyCardIds?: string[];
}

function mask(item: Item): string {
  const example = item.examples[0];
  if (!example) return '';
  const masked = maskTerm(example.jp, item.term);
  return masked ? escapeHtml(masked).replace('［　］', '<span class="kohi-blank">［　］</span>') : '';
}

export interface VocabRow {
  notetype: string;
  deck: string;
  fields: string[];
  tags: string[];
}

export interface PhraseRow {
  notetype: string;
  deck: string;
  fields: string[];
  tags: string[];
}

export function buildVocabRows(selection: ExportSelection): VocabRow[] {
  const allowed = selection.onlyCardIds ? new Set(selection.onlyCardIds) : null;
  const wanted = new Set(selection.chapterIds);
  const rows: VocabRow[] = [];
  for (const item of items) {
    if (!wanted.has(item.chapterId)) continue;
    if (allowed && !allowed.has(item.id)) continue;
    const example = item.examples[0];
    rows.push({
      notetype: VOCAB_NOTETYPE,
      deck: deckFor(item.chapterId, kindGroup(item)),
      fields: [
        item.term,
        item.readingKana || item.readingRomaji,
        item.meaning,
        example ? highlightTerm(example.jp, item.term) : '',
        mask(item),
        example ? escapeHtml(example.ru) : '',
        example ? escapeHtml(example.romaji) : '',
        item.chapterId,
        item.level,
        item.kind,
        escapeHtml(item.note),
        item.source,
      ],
      tags: tagsFor(item),
    });
  }
  return rows;
}

export function buildPhraseRows(selection: ExportSelection): PhraseRow[] {
  const wanted = new Set(selection.chapterIds);
  const rows: PhraseRow[] = [];
  for (const fragment of fragments) {
    if (!wanted.has(fragment.chapterId)) continue;
    if (!fragment.translation) continue;
    const keyVocab = cardKeyTerms(fragment)
      .map((i) => `${i.term}${i.readingKana ? `（${i.readingKana}）` : ''} — ${i.meaning}`)
      .join('; ');
    rows.push({
      notetype: PHRASE_NOTETYPE,
      deck: deckFor(fragment.chapterId, 'phrase'),
      fields: [
        escapeHtml(fragment.original),
        escapeHtml(fragment.romaji),
        escapeHtml(fragment.translation),
        fragment.chapterId,
        escapeHtml(fragment.heading),
        escapeHtml(keyVocab),
      ],
      tags: ['kohi', fragment.chapterId, 'phrase'],
    });
  }
  return rows;
}

function tsvCell(value: string): string {
  return value.replace(/\t/g, ' ').replace(/\r?\n/g, '<br>');
}

function csvCell(value: string): string {
  const text = value.replace(/\r?\n/g, ' ');
  return /[",\t]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export interface TsvOptions {
  /** Добавить колонки «тип заметки» и «колода»: Anki создаст их при импорте. */
  withNotetypeDeckColumns: boolean;
  includePhrases: boolean;
}

export function buildTsv(selection: ExportSelection, options: TsvOptions): string {
  const vocab = buildVocabRows(selection);
  const phrases = options.includePhrases ? buildPhraseRows(selection) : [];
  const lines: string[] = ['#separator:tab', '#html:true'];

  if (vocab.length) {
    if (options.withNotetypeDeckColumns) {
      lines.push('#notetype column:1', '#deck column:2', `#tags column:${VOCAB_FIELDS.length + 3}`);
      lines.push(['Notetype', 'Deck', ...VOCAB_FIELDS, 'Tags'].join('\t'));
      for (const row of vocab) {
        lines.push([row.notetype, row.deck, ...row.fields.map(tsvCell), row.tags.join(' ')].join('\t'));
      }
    } else {
      lines.push(`#tags column:${VOCAB_FIELDS.length + 1}`);
      lines.push([...VOCAB_FIELDS, 'Tags'].join('\t'));
      for (const row of vocab) {
        lines.push([...row.fields.map(tsvCell), row.tags.join(' ')].join('\t'));
      }
    }
  }

  if (phrases.length) {
    lines.push('');
    if (options.withNotetypeDeckColumns) {
      lines.push('#notetype column:1', '#deck column:2', `#tags column:${PHRASE_FIELDS.length + 3}`);
      lines.push(['Notetype', 'Deck', ...PHRASE_FIELDS, 'Tags'].join('\t'));
      for (const row of phrases) {
        lines.push([row.notetype, row.deck, ...row.fields.map(tsvCell), row.tags.join(' ')].join('\t'));
      }
    } else {
      lines.push(`#tags column:${PHRASE_FIELDS.length + 1}`);
      lines.push([...PHRASE_FIELDS, 'Tags'].join('\t'));
      for (const row of phrases) {
        lines.push([...row.fields.map(tsvCell), row.tags.join(' ')].join('\t'));
      }
    }
  }

  return lines.join('\n');
}

export function buildCsv(selection: ExportSelection): string {
  const rows: string[][] = [];
  rows.push(['Notetype', 'Deck', ...VOCAB_FIELDS, 'Tags']);
  for (const row of buildVocabRows(selection)) {
    rows.push([row.notetype, row.deck, ...row.fields, row.tags.join(' ')]);
  }
  for (const row of buildPhraseRows(selection)) {
    rows.push([row.notetype, row.deck, ...row.fields, row.tags.join(' ')]);
  }
  return rows.map((r) => r.map(csvCell).join(',')).join('\n');
}

/** JSON-выгрузка выбранных заметок — вход для tools/build_deck.py. */
export function buildDeckJson(selection: ExportSelection): string {
  return JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      root: ROOT_DECK,
      vocab: buildVocabRows(selection).map((r) => ({
        notetype: r.notetype,
        deck: r.deck,
        tags: r.tags,
        fields: Object.fromEntries(VOCAB_FIELDS.map((name, idx) => [name, r.fields[idx] ?? ''])),
      })),
      phrases: buildPhraseRows(selection).map((r) => ({
        notetype: r.notetype,
        deck: r.deck,
        tags: r.tags,
        fields: Object.fromEntries(PHRASE_FIELDS.map((name, idx) => [name, r.fields[idx] ?? ''])),
      })),
    },
    null,
    2,
  );
}

/** Черновик .apkg-инструкции: что делать с выгруженным файлом. */
export const ANKI_IMPORT_STEPS = [
  'Скачайте файл «Anki: карточки (TSV)».',
  'В Anki: Файл → Импорт → выберите файл (кодировка UTF-8 определится сама).',
  'Разделитель — Tab (прописан в заголовке файла), включите «Allow HTML in fields».',
  'Если в файле есть колонки Notetype и Deck — Anki создаст тип заметки и колоду автоматически (Anki 2.1.60+).',
  'Иначе создайте тип заметки с полями в порядке из файла и сопоставьте поля в окне импорта.',
  'Для варианта «одним файлом» запустите tools\\build_deck.cmd — он соберёт готовую колоду .apkg со шаблонами карточек.',
];

export function cardsToItemIds(cards: CardDef[]): string[] {
  return Array.from(new Set(cards.map((c) => c.itemId).filter((x): x is string => Boolean(x))));
}

export function describeSelection(selection: ExportSelection): { vocab: number; phrases: number; context: number; cards: number } {
  const vocabRows = buildVocabRows(selection);
  const phraseRows = buildPhraseRows(selection);
  // Поле ExampleMasked (индекс 4) заполнено ровно тогда, когда есть карточка «в контексте».
  const context = vocabRows.filter((row) => (row.fields[4] ?? '').length > 0).length;
  return {
    vocab: vocabRows.length,
    phrases: phraseRows.length,
    context,
    cards: vocabRows.length * 2 + context + phraseRows.length,
  };
}

export function itemOf(cardId: string): Item | undefined {
  if (!cardId) return undefined;
  const [id] = cardId.split('::');
  return itemById.get(id);
}

export function fragmentOf(cardId: string) {
  const [id] = cardId.split('::');
  return fragmentById.get(id.replace(/^frag:/, '').replace(/^fragment-/, ''));
}
