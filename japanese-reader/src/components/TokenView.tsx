import type { Token } from '../types';

interface TokenViewProps {
  token: Token;
  showFurigana?: boolean;
  onClick?: (token: Token) => void;
}

export function TokenView({
  token,
  showFurigana = true,
  onClick,
}: TokenViewProps) {
  return (
    <button
      type="button"
      className={`token ${token.isParticle ? 'token--particle' : ''}`}
      onClick={() => onClick?.(token)}
      aria-label={`${token.surface}${token.reading ? `, ${token.reading}` : ''}`}
    >
      {showFurigana && token.reading ? (
        <ruby>
          {token.surface}
          <rt>{token.reading}</rt>
        </ruby>
      ) : (
        token.surface
      )}
    </button>
  );
}
