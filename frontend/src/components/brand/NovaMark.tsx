import { useId } from 'react';

interface NovaMarkProps {
  className?: string;
  title?: string;
}

export function NovaMark({ className = 'h-8 w-8', title }: NovaMarkProps) {
  const instanceId = useId().replace(/:/g, '');
  const leftGradient = `${instanceId}-left`;
  const diagonalGradient = `${instanceId}-diagonal`;
  const rightGradient = `${instanceId}-right`;

  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title && <title>{title}</title>}
      <defs>
        <linearGradient id={leftGradient} x1="15" y1="10" x2="19" y2="50" gradientUnits="userSpaceOnUse">
          <stop stopColor="#67E8F9" />
          <stop offset="1" stopColor="#6366F1" />
        </linearGradient>
        <linearGradient id={diagonalGradient} x1="19" y1="10" x2="51" y2="51" gradientUnits="userSpaceOnUse">
          <stop stopColor="#818CF8" />
          <stop offset="0.55" stopColor="#A78BFA" />
          <stop offset="1" stopColor="#F0ABFC" />
        </linearGradient>
        <linearGradient id={rightGradient} x1="47" y1="15" x2="49" y2="54" gradientUnits="userSpaceOnUse">
          <stop stopColor="#C4B5FD" />
          <stop offset="1" stopColor="#E879F9" />
        </linearGradient>
      </defs>

      <path d="M10 17.5 21.5 10v32.8L10 50.5v-33Z" fill={`url(#${leftGradient})`} />
      <path d="m18.2 12.1 8.9-5.2 27.2 37.5-10.6 7.1-25.5-39.4Z" fill={`url(#${diagonalGradient})`} />
      <path d="m42.5 21.3 11.5-7.5v33.4L42.5 54.8V21.3Z" fill={`url(#${rightGradient})`} />

      <path d="m20.1 14.4 7.2-4.2 25.2 34.6-3.1 2.1-29.3-32.5Z" fill="white" fillOpacity=".22" />
      <path d="M13 19.1 18.5 15.5v25.7L13 45V19.1Z" fill="white" fillOpacity=".13" />
      <path d="m45.5 23 5.5-3.6v26.2l-5.5 3.6V23Z" fill="white" fillOpacity=".1" />
    </svg>
  );
}
