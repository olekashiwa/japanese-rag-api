import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CardDef, DeckSettings, Progress } from './types';
import { buildCards, chapters, dataset } from './lib/dataset';
import { clearProgress, loadProgress, saveProgress } from './lib/storage';
import { StudyView } from './components/StudyView';
import { BrowseView } from './components/BrowseView';
import { ReaderView } from './components/ReaderView';
import { ExportView } from './components/ExportView';
import { StatsView } from './components/StatsView';

type Tab = 'study' | 'browse' | 'reader' | 'export' | 'stats';

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'study', label: 'Учить', hint: 'Сессия повторений' },
  { id: 'browse', label: 'Обзор', hint: 'Список слов и выбор для колоды' },
  { id: 'reader', label: 'Текст', hint: 'Фрагменты романа с разбором' },
  { id: 'export', label: 'Экспорт в Anki', hint: 'TSV/CSV/JSON для импорта' },
  { id: 'stats', label: 'Статистика', hint: 'Прогресс и настройки' },
];

const TAB_IDS = TABS.map((t) => t.id);

function initialTab(): Tab {
  if (typeof window === 'undefined') return 'study';
  const hash = window.location.hash.replace('#', '') as Tab;
  return TAB_IDS.includes(hash) ? hash : 'study';
}

export default function App() {
  const [progress, setProgressState] = useState<Progress>(() => loadProgress());
  const [tab, setTab] = useState<Tab>(initialTab);
  const [focusCards, setFocusCards] = useState<string[] | null>(null);

  const setProgress = useCallback((updater: (previous: Progress) => Progress) => {
    setProgressState((previous) => updater(previous));
  }, []);

  // Первый запуск: включаем все главы и типы карточек.
  useEffect(() => {
    setProgressState((previous) => {
      if (previous.settings.chapterIds.length) return previous;
      return { ...previous, settings: { ...previous.settings, chapterIds: chapters.map((c) => c.id) } };
    });
  }, []);

  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  useEffect(() => {
    document.documentElement.dataset.theme = progress.settings.theme;
  }, [progress.settings.theme]);

  // Вкладка живёт в адресной строке: на неё можно дать ссылку (#export, #stats…).
  useEffect(() => {
    if (window.location.hash.replace('#', '') !== tab) {
      window.history.replaceState(null, '', `#${tab}`);
    }
  }, [tab]);

  useEffect(() => {
    const onHashChange = () => setTab(initialTab());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const settings = progress.settings;

  const allCards = useMemo(() => buildCards(settings.chapterIds, settings.cardKinds), [settings.cardKinds, settings.chapterIds]);

  const cards: CardDef[] = useMemo(() => {
    if (!focusCards) return allCards;
    const wanted = new Set(focusCards);
    const filtered = allCards.filter((card) => wanted.has(card.id));
    return filtered.length ? filtered : allCards;
  }, [allCards, focusCards]);

  const updateSettings = useCallback(
    (patch: Partial<DeckSettings>) => {
      setFocusCards(null);
      setProgress((previous) => ({ ...previous, settings: { ...previous.settings, ...patch } }));
    },
    [setProgress],
  );

  const reset = useCallback(() => {
    if (!window.confirm('Сбросить прогресс повторений? Настройки сохранятся.')) return;
    const current = progress.settings;
    clearProgress();
    setProgressState({ ...loadProgress(), settings: current });
  }, [progress.settings]);

  const dueNow = cards.filter((card) => {
    const state = progress.cards[card.id];
    return state && state.reps > 0 && state.due <= Date.now();
  }).length;
  const freshCount = cards.filter((card) => !progress.cards[card.id] || progress.cards[card.id].reps === 0).length;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <h1>
            コーヒーが冷めないうちに <span className="muted">· тренажёр слов и фраз</span>
          </h1>
          <div className="muted small">
            {dataset.meta.titleRu} · {dataset.meta.author} · уровень {dataset.meta.level} · издание пособия Japanese for Your Life
          </div>
        </div>
        <div className="counters">
          <span className="counter">
            к повторению <b>{dueNow}</b>
          </span>
          <span className="counter">
            новых <b>{freshCount}</b>
          </span>
          <button
            className="theme-toggle"
            title="Сменить тему"
            onClick={() => updateSettings({ theme: settings.theme === 'dark' ? 'light' : 'dark' })}
          >
            {settings.theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((item) => (
          <button key={item.id} className={tab === item.id ? 'active' : ''} title={item.hint} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>

      <main>
        {tab === 'study' ? (
          <StudyView
            progress={progress}
            setProgress={setProgress}
            cards={cards}
            settings={settings}
          />
        ) : null}
        {tab === 'browse' ? (
          <BrowseView
            progress={progress}
            setProgress={setProgress}
            onStudySelection={(cardIds) => {
              setFocusCards(cardIds);
              setTab('study');
            }}
          />
        ) : null}
        {tab === 'reader' ? <ReaderView settings={settings} /> : null}
        {tab === 'export' ? <ExportView progress={progress} /> : null}
        {tab === 'stats' ? (
          <StatsView
            progress={progress}
            cards={allCards}
            setProgress={setProgress}
            settings={settings}
            onSettingsChange={updateSettings}
            onReset={reset}
          />
        ) : null}
      </main>

      <footer className="app-footer muted small">
        Данные собраны из пособия по роману (tools/parse_sources.py) · колода Anki: tools/build_deck.cmd · прогресс хранится
        локально в браузере
      </footer>
    </div>
  );
}
