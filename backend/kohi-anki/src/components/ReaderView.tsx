import { useState } from 'react';
import type { DeckSettings } from '../types';
import { CHAPTER_LABELS, chapters, fragmentsOfChapter, itemsOfChapter } from '../lib/dataset';
import { speak } from '../lib/tts';

interface Props {
  settings: DeckSettings;
}

export function ReaderView({ settings }: Props) {
  const [chapterId, setChapterId] = useState(chapters[0]?.id ?? 'prologue');
  const [showRomaji, setShowRomaji] = useState(settings.showRomaji);
  const [showTranslation, setShowTranslation] = useState(true);
  const [openNotes, setOpenNotes] = useState(true);

  const chapter = chapters.find((c) => c.id === chapterId);
  const fragments = fragmentsOfChapter(chapterId);
  const chapterItems = itemsOfChapter(chapterId);

  return (
    <section className="panel">
      <div className="filters">
        <select value={chapterId} onChange={(e) => setChapterId(e.target.value)}>
          {chapters.map((c) => (
            <option key={c.id} value={c.id}>
              {CHAPTER_LABELS[c.id]}
            </option>
          ))}
        </select>
        <label className="checkbox">
          <input type="checkbox" checked={showRomaji} onChange={(e) => setShowRomaji(e.target.checked)} /> ромадзи
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={showTranslation} onChange={(e) => setShowTranslation(e.target.checked)} /> перевод
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={openNotes} onChange={(e) => setOpenNotes(e.target.checked)} /> комментарии
        </label>
        <span className="muted">
          {chapter ? `${fragments.length} фрагментов · ${chapterItems.length} словарных единиц` : ''}
        </span>
      </div>

      <div className="reader">
        {fragments.map((fragment) => {
          const fragmentItems = fragment.itemKeys
            .map((key) => chapterItems.find((i) => i.id === key))
            .filter((x): x is NonNullable<typeof x> => Boolean(x));
          return (
            <article key={fragment.id} className="fragment">
              <header>
                <span className="badge">{fragment.id}</span>
                <span className="muted">{fragment.heading}</span>
                <button
                  className="icon-button"
                  title="Прослушать"
                  onClick={() => speak(fragment.original, { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI })}
                >
                  🔈
                </button>
              </header>
              <div className="jp-text">{fragment.original}</div>
              {showRomaji && fragment.romaji ? <div className="romaji-line">{fragment.romaji}</div> : null}
              {showTranslation && fragment.translation ? <div className="translation">{fragment.translation}</div> : null}
              {fragmentItems.length ? (
                <div className="chips">
                  {fragmentItems.map((item) => (
                    <button
                      key={item.id}
                      className="chip"
                      title={item.meaning}
                      onClick={() => speak(item.term, { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI })}
                    >
                      {item.term}
                      {item.readingKana ? <span className="chip-reading">{item.readingKana}</span> : null}
                    </button>
                  ))}
                </div>
              ) : null}
              {openNotes && fragment.notes.length ? (
                <ul className="notes">
                  {fragment.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
