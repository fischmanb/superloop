"use client";

import { useEffect, useRef, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { trpc } from "@/lib/trpc/client";
import { useDeckStore } from "@/lib/store/deck";

// Mapbox CSS — imported at component level (client-only)
import "mapbox-gl/dist/mapbox-gl.css";

const MARKETS = [
  "New York City",
  "Chicago Metro",
  "Los Angeles - Orange - Inland",
  "Dallas - Ft. Worth",
  "Boston",
  "Bay Area",
  "Washington DC",
  "Houston",
  "Atlanta",
  "Miami - Ft. Lauderdale",
  "Seattle",
  "Denver",
  "Phoenix",
  "Austin",
  "Nashville",
  "Charlotte",
  "Tampa Bay",
  "Philadelphia - Central PA - DE - So. NJ",
  "San Francisco",
  "San Diego",
  "New Jersey - North and Central",
  "Long Island",
  "Westchester and CT",
  "Baltimore",
  "Minneapolis - St. Paul",
  "Portland Metro",
  "Las Vegas",
  "Salt Lake City",
  "Raleigh - Durham",
  "Orlando",
  "San Antonio",
];

const BUILDING_CLASSES = ["A", "B", "C"];

const PROPERTY_TYPES = [
  "Hotel",
  "Industrial",
  "Land",
  "Mixed-Use",
  "Multi-Family",
  "Office",
  "Other",
  "Retail",
];

// NYC default center
const DEFAULT_CENTER: [number, number] = [-74.006, 40.7128];
const DEFAULT_ZOOM = 11;

// Market → approximate center coordinates for auto-pan
const MARKET_CENTERS: Record<string, [number, number]> = {
  "New York City": [-74.006, 40.7128],
  "Chicago Metro": [-87.6298, 41.8781],
  "Los Angeles - Orange - Inland": [-118.2437, 34.0522],
  "Dallas - Ft. Worth": [-96.797, 32.7767],
  "Boston": [-71.0589, 42.3601],
  "Bay Area": [-122.4194, 37.7749],
  "Washington DC": [-77.0369, 38.9072],
  "Houston": [-95.3698, 29.7604],
  "Atlanta": [-84.388, 33.749],
  "Miami - Ft. Lauderdale": [-80.1918, 25.7617],
  "Seattle": [-122.3321, 47.6062],
  "Denver": [-104.9903, 39.7392],
  "Phoenix": [-112.074, 33.4484],
  "Austin": [-97.7431, 30.2672],
  "San Francisco": [-122.4194, 37.7749],
  "San Diego": [-117.1611, 32.7157],
};

function dateRangeToFrom(dateRange: string): string | undefined {
  if (dateRange === "all") return undefined;
  const now = new Date();
  const d = new Date(now);
  if (dateRange === "12mo") d.setFullYear(d.getFullYear() - 1);
  else if (dateRange === "3yr") d.setFullYear(d.getFullYear() - 3);
  else if (dateRange === "5yr") d.setFullYear(d.getFullYear() - 5);
  else return undefined;
  return d.toISOString().split("T")[0];
}

interface BBox {
  swLng: number;
  swLat: number;
  neLng: number;
  neLat: number;
}

interface LayerState {
  leases: boolean;
  sales: boolean;
  properties: boolean;
}

export default function CREPropertyMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapRef = useRef<any>(null);
  const [mapReady, setMapReady] = useState(false);
  const [bbox, setBbox] = useState<BBox | null>(null);
  const [layers, setLayers] = useState<LayerState>({
    leases: true,
    sales: true,
    properties: false,
  });

  // Widget-level filter overrides (empty = use deck-level)
  const [widgetMarket, setWidgetMarket] = useState("");
  const [widgetPropertyType, setWidgetPropertyType] = useState("");
  const [widgetBuildingClass, setWidgetBuildingClass] = useState("");

  const { activeDeckId, decks } = useDeckStore();
  const deckFilters = decks[activeDeckId]?.filters;

  const effectiveMarket = widgetMarket || deckFilters?.market || "New York City";
  const effectivePropertyType = widgetPropertyType || deckFilters?.propertyType || "";
  const effectiveBuildingClass = widgetBuildingClass || deckFilters?.buildingClass || "";
  const effectiveDateRange = deckFilters?.dateRange || "12mo";
  const dateFrom = dateRangeToFrom(effectiveDateRange);

  const { data, isLoading, isFetching } = trpc.map.getMarkers.useQuery(
    {
      market: effectiveMarket || undefined,
      propertyTypes: effectivePropertyType ? [effectivePropertyType] : undefined,
      buildingClass: effectiveBuildingClass || undefined,
      dateFrom,
      bbox: bbox || undefined,
      layers,
      limit: 500,
    },
    {
      enabled: mapReady,
      placeholderData: keepPreviousData,
    }
  );

  const mapboxToken =
    typeof process !== "undefined" ? process.env.NEXT_PUBLIC_MAPBOX_TOKEN : undefined;

  // Initialize Mapbox
  useEffect(() => {
    if (!containerRef.current || mapRef.current || !mapboxToken) return;

    let map: any; // eslint-disable-line @typescript-eslint/no-explicit-any

    import("mapbox-gl").then((mapboxgl) => {
      mapboxgl.default.accessToken = mapboxToken;

      map = new mapboxgl.default.Map({
        container: containerRef.current!,
        style: "mapbox://styles/mapbox/dark-v11",
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
      });

      map.on("load", () => {
        // GeoJSON sources for each layer
        map.addSource("leases-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addSource("sales-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addSource("properties-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        // Lease comps — green circles
        map.addLayer({
          id: "leases-layer",
          type: "circle",
          source: "leases-source",
          paint: {
            "circle-color": "#10b981",
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3, 14, 6],
            "circle-opacity": 0.85,
            "circle-stroke-width": 0.5,
            "circle-stroke-color": "#064e3b",
          },
        });

        // Sales comps — blue circles
        map.addLayer({
          id: "sales-layer",
          type: "circle",
          source: "sales-source",
          paint: {
            "circle-color": "#3b82f6",
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 4, 14, 7],
            "circle-opacity": 0.85,
            "circle-stroke-width": 0.5,
            "circle-stroke-color": "#1e3a8a",
          },
        });

        // Properties — orange circles
        map.addLayer({
          id: "properties-layer",
          type: "circle",
          source: "properties-source",
          layout: { visibility: "none" },
          paint: {
            "circle-color": "#f97316",
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3, 14, 5],
            "circle-opacity": 0.75,
            "circle-stroke-width": 0.5,
            "circle-stroke-color": "#7c2d12",
          },
        });

        setMapReady(true);

        // Set initial bbox
        const bounds = map.getBounds();
        setBbox({
          swLng: bounds.getWest(),
          swLat: bounds.getSouth(),
          neLng: bounds.getEast(),
          neLat: bounds.getNorth(),
        });
      });

      map.on("moveend", () => {
        const bounds = map.getBounds();
        setBbox({
          swLng: bounds.getWest(),
          swLat: bounds.getSouth(),
          neLng: bounds.getEast(),
          neLat: bounds.getNorth(),
        });
      });

      mapRef.current = map;
    });

    return () => {
      if (map) {
        map.remove();
        mapRef.current = null;
        setMapReady(false);
      }
    };
  }, [mapboxToken]);

  // Update GeoJSON sources when data arrives
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !data) return;

    const leasesSource = map.getSource("leases-source");
    if (leasesSource) {
      leasesSource.setData({
        type: "FeatureCollection",
        features: data.leases.map((l: any) => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
          type: "Feature",
          geometry: { type: "Point", coordinates: [l.lng, l.lat] },
          properties: {
            id: l.id,
            address: l.address,
            tenant: l.tenantName,
            rent: l.startingRent ? `$${l.startingRent.toFixed(2)}/sf` : "N/A",
            sqft: l.sqft ? `${l.sqft.toLocaleString()} sf` : "N/A",
            date: l.executionDate,
          },
        })),
      });
    }

    const salesSource = map.getSource("sales-source");
    if (salesSource) {
      salesSource.setData({
        type: "FeatureCollection",
        features: data.sales.map((s: any) => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
          type: "Feature",
          geometry: { type: "Point", coordinates: [s.lng, s.lat] },
          properties: {
            id: s.id,
            address: s.address,
            pricePSF: s.salePricePSF ? `$${s.salePricePSF.toFixed(0)}/sf` : "N/A",
            capRate: s.capRate ? `${s.capRate.toFixed(1)}%` : "N/A",
            sqft: s.sqft ? `${s.sqft.toLocaleString()} sf` : "N/A",
            date: s.saleDate,
          },
        })),
      });
    }

    const propertiesSource = map.getSource("properties-source");
    if (propertiesSource) {
      propertiesSource.setData({
        type: "FeatureCollection",
        features: data.properties.map((p: any) => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
          type: "Feature",
          geometry: { type: "Point", coordinates: [p.lng, p.lat] },
          properties: {
            id: p.id,
            address: p.address,
            name: p.propertyName,
            size: p.propertySize ? `${p.propertySize.toLocaleString()} sf` : "N/A",
            rentEst: p.startingRentEstimate
              ? `$${p.startingRentEstimate.toFixed(2)}/sf`
              : "N/A",
          },
        })),
      });
    }
  }, [data]);

  // Sync layer visibility toggles
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const vis = (on: boolean) => (on ? "visible" : "none");
    if (map.getLayer("leases-layer"))
      map.setLayoutProperty("leases-layer", "visibility", vis(layers.leases));
    if (map.getLayer("sales-layer"))
      map.setLayoutProperty("sales-layer", "visibility", vis(layers.sales));
    if (map.getLayer("properties-layer"))
      map.setLayoutProperty("properties-layer", "visibility", vis(layers.properties));
  }, [layers, mapReady]);

  // Pan map when effective market changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const center = MARKET_CENTERS[effectiveMarket];
    if (center) {
      map.flyTo({ center, zoom: DEFAULT_ZOOM, duration: 800 });
    }
  }, [effectiveMarket, mapReady]);

  const toggleLayer = (layer: keyof LayerState) => {
    setLayers((prev) => ({ ...prev, [layer]: !prev[layer] }));
  };

  if (!mapboxToken) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "var(--color-surface)",
          padding: "24px",
        }}
      >
        <div style={{ textAlign: "center", maxWidth: "360px" }}>
          <div
            style={{
              fontSize: "32px",
              marginBottom: "12px",
              color: "var(--color-text-muted)",
            }}
          >
            🗺
          </div>
          <div
            style={{
              color: "var(--color-text)",
              fontSize: "14px",
              fontWeight: 600,
              marginBottom: "8px",
            }}
          >
            Mapbox token required
          </div>
          <div
            style={{
              color: "var(--color-text-secondary)",
              fontSize: "12px",
              lineHeight: 1.5,
            }}
          >
            Set{" "}
            <code
              style={{
                backgroundColor: "var(--color-surface-elevated)",
                padding: "1px 4px",
                borderRadius: "3px",
              }}
            >
              NEXT_PUBLIC_MAPBOX_TOKEN
            </code>{" "}
            in <code style={{ backgroundColor: "var(--color-surface-elevated)", padding: "1px 4px", borderRadius: "3px" }}>.env.local</code>{" "}
            to enable the CRE Property Map.
          </div>
        </div>
      </div>
    );
  }

  const isEmpty =
    mapReady &&
    !isLoading &&
    data &&
    data.leases.length === 0 &&
    data.sales.length === 0 &&
    data.properties.length === 0;

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: "var(--color-surface)",
        overflow: "hidden",
      }}
    >
      {/* Controls bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 10px",
          backgroundColor: "var(--color-surface-elevated)",
          borderBottom: "1px solid var(--color-border)",
          flexShrink: 0,
          flexWrap: "wrap",
        }}
      >
        {/* Layer toggles */}
        <LayerToggle
          label="Leases"
          color="#10b981"
          active={layers.leases}
          onClick={() => toggleLayer("leases")}
        />
        <LayerToggle
          label="Sales"
          color="#3b82f6"
          active={layers.sales}
          onClick={() => toggleLayer("sales")}
        />
        <LayerToggle
          label="Properties"
          color="#f97316"
          active={layers.properties}
          onClick={() => toggleLayer("properties")}
        />

        <div
          style={{
            width: "1px",
            height: "16px",
            backgroundColor: "var(--color-border)",
            margin: "0 4px",
          }}
        />

        {/* Widget-level market override */}
        <select
          value={widgetMarket}
          onChange={(e) => setWidgetMarket(e.target.value)}
          style={selectStyle}
          title="Widget market filter (overrides deck)"
        >
          <option value="">Market: {effectiveMarket}</option>
          {MARKETS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>

        {/* Property type filter */}
        <select
          value={widgetPropertyType}
          onChange={(e) => setWidgetPropertyType(e.target.value)}
          style={selectStyle}
        >
          <option value="">All Types</option>
          {PROPERTY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        {/* Building class filter */}
        <select
          value={widgetBuildingClass}
          onChange={(e) => setWidgetBuildingClass(e.target.value)}
          style={selectStyle}
        >
          <option value="">All Classes</option>
          {BUILDING_CLASSES.map((c) => (
            <option key={c} value={c}>
              Class {c}
            </option>
          ))}
        </select>
      </div>

      {/* Map container */}
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

        {/* Empty state overlay */}
        {isEmpty && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: "rgba(10,14,26,0.7)",
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                color: "var(--color-text-secondary)",
                fontSize: "13px",
                backgroundColor: "var(--color-surface-elevated)",
                padding: "10px 16px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
              }}
            >
              No records match current filters
            </div>
          </div>
        )}
      </div>

      {/* Status bar */}
      <div
        style={{
          height: "24px",
          display: "flex",
          alignItems: "center",
          padding: "0 10px",
          backgroundColor: "var(--color-surface-elevated)",
          borderTop: "1px solid var(--color-border)",
          fontSize: "11px",
          color: "var(--color-text-muted)",
          flexShrink: 0,
          gap: "12px",
        }}
      >
        {isFetching ? (
          <span style={{ color: "var(--color-accent-blue)" }}>Loading…</span>
        ) : data ? (
          <>
            {layers.leases && (
              <span>
                <span style={{ color: "#10b981", marginRight: "4px" }}>●</span>
                {data.leases.length} leases
              </span>
            )}
            {layers.sales && (
              <span>
                <span style={{ color: "#3b82f6", marginRight: "4px" }}>●</span>
                {data.sales.length} sales
              </span>
            )}
            {layers.properties && (
              <span>
                <span style={{ color: "#f97316", marginRight: "4px" }}>●</span>
                {data.properties.length} properties
              </span>
            )}
            {!layers.leases && !layers.sales && !layers.properties && (
              <span>No layers active</span>
            )}
          </>
        ) : null}
        <span style={{ marginLeft: "auto" }}>
          {effectiveMarket} · {effectiveDateRange}
        </span>
      </div>
    </div>
  );
}

function LayerToggle({
  label,
  color,
  active,
  onClick,
}: {
  label: string;
  color: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "5px",
        padding: "2px 8px",
        borderRadius: "var(--radius-full)",
        border: `1px solid ${active ? color : "var(--color-border)"}`,
        backgroundColor: active ? `${color}20` : "transparent",
        color: active ? color : "var(--color-text-muted)",
        fontSize: "11px",
        fontWeight: 500,
        cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      <span
        style={{
          width: "7px",
          height: "7px",
          borderRadius: "50%",
          backgroundColor: active ? color : "var(--color-text-muted)",
          flexShrink: 0,
        }}
      />
      {label}
    </button>
  );
}

const selectStyle: React.CSSProperties = {
  backgroundColor: "var(--color-surface)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-sm)",
  padding: "2px 6px",
  fontSize: "11px",
  cursor: "pointer",
};
