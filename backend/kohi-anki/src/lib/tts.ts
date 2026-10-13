/** Озвучка через встроенный синтез речи браузера (Web Speech API). */

let cachedVoices: SpeechSynthesisVoice[] = [];

export function ttsSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function japaneseVoices(): SpeechSynthesisVoice[] {
  if (!ttsSupported()) return [];
  const all = window.speechSynthesis.getVoices();
  if (all.length) cachedVoices = all;
  const ja = cachedVoices.filter((v) => v.lang.toLowerCase().startsWith('ja'));
  return ja.length ? ja : cachedVoices.filter((v) => v.lang.toLowerCase().includes('jp'));
}

export function onVoicesChanged(cb: () => void): () => void {
  if (!ttsSupported()) return () => {};
  const handler = () => {
    cachedVoices = window.speechSynthesis.getVoices();
    cb();
  };
  window.speechSynthesis.addEventListener('voiceschanged', handler);
  // Safari/iOS отдаёт голоса не сразу — подстрахуемся таймером.
  const timer = window.setTimeout(handler, 600);
  return () => {
    window.speechSynthesis.removeEventListener('voiceschanged', handler);
    window.clearTimeout(timer);
  };
}

export interface SpeakOptions {
  rate?: number;
  voiceURI?: string;
  pitch?: number;
}

export function speak(text: string, options: SpeakOptions = {}): boolean {
  if (!ttsSupported() || !text.trim()) return false;
  const synth = window.speechSynthesis;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'ja-JP';
  utterance.rate = options.rate ?? 0.95;
  utterance.pitch = options.pitch ?? 1;
  const voices = japaneseVoices();
  const chosen = options.voiceURI ? voices.find((v) => v.voiceURI === options.voiceURI) : undefined;
  if (chosen) utterance.voice = chosen;
  else if (voices.length) utterance.voice = voices[0];
  synth.speak(utterance);
  return true;
}

export function stopSpeaking(): void {
  if (ttsSupported()) window.speechSynthesis.cancel();
}
