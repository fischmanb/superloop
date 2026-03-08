import NavBar from "@/components/NavBar";
import DeckFilterBar from "@/components/DeckFilterBar";
import WidgetGrid from "@/components/WidgetGrid";

export default function DashboardPage() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      <NavBar />
      <DeckFilterBar />
      <main style={{ flex: 1, overflow: "auto" }}>
        <WidgetGrid />
      </main>
    </div>
  );
}
