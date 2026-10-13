import { useMemo, useState } from 'react';
import type { Item, Progress } from '../types';
import { CHAPTER_LABELS, chapters, fragments, items } from '../lib/dataset';
import { speak } from '../lib/tts';
import { formatDelay } from '../lib/srs';

interface Props {
  progress: Progress;
  setProgress: (updater: (previous: Progress) => Progress) => void;
  onStudySelection: (cardIds: string[]) => void;
}

const KIND_FILTERS: { id: string; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'vocab', label: 'Слова' },
  { id: 'grammar', label: 'Грамматика' },
  { id: 'onomatopoeia', label: 'Звукоподражания' },
];

export function BrowseView({ progress, setProgress, onStudySelection }: Props) {
  const [query, setQuery] = useState('');
  const [chapter, setChapter] = useState('all');
  const [kind, setKind] = useState('all');
  const [level, setLevel] = useState('all');
  const [onlySelected, setOnlySelected] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const levels = useMemo(() => Array.from(new Set(items.map((i) => i.level).filter(Boolean))).sort(), []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      if (chapter !== 'all' && item.chapterId !== chapter) return false;
      if (kind !== 'all' && item.kind !== kind) return false;
      if (level !== 'all' && item.level !== level) return false;
      if (onlySelected && !progress.selection.includes(item.id)) return false;
      if (!q) return true;
      const haystack = [item.term, item.readingKana, item.readingRomaji, item.meaning, item.note].join(' ').toLowerCase();
      return haystack.includes(q);
    });
  }, [chapter, kind, level, onlySelected, progress.selection, query]);

  const toggleSelected = (id: string) => {
    setProgress((p) => ({
      ...p,
      selection: p.selection.includes(id) ? p.selection.filter((x) => x !== id) : [...p.selection, id],
    }));
  };

  const selectAllFiltered = () => {
    setProgress((p) => ({ ...p, selection: Array.from(new Set([...p.selection, ...filtered.map((i) => i.id)])) }));
  };

  const clearSelection = () => setProgress((p) => ({ ...p, selection: [] }));

  const stateFor = (item: Item) => {
    const states = [`${item.id}::recog`, `${item.id}::prod`, `${item.id}::context`]
      .map((id) => progress.cards[id])
      .filter(Boolean);
    if (!states.length) return 'новая';
    const next = Math.min(...states.map((s) => s!.due));
    return next <= Date.now() ? 'к повторению' : `через ${formatDelay(next - Date.now())}`;
  };

  return (
    <section className="panel">
      <div className="filters">
        <input placeholder="Поиск: слово, чтение, значение…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select value={chapter} onChange={(e) => setChapter(e.target.value)}>
          <option value="all">Все главы</option>
          {chapters.map((c) => (
            <option key={c.id} value={c.id}>
              {CHAPTER_LABELS[c.id]}
            </option>
          ))}
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KIND_FILTERS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="all">Любой уровень</option>
          {levels.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <label className="checkbox">
          <input type="checkbox" checked={onlySelected} onChange={(e) => setOnlySelected(e.target.checked)} /> только выбранные
        </label>
      </div>

      <div className="row space-between">
        <div className="muted">
          Найдено: <b>{filtered.length}</b> из {items.length} · выбрано: <b>{progress.selection.length}</b>
        </div>
        <div className="row">
          <button onClick={selectAllFiltered}>Выбрать найденные</button>
          <button onClick={clearSelection} disabled={!progress.selection.length}>
            Снять выбор
          </button>
          <button
            className="primary"
            disabled={!progress.selection.length}
            onClick={() => onStudySelection(progress.selection.map((id) => `${id}::recog`))}
          >
            Учить выбранные
          </button>
        </div>
      </div>

      <table className="word-table">
        <thead>
          <tr>
            <th />
            <th>Слово</th>
            <th>Чтение</th>
            <th>Значение</th>
            <th>Уровень</th>
            <th>Глава</th>
            <th>Статус</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {filtered.map((item) => (
            <tr key={item.id} className={progress.selection.includes(item.id) ? 'selected' : ''}>
              <td>
                <input type="checkbox" checked={progress.selection.includes(item.id)} onChange={() => toggleSelected(item.id)} />
              </td>
              <td className="term-cell">
                {item.term}
                <button className="icon-button" onClick={() => speak(item.term, { rate: progress.settings.ttsRate, voiceURI: progress.settings.ttsVoiceURI })}>
                  🔈
                </button>
              </td>
              <td>{item.readingKana || item.readingRomaji}</td>
              <td>{item.meaning}</td>
              <td>{item.level || '—'}</td>
              <td>{CHAPTER_LABELS[item.chapterId]?.split(' ')[0]}</td>
              <td className="muted">{stateFor(item)}</td>
              <td>
                <button className="link" onClick={() => setExpanded(expanded === item.id ? null : item.id)}>
                  {expanded === item.id ? 'скрыть' : 'контекст'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {expanded ? (
        <div className="detail">
          {(() => {
            const item = items.find((i) => i.id === expanded);
            if (!item) return null;
            return (
              <>
                <h3>
                  {item.term} <span className="muted">{item.readingKana}</span>
                </h3>
                <p>{item.meaning}</p>
                {item.examples.map((example) => (
                  <div key={example.fragmentId} className="example">
                    <div className="jp-text">{example.jp}</div>
                    <div className="romaji-line">{example.romaji}</div>
                    <div className="translation">{example.ru}</div>
                    <div className="muted">
                      {example.fragmentId} · {fragments.find((f) => f.id === example.fragmentId)?.heading}
                    </div>
                  </div>
                ))}
                {item.note ? <p className="note">{item.note}</p> : null}
                <div className="row">
                  <button
                    className="primary"
                    onClick={() => onStudySelection([`${item.id}::recog`, `${item.id}::prod`, `${item.id}::context`])}
                  >
                    Учить эту единицу
                  </button>
                  <button onClick={() => toggleSelected(item.id)}>
                    {progress.selection.includes(item.id) ? 'Убрать из выбранных' : 'Добавить в выбранные'}
                  </button>
                </div>
              </>
            );
          })()}
        </div>
      ) : null}
    </section>
  );
}
