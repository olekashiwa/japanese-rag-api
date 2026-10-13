import { useMemo, useState } from 'react';
import type { Progress } from '../types';
import { CHAPTER_LABELS, chapters } from '../lib/dataset';
import {
  ANKI_IMPORT_STEPS,
  buildCsv,
  buildDeckJson,
  buildTsv,
  describeSelection,
  type ExportSelection,
} from '../lib/ankiExport';
import { downloadFile } from '../lib/storage';

interface Props {
  progress: Progress;
}

type Scope = 'all' | 'chapters' | 'selection' | 'leeches';

export function ExportView({ progress }: Props) {
  const [scope, setScope] = useState<Scope>('all');
  const [withColumns, setWithColumns] = useState(true);
  const [includePhrases, setIncludePhrases] = useState(true);
  const [chosen, setChosen] = useState<string[]>(chapters.map((c) => c.id));

  const selection: ExportSelection = useMemo(() => {
    if (scope === 'all') return { chapterIds: chapters.map((c) => c.id) };
    if (scope === 'chapters') return { chapterIds: chosen };
    if (scope === 'selection') return { chapterIds: chapters.map((c) => c.id), onlyCardIds: progress.selection };
    const leeches = Object.entries(progress.cards)
      .filter(([, state]) => state.againCount >= 3 || state.lapses >= 2)
      .map(([id]) => id.split('::')[0]);
    return { chapterIds: chapters.map((c) => c.id), onlyCardIds: Array.from(new Set(leeches)) };
  }, [chosen, progress.cards, progress.selection, scope]);

  const counts = describeSelection(selection);
  const tsv = useMemo(() => buildTsv(selection, { withNotetypeDeckColumns: withColumns, includePhrases }), [includePhrases, selection, withColumns]);
  const preview = tsv.split('\n').slice(0, 8).join('\n');

  const stamp = new Date().toISOString().slice(0, 10);

  return (
    <section className="panel">
      <h2>Экспорт в Anki</h2>
      <p className="muted">
        Файл формируется в браузере из тех же данных, что и тренажёр: слова, грамматика, звукоподражания и фразы романа с чтением,
        переводом и контекстом.
      </p>

      <div className="export-grid">
        <label className="field">
          <span>Что выгружаем</span>
          <select value={scope} onChange={(e) => setScope(e.target.value as Scope)}>
            <option value="all">Всё (пролог и все главы)</option>
            <option value="chapters">Только выбранные главы</option>
            <option value="selection">Отмеченные в «Обзоре» ({progress.selection.length})</option>
            <option value="leeches">Трудные карточки (оценка «Снова» 3+ раз)</option>
          </select>
        </label>

        <label className="checkbox">
          <input type="checkbox" checked={withColumns} onChange={(e) => setWithColumns(e.target.checked)} />
          колонки Notetype/Deck (Anki создаст тип заметки и колоду сам)
        </label>

        <label className="checkbox">
          <input type="checkbox" checked={includePhrases} onChange={(e) => setIncludePhrases(e.target.checked)} />
          добавить фразы из романа (118 предложений)
        </label>
      </div>

      {scope === 'chapters' ? (
        <div className="chips">
          {chapters.map((c) => (
            <label key={c.id} className="checkbox chip-checkbox">
              <input
                type="checkbox"
                checked={chosen.includes(c.id)}
                onChange={(e) => setChosen((prev) => (e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)))}
              />
              {CHAPTER_LABELS[c.id]}
            </label>
          ))}
        </div>
      ) : null}

      <div className="row space-between">
        <div>
          К выгрузке: <b>{counts.vocab}</b> заметок «Kohi Novel Card» и <b>{counts.phrases}</b> заметок «Kohi Novel Phrase»
          {counts.cards ? (
            <span className="muted">
              {' '}
              · карточек в Anki: {counts.cards} (распознавание {counts.vocab}, воспроизведение {counts.vocab}, контекст{' '}
              {counts.context}, фразы {counts.phrases})
            </span>
          ) : null}
        </div>
        <div className="row">
          <button
            className="primary"
            onClick={() => downloadFile(`kohi-anki-${stamp}.txt`, tsv)}
            disabled={!counts.vocab && !counts.phrases}
          >
            ⬇ Anki: карточки (TSV)
          </button>
          <button onClick={() => downloadFile(`kohi-anki-${stamp}.csv`, buildCsv(selection), 'text/csv;charset=utf-8')}>
            ⬇ CSV
          </button>
          <button onClick={() => downloadFile(`kohi-deck-${stamp}.json`, buildDeckJson(selection), 'application/json')}>
            ⬇ JSON для .apkg
          </button>
        </div>
      </div>

      <details open>
        <summary>Предпросмотр файла TSV</summary>
        <pre className="preview">{preview}</pre>
      </details>

      <details>
        <summary>Как импортировать в Anki</summary>
        <ol className="steps">
          {ANKI_IMPORT_STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <p className="muted">
          Готовая колода с шаблонами карточек (3 шаблона для слов и 1 для фраз, подколоды по главам) собирается скриптом
          <code> tools\build_deck.cmd </code> — он использует Python из установленного Anki и создаёт файл
          <code> anki\kohi_コーヒーが冷めないうちに.apkg</code>, который открывается двойным щелчком.
        </p>
      </details>
    </section>
  );
}
