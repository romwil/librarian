import LampMark from "./LampMark.jsx";

const SPINES = [
  ["72%", "#4a2c22"],
  ["88%", "#2a3344"],
  ["64%", "#3d4a32"],
  ["94%", "#5a3a1c"],
  ["70%", "#2c2420"],
  ["82%", "#6b3e2a"],
  ["58%", "#1e2a3a"],
  ["90%", "#4a3548"],
  ["76%", "#3a2a18"],
  ["85%", "#243044"],
  ["62%", "#4e3a28"],
  ["96%", "#2f241c"],
  ["68%", "#35402e"],
  ["80%", "#5c2e24"],
  ["74%", "#1c2430"],
  ["91%", "#463218"],
];

export default function GlassDoor({ eyebrow, title, lede, seal, footer, children, testId = "foyer" }) {
  return (
    <div className="foyer" data-testid={testId}>
      <div className="lamp-shaft" aria-hidden="true" />
      <div className="lamp-bulb" aria-hidden="true" />
      <div className="dust" aria-hidden="true" />
      <div className="page-turn" aria-hidden="true" />
      <div className="spines" aria-hidden="true">
        {SPINES.map(([height, color], index) => (
          <div key={index} className="spine" style={{ height, backgroundColor: color }} />
        ))}
      </div>
      <div className="glass">
        <LampMark />
        {seal ? <p className="seal">{seal}</p> : null}
        {eyebrow ? <p className="kicker">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {lede ? <p className="lede">{lede}</p> : null}
        {children}
        {footer ? <div>{footer}</div> : null}
      </div>
    </div>
  );
}
