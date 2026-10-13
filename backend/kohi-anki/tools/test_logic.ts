/** Юнит-проверки планировщика повторений.
 *  Запуск: node tools/test_logic.ts  (Node 24 выполняет TypeScript напрямую) */

import { DAY, MIN, formatDelay, newState, previewInterval, retention, schedule, todayKey } from '../src/lib/srs.ts';
import type { CardState, Grade } from '../src/types.ts';

let failures = 0;

function check(name: string, condition: boolean, detail = ''): void {
  if (condition) {
    console.log(`  ok   ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${name} ${detail}`);
  }
}

const now = 1_700_000_000_000;

console.log('Планировщик повторений');
const first = schedule(undefined, 'good', now);
check('новая карточка уходит в обучение (10 минут)', first.due - now === 10 * MIN, `due-null=${first.due - now}`);
check('интервал «взрослой» карточки ещё не задан', first.interval === 0);
check('отмечено время первого показа', first.firstSeen === now);

const second = schedule(first, 'good', first.due);
check('второй «Хорошо» выпускает из обучения (>= 1 дня)', second.due - first.due >= DAY, `delta=${second.due - first.due}`);

const grown = schedule({ ...newState(now), interval: 10, reps: 3, ease: 2.5 }, 'good', now);
check('«Хорошо» умножает интервал на ease (10 → 25)', grown.interval === 25, `interval=${grown.interval}`);

const hard = schedule({ ...newState(now), interval: 10, reps: 3, ease: 2.5 }, 'hard', now);
check('«Трудно» даёт меньший интервал, чем «Хорошо»', hard.interval < grown.interval, `${hard.interval} < ${grown.interval}`);
check('«Трудно» снижает ease', hard.ease < 2.5, `ease=${hard.ease}`);

const easy = schedule({ ...newState(now), interval: 10, reps: 3, ease: 2.5 }, 'easy', now);
check('«Легко» даёт больший интервал, чем «Хорошо»', easy.interval > grown.interval, `${easy.interval} > ${grown.interval}`);

const again = schedule({ ...newState(now), interval: 10, reps: 3, ease: 2.5 }, 'again', now);
check('«Снова» возвращает карточку через минуту', again.due - now === MIN, `delta=${again.due - now}`);
check('«Снова» сбрасывает интервал и считается провалом', again.interval === 0 && again.lapses === 1, `lapses=${again.lapses}`);

let state: CardState | undefined = undefined;
let stamp = now;
for (let i = 0; i < 30; i += 1) {
  state = schedule(state, 'good', stamp);
  stamp = state.due;
}
check('интервал не превышает год', (state?.interval ?? 0) <= 365, `interval=${state?.interval}`);
check('ease остаётся в допустимых границах', (state?.ease ?? 0) >= 1.3 && (state?.ease ?? 0) <= 2.9, `ease=${state?.ease}`);

const previews = previewInterval(undefined, now);
check('прогноз интервалов содержит все четыре оценки', ['again', 'hard', 'good', 'easy'].every((g) => previews[g as Grade].length > 0));

check('formatDelay: минуты', formatDelay(5 * MIN) === '5 мин', formatDelay(5 * MIN));
check('formatDelay: часы', formatDelay(3 * 60 * MIN) === '3 ч', formatDelay(3 * 60 * MIN));
check('formatDelay: дни', formatDelay(3 * DAY) === '3 дн', formatDelay(3 * DAY));
check('todayKey в формате ГГГГ-ММ-ДД', /^\d{4}-\d{2}-\d{2}$/.test(todayKey(now)), todayKey(now));

const good = schedule({ ...newState(now), reps: 4, interval: 20 }, 'good', now);
const bad = schedule({ ...newState(now), reps: 4, interval: 20 }, 'again', now);
check('удержание считается по последней оценке', Math.abs(retention([good, bad]) - 0.5) < 1e-9, String(retention([good, bad])));

console.log(failures ? `\nПРОВАЛЕНО проверок: ${failures}` : '\nВсе проверки планировщика пройдены');
process.exit(failures ? 1 : 0);
