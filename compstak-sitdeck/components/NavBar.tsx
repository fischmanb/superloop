export default function NavBar() {
  return (
    <header
      style={{
        height: "48px",
        backgroundColor: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        gap: "16px",
        flexShrink: 0,
      }}
    >
      <span
        style={{
          fontWeight: 700,
          fontSize: "14px",
          letterSpacing: "0.05em",
          color: "var(--color-primary)",
        }}
      >
        COMPSTAK SITDECK
      </span>
      <span
        style={{
          marginLeft: "auto",
          fontSize: "12px",
          color: "var(--color-text-secondary)",
        }}
      >
        CRE Intelligence Dashboard
      </span>
    </header>
  );
}
