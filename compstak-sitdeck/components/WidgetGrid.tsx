"use client";

import dynamic from "next/dynamic";
import { useDeckStore } from "@/lib/store/deck";

// Dynamic import to keep Mapbox client-only (no SSR)
const CREPropertyMap = dynamic(
  () => import("./widgets/CREPropertyMap"),
  { ssr: false }
);

function WidgetRenderer({ widgetType }: { widgetType: string }) {
  switch (widgetType) {
    case "cre-property-map":
      return <CREPropertyMap />;
    default:
      return (
        <div
          style={{
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--color-text-muted)",
            fontSize: "12px",
            backgroundColor: "var(--color-surface)",
            border: "1px dashed var(--color-border)",
          }}
        >
          Widget: {widgetType}
        </div>
      );
  }
}

export default function WidgetGrid() {
  const { activeDeckId, decks } = useDeckStore();
  const deck = decks[activeDeckId];
  const widgets = deck?.widgets ?? [];

  if (widgets.length === 0) {
    return (
      <div
        style={{
          padding: "16px",
          minHeight: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--color-text-muted)",
          fontSize: "14px",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "24px", marginBottom: "8px" }}>+</div>
          <div>Add widgets to your deck</div>
          <div style={{ fontSize: "12px", marginTop: "4px", color: "var(--color-text-muted)" }}>
            Drag and drop to arrange
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "8px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      {widgets.map((widget) => (
        <div
          key={widget.i}
          style={{
            flex: 1,
            minHeight: 0,
            borderRadius: "var(--radius-md)",
            overflow: "hidden",
            border: "1px solid var(--color-border)",
          }}
        >
          <WidgetRenderer widgetType={widget.widgetType} />
        </div>
      ))}
    </div>
  );
}
