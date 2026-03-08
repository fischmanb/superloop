export const dynamic = "force-dynamic";

export default function NotFound() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      <h1 style={{ fontSize: "48px", fontWeight: 700, margin: 0 }}>404</h1>
      <p style={{ margin: 0 }}>Page not found</p>
    </div>
  );
}
