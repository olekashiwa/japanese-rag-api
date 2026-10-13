import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CardDef, DeckSettings, Grade, Progress } from '../types';
import { CardView } from './CardView';
import { DAY, formatDelay, newState, previewInterval, schedule, todayKey } from '../lib/srs';
import { speak } from '../lib/tts';
import { fragmentById, itemById } from '../lib/dataset';

interface Props {
  progress: Progress;
  setProgress: (updater: (previous: Progress) => Progress) => void;
  cards: CardDef[];
  settings: DeckSettings;
}

interface HistoryEntry {
  cardId: string;
  queue: string[];
  previous: Progress['cards'][string] | undefined;
}

const LEARNING_RETURN = 10 * 60 * 1000;

export function StudyView({ progress, setProgress, cards, settings }: Props) {
  const [queue, setQueue] = useState<string[]>([]);
  const [revealed, setRevealed] = useState(false);
  const [typed, setTyped] = useState('');
  const [session, setSession] = useState({ done: 0, again: 0, good: 0, started: 0 });
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const lastSpoken = useRef<string>('');

  const cardMap = useMemo(() => new Map(cards.map((c) => [c.id, c])), [cards]);

  const startSession = useCallback(() => {
    const stamp = Date.now();
    const dueToday: string[] = [];
    const fresh: string[] = [];
    for (const card of cards) {
      const state = progress.cards[card.id];
      if (!state || state.reps === 0) fresh.push(card.id);
      else if (state.due <= stamp) dueToday.push(card.id);
    }
    dueToday.sort((a, b) => (progress.cards[a]?.due ?? 0) - (progress.cards[b]?.due ?? 0));
    const introducedToday = cards.filter((card) => {
      const state = progress.cards[card.id];
      return state && state.firstSeen && todayKey(state.firstSeen) === todayKey(stamp);
    }).length;
    const freshLimit = Math.max(0, settings.newPerDay - introducedToday);
    const built = [...dueToday.slice(0, settings.maxReviews), ...fresh.slice(0, freshLimit)];
    setQueue(built);
    setHistory([]);
    setRevealed(false);
    setTyped('');
    setSession({ done: 0, again: 0, good: 0, started: built.length });
    setNow(stamp);
  }, [cards, progress.cards, settings.maxReviews, settings.newPerDay]);

  useEffect(() => {
    startSession();
    // Пересобираем очередь при смене набора карточек или настроек.
  }, [startSession]);

  const currentId = queue[0];
  const currentCard = currentId ? cardMap.get(currentId) : undefined;
  const currentState = currentId ? progress.cards[currentId] : undefined;

  const previews = useMemo(() => previewInterval(currentState, now), [currentState, now]);

  useEffect(() => {
    if (!currentCard || !settings.autoPlayAudio || revealed) return;
    if (lastSpoken.current === currentCard.id) return;
    lastSpoken.current = currentCard.id;
    const options = { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI };
    if (currentCard.kind === 'phrase' && currentCard.fragmentId) {
      const fragment = fragmentById.get(currentCard.fragmentId);
      if (fragment) speak(fragment.original, options);
      return;
    }
    const item = currentCard.itemId ? itemById.get(currentCard.itemId) : undefined;
    if (!item) return;
    if (currentCard.kind === 'listen') speak(item.examples[0]?.jp ?? item.term, options);
    else speak(item.term, options);
  }, [currentCard, revealed, settings.autoPlayAudio, settings.ttsRate, settings.ttsVoiceURI]);

  const bumpDay = (progress: Progress, key: string): Progress => {
    const reviewsByDay = { ...progress.reviewsByDay, [key]: (progress.reviewsByDay[key] ?? 0) + 1 };
    let streak = progress.streak;
    if (streak.lastDay !== key) {
      const yesterday = todayKey(Date.now() - DAY);
      streak = { lastDay: key, days: streak.lastDay === yesterday ? streak.days + 1 : 1 };
    }
    return { ...progress, reviewsByDay, streak };
  };

  const grade = useCallback(
    (value: Grade) => {
      if (!currentId) return;
      const stamp = Date.now();
      const previousState = progress.cards[currentId];
      const next = schedule(previousState, value, stamp);
      if (!next.firstSeen) next.firstSeen = stamp;

      setHistory((h) => [...h, { cardId: currentId, queue, previous: previousState }]);
      setProgress((p) => ({ ...bumpDay(p, todayKey(stamp)), cards: { ...p.cards, [currentId]: next } }));

      const rest = queue.slice(1);
      const comesBack = next.due - stamp <= LEARNING_RETURN;
      const updated = comesBack ? [...rest.slice(0, 4), currentId, ...rest.slice(4)] : rest;
      setQueue(updated);
      setRevealed(false);
      setTyped('');
      setNow(stamp);
      setSession((s) => ({ ...s, done: s.done + 1, again: s.again + (value === 'again' ? 1 : 0), good: s.good + (value === 'good' || value === 'easy' ? 1 : 0) }));
    },
    [currentId, progress.cards, queue, setProgress],
  );

  const undo = useCallback(() => {
    setHistory((h) => {
      if (!h.length) return h;
      const entry = h[h.length - 1];
      setProgress((p) => {
        const cards = { ...p.cards };
        if (entry.previous) cards[entry.cardId] = entry.previous;
        else delete cards[entry.cardId];
        return { ...p, cards };
      });
      setQueue(entry.queue);
      setRevealed(false);
      setTyped('');
      setSession((s) => ({ ...s, done: Math.max(0, s.done - 1) }));
      return h.slice(0, -1);
    });
  }, [setProgress]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        if (event.key === 'Enter' && revealed) {
          event.preventDefault();
          grade('good');
        }
        return;
      }
      if (event.code === 'Space' || event.key === 'Enter') {
        event.preventDefault();
        setRevealed(true);
      } else if (event.key === '1') grade('again');
      else if (event.key === '2') grade('hard');
      else if (event.key === '3') grade('good');
      else if (event.key === '4') grade('easy');
      else if (event.key.toLowerCase() === 'z') undo();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [grade, undo, revealed]);

  if (!cards.length) {
    return (
      <section className="panel">
        <h2>Нечего повторять</h2>
        <p>Выберите хотя бы одну главу и тип карточек на вкладке «Настройки».</p>
      </section>
    );
  }

  if (!currentCard) {
    const nextDue = cards
      .map((c) => progress.cards[c.id]?.due)
      .filter((d): d is number => typeof d === 'number' && d > Date.now())
      .sort((a, b) => a - b)[0];
    return (
      <section className="panel session-finished">
        <h2>На сегодня всё 🎉</h2>
        <p>
          Повторено карточек: <b>{session.done}</b>
          {session.done ? ` · «Снова»: ${session.again} · «Хорошо/Легко»: ${session.good}` : ''}
        </p>
        {nextDue ? <p>Следующая карточка будет доступна через {formatDelay(nextDue - Date.now())}.</p> : null}
        <div className="row">
          <button className="primary" onClick={startSession}>
            Проверить ещё раз
          </button>
          <button onClick={() => setProgress((p) => ({ ...p, cards: { ...p.cards, ...Object.fromEntries(queue.map((id) => [id, newState(Date.now())])) } }))}>
            Повторить все сейчас
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="study">
      <div className="study-header">
        <div className="progress-line">
          <span>
            Осталось: <b>{queue.length}</b>
          </span>
          <span>
            Повторено: <b>{session.done}</b>
          </span>
          {currentState ? <span className="muted">интервал: {currentState.interval ? `${currentState.interval} дн` : 'обучение'}</span> : <span className="muted">новая карточка</span>}
        </div>
        <div className="row">
          <button onClick={undo} disabled={!history.length} title="Отменить последнюю оценку (Z)">
            ↩ Отменить
          </button>
          <button onClick={startSession} title="Пересобрать очередь">
            ⟳ Очередь
          </button>
        </div>
      </div>

      <CardView
        card={currentCard}
        revealed={revealed}
        settings={settings}
        typed={typed}
        onTypedChange={settings.typingMode && currentCard.kind === 'context' ? setTyped : undefined}
        onGrade={grade}
        previews={previews}
      />

      {!revealed ? (
        <div className="row center">
          <button className="primary big" onClick={() => setRevealed(true)}>
            Показать ответ <kbd>Space</kbd>
          </button>
        </div>
      ) : (
        <div className="hint center">Оцените себя клавишами 1–4</div>
      )}
    </section>
  );
}
