import { useMemo } from 'react';
import type { CardDef, DeckSettings, Grade, Item } from '../types';
import { fragmentById, itemById, maskTerm, splitAroundTerm, CHAPTER_LABELS } from '../lib/dataset';
import { speak } from '../lib/tts';

interface Props {
  card: CardDef;
  revealed: boolean;
  settings: DeckSettings;
  typed?: string;
  onTypedChange?: (value: string) => void;
  onGrade?: (grade: Grade) => void;
  previews?: Record<Grade, string>;
}

const KIND_BADGE: Record<string, string> = {
  vocab: 'слово',
  grammar: 'грамматика',
  onomatopoeia: 'звукоподражание',
};

function Reading({ item, settings }: { item: Item; settings: DeckSettings }) {
  const reading = item.readingKana || item.readingRomaji;
  if (!reading) return null;
  return (
    <div className="reading">
      {reading}
      {settings.showRomaji && item.readingRomaji && item.readingRomaji !== reading ? (
        <span className="romaji"> · {item.readingRomaji}</span>
      ) : null}
    </div>
  );
}

function Sentence({ sentence, term, translation }: { sentence: string; term: string; translation?: string }) {
  const parts = splitAroundTerm(sentence, term);
  return (
    <div className="sentence">
      {parts ? (
        <>
          <span>{parts[0]}</span>
          <mark>{parts[1]}</mark>
          <span>{parts[2]}</span>
        </>
      ) : (
        <span>{sentence}</span>
      )}
      {translation ? <div className="translation">{translation}</div> : null}
    </div>
  );
}

export function CardView({ card, revealed, settings, typed = '', onTypedChange, onGrade, previews }: Props) {
  const item = card.itemId ? itemById.get(card.itemId) : undefined;
  const fragment = card.fragmentId ? fragmentById.get(card.fragmentId) : undefined;

  const masked = useMemo(() => {
    if (!item) return null;
    const example = item.examples[0];
    if (!example) return null;
    return maskTerm(example.jp, item.term);
  }, [item]);

  const chapterName = CHAPTER_LABELS[card.chapterId] ?? card.chapterId;

  if (card.kind === 'phrase' && fragment) {
    return (
      <div className="card">
        <div className="card-meta">
          <span className="badge">{chapterName}</span>
          <span className="badge">фраза</span>
        </div>
        <div className="jp-text">
          {fragment.original}
          <button className="icon-button" title="Прослушать" onClick={() => speak(fragment.original, { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI })}>
            🔈
          </button>
        </div>
        {revealed ? (
          <div className="answer">
            <div className="translation big">{fragment.translation}</div>
            {fragment.romaji ? <div className="romaji-line">{fragment.romaji}</div> : null}
            {fragment.notes.length ? (
              <ul className="notes">
                {fragment.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : (
          <div className="hint">Вспомните перевод фразы и нажмите «Показать ответ»</div>
        )}
        <CardFooter revealed={revealed} onGrade={onGrade} previews={previews} showTyping={false} />
      </div>
    );
  }

  if (!item) {
    return <div className="card">Карточка не найдена</div>;
  }

  const example = item.examples[0];
  const meaningHint = [KIND_BADGE[item.kind], item.level].filter(Boolean).join(' · ');

  const front = (() => {
    switch (card.kind) {
      case 'prod':
        return (
          <div className="front">
            <div className="meaning big">{item.meaning}</div>
            <div className="card-meta">
              <span className="badge">{meaningHint}</span>
              {item.note ? <span className="badge">{item.note}</span> : null}
            </div>
          </div>
        );
      case 'context':
        return (
          <div className="front">
            <div className="jp-text masked">{masked ?? example?.jp ?? item.term}</div>
            {onTypedChange ? (
              <input
                className="typed-input"
                value={typed}
                placeholder="Впишите пропущенное слово (можно каной)"
                onChange={(event) => onTypedChange(event.target.value)}
                autoFocus
              />
            ) : null}
          </div>
        );
      case 'listen':
        return (
          <div className="front">
            <button className="listen-button" onClick={() => speak(example?.jp ?? item.term, { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI })}>
              🔈 Прослушать ещё раз
            </button>
            <div className="hint">На слух: что это за слово или фраза?</div>
          </div>
        );
      default:
        return (
          <div className="front">
            <div className="term">
              {item.term}
              <button className="icon-button" title="Прослушать" onClick={() => speak(item.term, { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI })}>
                🔈
              </button>
            </div>
            {example ? <Sentence sentence={example.jp} term={item.term} /> : null}
          </div>
        );
    }
  })();

  const answer = (
    <div className="answer">
      {card.kind !== 'recog' && card.kind !== 'listen' ? (
        <div className="term small">
          {item.term}
          <button className="icon-button" title="Прослушать" onClick={() => speak(item.term, { rate: settings.ttsRate, voiceURI: settings.ttsVoiceURI })}>
            🔈
          </button>
        </div>
      ) : null}
      <Reading item={item} settings={settings} />
      {card.kind !== 'prod' ? <div className="meaning">{item.meaning}</div> : null}
      {card.kind === 'context' || card.kind === 'listen' ? null : example ? (
        <Sentence sentence={example.jp} term={item.term} />
      ) : null}
      {example?.ru ? <div className="translation">{example.ru}</div> : null}
      {example?.romaji && settings.showRomaji ? <div className="romaji-line">{example.romaji}</div> : null}
      {item.note ? <div className="note">{item.note}</div> : null}
      <div className="card-meta">
        <span className="badge">{chapterName}</span>
        {item.fragmentIds.length ? <span className="badge">{item.fragmentIds.join(', ')}</span> : null}
      </div>
    </div>
  );

  return (
    <div className="card">
      {front}
      {revealed ? answer : <div className="hint">Вспомните ответ и нажмите «Показать ответ»</div>}
      <CardFooter
        revealed={revealed}
        onGrade={onGrade}
        previews={previews}
        showTyping={Boolean(onTypedChange) && card.kind === 'context'}
        typed={typed}
        item={item}
      />
    </div>
  );
}

function CardFooter({
  revealed,
  onGrade,
  previews,
  showTyping,
  typed,
  item,
}: {
  revealed: boolean;
  onGrade?: (grade: Grade) => void;
  previews?: Record<Grade, string>;
  showTyping?: boolean;
  typed?: string;
  item?: Item;
}) {
  if (!revealed || !onGrade) return null;
  const normalize = (value: string) => value.replace(/[\s　]/g, '').toLowerCase();
  const typedOk =
    !showTyping || !typed || !item
      ? null
      : normalize(typed) === normalize(item.term) ||
        normalize(typed) === normalize(item.readingKana) ||
        normalize(typed) === normalize(item.readingRomaji);

  return (
    <div className="grade-bar">
      {typedOk !== null ? (
        <div className={typedOk ? 'typed-result ok' : 'typed-result bad'}>
          {typedOk ? 'Верно: ' : 'Ваш ответ: '}
          {typed}
          {typedOk ? '' : ` → ${item?.term}`}
        </div>
      ) : null}
      <div className="grade-buttons">
        {(['again', 'hard', 'good', 'easy'] as Grade[]).map((grade, index) => (
          <button key={grade} className={`grade grade-${grade}`} onClick={() => onGrade(grade)}>
            <span className="grade-label">
              {index + 1}. {grade === 'again' ? 'Снова' : grade === 'hard' ? 'Трудно' : grade === 'good' ? 'Хорошо' : 'Легко'}
            </span>
            {previews ? <span className="grade-preview">{previews[grade]}</span> : null}
          </button>
        ))}
      </div>
    </div>
  );
}
