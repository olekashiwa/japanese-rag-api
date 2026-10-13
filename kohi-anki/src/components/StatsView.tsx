import { useMemo } from 'react';
import type { Chapter, CardDef, DeckSettings, Progress } from '../types';
import { CARD_KIND_LABELS, CHAPTER_LABELS, chapters, stats } from '../lib/dataset';
import { isNew, retention } from '../lib/srs';
import type { CardKind } from '../types';

interface Props {
  progress: Progress;
  cards: CardDef[];
  setProgress: (updater: (previous: Progress) => Progress) => void;
  settings: DeckSettings;
  onSettingsChange: (patch: Partial<DeckSettings>) => void;
  onReset: () => void;
}

const ALL_CARD_KINDS: CardKind[] = ['recog', 'prod', 'context', 'listen', 'phrase'];

export function StatsView({ progress, cards, setProgress, settings, onSettingsChange, onReset }: Props) {
  const overview = useMemo(() => stats(), []);
  const states = cards.map((card) => progress.cards[card.id]);
  const learned = states.filter((s) => s && s.reps > 0).length;
  const due = states.filter((s) => s && s.reps > 0 && s.due <= Date.now()).length;
  const fresh = states.filter((s) => isNew(s)).length;
  const retentionRate = retention(states.filter(Boolean) as NonNullable<typeof states[number]>[]);

  const perChapter = chapters.map((chapter) => {
    const chapterCards = cards.filter((c) => c.chapterId === chapter.id);
    const done = chapterCards.filter((c) => progress.cards[c.id]?.reps).length;
    return { chapter, total: chapterCards.length, done };
  });

  const week = useMemo(() => {
    const out: { day: string; count: number }[] = [];
    for (let i = 6; i >= 0; i -= 1) {
      const date = new Date(Date.now() - i * 24 * 60 * 60 * 1000);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
      out.push({ day: key.slice(5), count: progress.reviewsByDay[key] ?? 0 });
    }
    return out;
  }, [progress.reviewsByDay]);

  const maxWeek = Math.max(1, ...week.map((w) => w.count));

  return (
    <section className="panel">
      <h2>Статистика и настройки</h2>
      <div className="stat-cards">
        <Stat label="Карточек в наборе" value={cards.length} />
        <Stat label="Изучается" value={learned} />
        <Stat label="К повторению" value={due} />
        <Stat label="Новых" value={fresh} />
        <Stat label="Удержание" value={`${Math.round(retentionRate * 100)}%`} />
        <Stat label="Серия дней" value={progress.streak.days} />
      </div>

      <h3>Повторения за неделю</h3>
      <div className="bars">
        {week.map((w) => (
          <div key={w.day} className="bar">
            <div className="bar-fill" style={{ height: `${(w.count / maxWeek) * 100}%` }} />
            <span className="bar-label">{w.day}</span>
            <span className="bar-value">{w.count}</span>
          </div>
        ))}
      </div>

      <h3>Прогресс по главам</h3>
      <table className="word-table">
        <thead>
          <tr>
            <th>Глава</th>
            <th>Карточек</th>
            <th>Пройдено</th>
            <th>Прогресс</th>
          </tr>
        </thead>
        <tbody>
          {perChapter.map(({ chapter, total, done }) => (
            <tr key={chapter.id}>
              <td>{CHAPTER_LABELS[chapter.id]}</td>
              <td>{total}</td>
              <td>{done}</td>
              <td>
                <ProgressBar value={total ? done / total : 0} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Материал базы</h3>
      <p className="muted">
        {overview.totalFragments} фрагментов текста · {overview.totalItems} словарных единиц ·{' '}
        {Object.entries(overview.byKind).map(([kind, count]) => `${kind}: ${count}`).join(' · ')}
      </p>
      <p className="muted">Уровни: {Object.entries(overview.byLevel).map(([level, count]) => `${level}: ${count}`).join(' · ')}</p>

      <h3>Настройки занятий</h3>
      <div className="settings-grid">
        <label className="field">
          <span>Новых карточек в день</span>
          <input
            type="number"
            min={0}
            max={200}
            value={settings.newPerDay}
            onChange={(e) => onSettingsChange({ newPerDay: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Повторений за сессию</span>
          <input
            type="number"
            min={10}
            max={1000}
            value={settings.maxReviews}
            onChange={(e) => onSettingsChange({ maxReviews: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Скорость озвучки</span>
          <input
            type="range"
            min={0.5}
            max={1.4}
            step={0.05}
            value={settings.ttsRate}
            onChange={(e) => onSettingsChange({ ttsRate: Number(e.target.value) })}
          />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={settings.autoPlayAudio} onChange={(e) => onSettingsChange({ autoPlayAudio: e.target.checked })} />
          озвучивать карточку автоматически
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={settings.showRomaji} onChange={(e) => onSettingsChange({ showRomaji: e.target.checked })} />
          показывать ромадзи
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={settings.typingMode} onChange={(e) => onSettingsChange({ typingMode: e.target.checked })} />
          ввод ответа с клавиатуры (карточки «в контексте»)
        </label>
      </div>

      <h3>Типы карточек</h3>
      <div className="chips">
        {ALL_CARD_KINDS.map((kind) => (
          <label key={kind} className="checkbox chip-checkbox">
            <input
              type="checkbox"
              checked={settings.cardKinds.includes(kind)}
              onChange={(e) =>
                onSettingsChange({
                  cardKinds: e.target.checked ? [...settings.cardKinds, kind] : settings.cardKinds.filter((k) => k !== kind),
                })
              }
            />
            {CARD_KIND_LABELS[kind]}
          </label>
        ))}
      </div>

      <h3>Главы в наборе</h3>
      <div className="chips">
        {chapters.map((chapter: Chapter) => (
          <label key={chapter.id} className="checkbox chip-checkbox">
            <input
              type="checkbox"
              checked={settings.chapterIds.includes(chapter.id)}
              onChange={(e) =>
                onSettingsChange({
                  chapterIds: e.target.checked ? [...settings.chapterIds, chapter.id] : settings.chapterIds.filter((id) => id !== chapter.id),
                })
              }
            />
            {CHAPTER_LABELS[chapter.id]}
          </label>
        ))}
      </div>

      <div className="row">
        <button onClick={() => setProgress((p) => ({ ...p, selection: [] }))}>Очистить выбранные слова</button>
        <button className="danger" onClick={onReset}>
          Сбросить весь прогресс
        </button>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress">
      <div className="progress-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      <span>{Math.round(value * 100)}%</span>
    </div>
  );
}
