/** Типы данных тренажёра. Соответствуют структуре src/data/novel.json,
 *  которую создаёт tools/parse_sources.py из Markdown-пособия по роману. */

export type ItemKind = 'vocab' | 'grammar' | 'onomatopoeia' | 'phrase';

export interface Example {
  /** Предложение из романа, в котором встречается слово. */
  jp: string;
  /** Полный текст фрагмента (для контекста и читалки). */
  jpFull?: string;
  romaji: string;
  ru: string;
  fragmentId: string;
}

export interface Item {
  id: string;
  kind: ItemKind;
  term: string;
  readingKana: string;
  readingRomaji: string;
  note: string;
  meaning: string;
  level: string;
  pattern: boolean;
  chapterId: string;
  fragmentIds: string[];
  examples: Example[];
  source: string;
  needsReview: boolean;
}

export interface Fragment {
  id: string;
  chapterId: string;
  index: number;
  heading: string;
  original: string;
  romaji: string;
  translation: string;
  notes: string[];
  itemKeys: string[];
}

export interface Chapter {
  id: string;
  number: number;
  titleJp: string;
  titleRu: string;
  fragmentIds: string[];
  itemKeys: string[];
}

export interface Dataset {
  meta: {
    title: string;
    titleRu: string;
    author: string;
    level: string;
    sources: { role: string; file: string; sha1: string; chapters: string[]; fragments: number }[];
    counts: Record<string, number>;
  };
  chapters: Chapter[];
  fragments: Fragment[];
  items: Item[];
  problems: string[];
}

/** Типы карточек, которые генерируются для каждой единицы. */
export type CardKind = 'recog' | 'prod' | 'context' | 'phrase' | 'listen';

export interface CardDef {
  /** Устойчивый идентификатор карточки (используется в прогрессе и в экспорте). */
  id: string;
  kind: CardKind;
  chapterId: string;
  itemId?: string;
  fragmentId?: string;
  tags: string[];
}

export type Grade = 'again' | 'hard' | 'good' | 'easy';

export interface CardState {
  /** Время следующего показа (мс). */
  due: number;
  /** Интервал в днях. */
  interval: number;
  ease: number;
  reps: number;
  lapses: number;
  lastGrade: Grade;
  last: number;
  /** Когда карточка была увидена впервые (для лимита новых карточек в день). */
  firstSeen?: number;
  /** Сколько раз карточка оценена «Снова». */
  againCount: number;
}

export interface DeckSettings {
  chapterIds: string[];
  cardKinds: CardKind[];
  newPerDay: number;
  maxReviews: number;
  autoPlayAudio: boolean;
  ttsRate: number;
  ttsVoiceURI: string;
  showRomaji: boolean;
  typingMode: boolean;
  theme: 'dark' | 'light';
}

export interface Progress {
  v: number;
  cards: Record<string, CardState>;
  selection: string[];
  settings: DeckSettings;
  /** История оценок по дням: '2026-10-05' -> количество. */
  reviewsByDay: Record<string, number>;
  streak: { lastDay: string; days: number };
}
