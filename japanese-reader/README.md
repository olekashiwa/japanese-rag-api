# Japanese Reader MVP

Минимальное React + TypeScript приложение для интерактивного японского текста.

## Запуск

```bash
npm install
npm run dev
```

Откройте URL, который выведет Vite. В демо-режиме фраза `今日は良い天気です。` отображается как набор токенов с фуриганой. Частица `は` выделена красным; клик по слову показывает его свойства.

## Что есть

- `src/App.tsx` — экран MVP и демонстрационные токены
- `src/features/analysis/sentenceSplitter.ts` — разбиение по `。！？`
- `src/components/TokenView.tsx` — интерактивный токен и `<ruby>`/`<rt>`

Токены сейчас заданы вручную. Следующий этап — заменить `demoTokens` результатом `kuromoji.js` в Web Worker.
