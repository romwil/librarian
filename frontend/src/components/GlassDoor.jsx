export default function GlassDoor({ eyebrow, title, lede, footer, children, testId = "foyer" }) {
  return (
    <div className="glass-door" data-testid={testId}>
      <div className="glass-door-atmosphere" aria-hidden="true">
        <div className="glass-door-spines" />
        <div className="glass-door-lamp" />
        <div className="glass-door-dust" />
        <div className="glass-door-page" />
        <div className="glass-door-grain" />
      </div>
      <div className="glass-door-card">
        {eyebrow ? <p className="eyebrow glass-door-eyebrow">{eyebrow}</p> : null}
        <h1 className="glass-door-title">{title}</h1>
        {lede ? <p className="login-lede glass-door-lede">{lede}</p> : null}
        {children}
        {footer ? <div className="glass-door-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
