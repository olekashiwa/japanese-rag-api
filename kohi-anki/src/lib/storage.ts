/** Сохранение прогресса и настроек в localStorage. */

import type { CardState, DeckSettings, Progress } from '../types';

const STORAGE_KEY = 'kohi.progress.v1';

export const defaultSettings: DeckSettings = {
  chapterIds: [],
  cardKinds: ['recog', 'prod', 'context', 'phrase'],
  newPerDay: 20,
  maxReviews: 120,
  autoPlayAudio: true,
  ttsRate: 0.95,
  ttsVoiceURI: '',
  showRomaji: false,
  typingMode: false,
  theme: 'dark',
};

export function emptyProgress(): Progress {
  return {
    v: 1,
    cards: {},
    selection: [],
    settings: { ...defaultSettings },
    reviewsByDay: {},
    streak: { lastDay: '', days: 0 },
  };
}

export function loadProgress(): Progress {
  if (typeof localStorage === 'undefined') return emptyProgress();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyProgress();
    const parsed = JSON.parse(raw) as Progress;
    return {
      ...emptyProgress(),
      ...parsed,
      settings: { ...defaultSettings, ...(parsed.settings ?? {}) },
      cards: parsed.cards ?? {},
      selection: parsed.selection ?? [],
      reviewsByDay: parsed.reviewsByDay ?? {},
      streak: parsed.streak ?? { lastDay: '', days: 0 },
    };
  } catch {
    return emptyProgress();
  }
}

export function saveProgress(progress: Progress): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    /* хранилище может быть недоступно (приватный режим) — молча игнорируем */
  }
}

export function clearProgress(): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.removeItem(STORAGE_KEY);
}

export function exportProgress(progress: Progress): string {
  return JSON.stringify(progress, null, 2);
}

export function cardStateOf(progress: Progress, cardId: string): CardState | undefined {
  return progress.cards[cardId];
}

export function downloadFile(filename: string, content: string, mime = 'text/plain;charset=utf-8'): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
