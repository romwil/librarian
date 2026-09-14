export default function LampMark({ className = "brand-mark" }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true" width="28" height="28">
      <path
        fill="currentColor"
        d="M16 3c-1.2 0-2 .8-2 2v1.2c-4.4.8-7.5 3.4-8.2 7.1-.2 1 .6 1.7 1.6 1.7h1.1c.6 4.6 3.8 7.6 7.5 8.6V26h-3c-.6 0-1 .4-1 1s.4 1 1 1h8c.6 0 1-.4 1-1s-.4-1-1-1h-3v-2.4c3.7-1 6.9-4 7.5-8.6h1.1c1 0 1.8-.7 1.6-1.7C25.5 9.6 22.4 7 18 6.2V5c0-1.2-.8-2-2-2zm0 5.2c3.5.6 5.9 2.6 6.4 5.5H9.6C10.1 10.8 12.5 8.8 16 8.2z"
      />
    </svg>
  );
}
