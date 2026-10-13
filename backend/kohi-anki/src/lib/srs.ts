/** Планировщик повторений: упрощённый SM-2 с шагами обучения.
 *  Чистые функции без обращений к браузеру — легко тестируются. */

import type { CardState, Grade } from '../types';

export const MIN = 60 * 1000;
export const DAY = 24 * 60 * MIN;

export const GRADE_LABELS: Record<Grade, string> = {
  again: 'Снова',
  hard: 'Трудно',
  good: 'Хорошо',
  easy: 'Легко',
};

export const GRADE_HOTKEYS: Record<Grade, string> = {
  again: '1',
  hard: '2',
  good: '3',
  easy: '4',
};

/** Шаг обучения (в минутах) перед выходом в «взрослые» интервалы.
 *  Новая карточка: «Хорошо» → 10 минут, следующее «Хорошо» → 1 день. */
const LEARNING_STEPS = [10];
/** Через сколько минут показать карточку заново после оценки «Снова». */
const RELEARN_DELAY_MIN = 1;
const EASE_MIN = 1.3;
const EASE_MAX = 2.9;
const EASE_START = 2.5;
const MAX_INTERVAL_DAYS = 365;

export function newState(now: number): CardState {
  return { due: now, interval: 0, ease: EASE_START, reps: 0, lapses: 0, lastGrade: 'good', last: 0, againCount: 0 };
}

export function isDue(state: CardState | undefined, now: number): boolean {
  return !state || state.due <= now;
}

export function isNew(state: CardState | undefined): boolean {
  return !state || state.reps === 0;
}

function clampEase(ease: number): number {
  return Math.min(EASE_MAX, Math.max(EASE_MIN, ease));
}

/** Пересчитывает состояние карточки после оценки. */
export function schedule(state: CardState | undefined, grade: Grade, now: number): CardState {
  const prev = state ? { ...state } : newState(now);
  const firstSeen = prev.firstSeen ?? now;
  const learning = prev.reps < LEARNING_STEPS.length && prev.interval <= 0;

  if (grade === 'again') {
    return {
      ...prev,
      firstSeen,
      due: now + RELEARN_DELAY_MIN * MIN,
      interval: 0,
      ease: clampEase(prev.ease - 0.2),
      reps: Math.max(1, prev.reps),
      lapses: prev.reps > 0 ? prev.lapses + 1 : prev.lapses,
      lastGrade: grade,
      last: now,
      againCount: prev.againCount + 1,
    };
  }

  if (learning) {
    if (grade === 'hard') {
      return { ...prev, firstSeen, due: now + LEARNING_STEPS[0] * MIN, interval: 0, ease: clampEase(prev.ease - 0.15), reps: prev.reps + 1, lastGrade: grade, last: now };
    }
    if (grade === 'good') {
      const step = LEARNING_STEPS[Math.min(prev.reps, LEARNING_STEPS.length - 1)];
      return { ...prev, firstSeen, due: now + step * MIN, interval: 0, ease: prev.ease, reps: prev.reps + 1, lastGrade: grade, last: now };
    }
    // easy — сразу выпускаем из обучения
    return { ...prev, firstSeen, due: now + 4 * DAY, interval: 4, ease: clampEase(prev.ease + 0.15), reps: prev.reps + 1, lastGrade: grade, last: now };
  }

  const graduating = prev.interval <= 0;
  const base = Math.max(1, prev.interval || 1);
  let interval: number;
  let ease = prev.ease;

  switch (grade) {
    case 'hard':
      interval = graduating ? 1 : base * 1.2;
      ease = clampEase(ease - 0.15);
      break;
    case 'good':
      interval = graduating ? 1 : base * ease;
      break;
    case 'easy':
      interval = graduating ? 4 : base * ease * 1.35;
      ease = clampEase(ease + 0.15);
      break;
    default:
      interval = base;
  }

  interval = Math.min(MAX_INTERVAL_DAYS, Math.max(1, Math.round(interval)));
  return {
    ...prev,
    firstSeen,
    due: now + interval * DAY,
    interval,
    ease,
    reps: prev.reps + 1,
    lastGrade: grade,
    last: now,
  };
}

/** Человекочитаемый прогноз интервала для кнопки оценки. */
export function previewInterval(state: CardState | undefined, now: number): Record<Grade, string> {
  const grades: Grade[] = ['again', 'hard', 'good', 'easy'];
  const out = {} as Record<Grade, string>;
  for (const g of grades) {
    const next = schedule(state, g, now);
    out[g] = formatDelay(next.due - now);
  }
  return out;
}

export function formatDelay(ms: number): string {
  if (ms < MIN) return 'сейчас';
  if (ms < 60 * MIN) return `${Math.round(ms / MIN)} мин`;
  if (ms < DAY) return `${Math.round(ms / (60 * MIN))} ч`;
  const days = ms / DAY;
  if (days < 30) return `${days < 10 ? days.toFixed(days < 2 ? 1 : 0) : Math.round(days)} дн`;
  const months = days / 30;
  if (months < 12) return `${months.toFixed(1)} мес`;
  return `${(days / 365).toFixed(1)} г`;
}

/** Доля карточек, оценённых «Хорошо» или «Легко» (по последней оценке). */
export function retention(states: CardState[]): number {
  const rated = states.filter((s) => s.reps > 0);
  if (!rated.length) return 0;
  const good = rated.filter((s) => s.lastGrade === 'good' || s.lastGrade === 'easy').length;
  return good / rated.length;
}

export function todayKey(now: number): string {
  const d = new Date(now);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
