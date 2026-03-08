import { z } from "zod";
import { router, publicProcedure } from "../server";
import { query, initDuckDBViews } from "@/lib/db/duckdb";

const BBoxSchema = z.object({
  swLng: z.number(),
  swLat: z.number(),
  neLng: z.number(),
  neLat: z.number(),
});

const LayersSchema = z.object({
  leases: z.boolean().default(true),
  sales: z.boolean().default(true),
  properties: z.boolean().default(false),
});

const MapQueryInput = z.object({
  market: z.string().optional(),
  propertyTypes: z.array(z.string()).optional(),
  buildingClass: z.string().optional(),
  dateFrom: z.string().optional(),
  dateTo: z.string().optional(),
  bbox: BBoxSchema.optional(),
  layers: LayersSchema.optional(),
  limit: z.number().min(1).max(2000).default(500),
});

export interface LeaseMarker {
  id: string;
  lat: number;
  lng: number;
  address: string;
  market: string;
  propertyType: string;
  buildingClass: string;
  startingRent: number | null;
  sqft: number | null;
  tenantName: string;
  executionDate: string;
}

export interface SaleMarker {
  id: string;
  lat: number;
  lng: number;
  address: string;
  market: string;
  propertyType: string;
  buildingClass: string;
  salePricePSF: number | null;
  capRate: number | null;
  sqft: number | null;
  saleDate: string;
}

export interface PropertyMarker {
  id: string;
  lat: number;
  lng: number;
  address: string;
  market: string;
  propertyType: string;
  buildingClass: string;
  propertyName: string;
  propertySize: number | null;
  startingRentEstimate: number | null;
}

export const mapRouter = router({
  getMarkers: publicProcedure.input(MapQueryInput).query(async ({ input }) => {
    await initDuckDBViews();

    const {
      market,
      propertyTypes,
      buildingClass,
      dateFrom,
      dateTo,
      bbox,
      layers = { leases: true, sales: true, properties: false },
      limit,
    } = input;

    const leaseMarkers: LeaseMarker[] = [];
    const saleMarkers: SaleMarker[] = [];
    const propertyMarkers: PropertyMarker[] = [];

    if (layers.leases) {
      const conditions: string[] = [
        `"Geo Point" IS NOT NULL`,
        `"Geo Point" != ''`,
        `TRY_CAST(split_part("Geo Point", ',', 1) AS DOUBLE) IS NOT NULL`,
        `TRY_CAST(split_part("Geo Point", ',', 2) AS DOUBLE) IS NOT NULL`,
      ];
      const params: (string | number)[] = [];

      if (market) {
        conditions.push(`"Market" = ?`);
        params.push(market);
      }
      if (propertyTypes && propertyTypes.length > 0) {
        conditions.push(`"Property Type" IN (${propertyTypes.map(() => "?").join(",")})`);
        params.push(...propertyTypes);
      }
      if (buildingClass) {
        conditions.push(`"Building Class" = ?`);
        params.push(buildingClass);
      }
      if (dateFrom) {
        conditions.push(`"Execution Date" >= ?`);
        params.push(dateFrom);
      }
      if (dateTo) {
        conditions.push(`"Execution Date" <= ?`);
        params.push(dateTo);
      }
      if (bbox) {
        conditions.push(
          `TRY_CAST(split_part("Geo Point", ',', 1) AS DOUBLE) BETWEEN ? AND ?`
        );
        params.push(bbox.swLat, bbox.neLat);
        conditions.push(
          `TRY_CAST(split_part("Geo Point", ',', 2) AS DOUBLE) BETWEEN ? AND ?`
        );
        params.push(bbox.swLng, bbox.neLng);
      }

      const where = `WHERE ${conditions.join(" AND ")}`;

      const rows = await query<Record<string, unknown>>(
        `SELECT
          COALESCE(CAST("Id" AS VARCHAR), '') AS id,
          COALESCE("Street Address", '') AS address,
          COALESCE("Market", '') AS market,
          COALESCE("Property Type", '') AS property_type,
          COALESCE("Building Class", '') AS building_class,
          TRY_CAST("Starting Rent" AS DOUBLE) AS starting_rent,
          TRY_CAST("Transaction SQFT" AS DOUBLE) AS sqft,
          COALESCE("Tenant Name", '') AS tenant_name,
          COALESCE(CAST("Execution Date" AS VARCHAR), '') AS execution_date,
          TRY_CAST(split_part("Geo Point", ',', 1) AS DOUBLE) AS lat,
          TRY_CAST(split_part("Geo Point", ',', 2) AS DOUBLE) AS lng
        FROM leases
        ${where}
        ORDER BY "Execution Date" DESC NULLS LAST
        LIMIT ${limit}`,
        params
      );

      for (const row of rows) {
        const lat = Number(row.lat);
        const lng = Number(row.lng);
        if (lat && lng && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
          leaseMarkers.push({
            id: String(row.id ?? ""),
            lat,
            lng,
            address: String(row.address ?? ""),
            market: String(row.market ?? ""),
            propertyType: String(row.property_type ?? ""),
            buildingClass: String(row.building_class ?? ""),
            startingRent: row.starting_rent != null ? Number(row.starting_rent) : null,
            sqft: row.sqft != null ? Number(row.sqft) : null,
            tenantName: String(row.tenant_name ?? ""),
            executionDate: String(row.execution_date ?? ""),
          });
        }
      }
    }

    if (layers.sales) {
      const conditions: string[] = [
        `"Geo Point" IS NOT NULL`,
        `"Geo Point" != ''`,
        `TRY_CAST(split_part("Geo Point", ',', 1) AS DOUBLE) IS NOT NULL`,
        `TRY_CAST(split_part("Geo Point", ',', 2) AS DOUBLE) IS NOT NULL`,
      ];
      const params: (string | number)[] = [];

      if (market) {
        conditions.push(`"Market" = ?`);
        params.push(market);
      }
      if (propertyTypes && propertyTypes.length > 0) {
        conditions.push(`"Property Type" IN (${propertyTypes.map(() => "?").join(",")})`);
        params.push(...propertyTypes);
      }
      if (buildingClass) {
        conditions.push(`"Building Class" = ?`);
        params.push(buildingClass);
      }
      if (dateFrom) {
        conditions.push(`"Sale Date" >= ?`);
        params.push(dateFrom);
      }
      if (dateTo) {
        conditions.push(`"Sale Date" <= ?`);
        params.push(dateTo);
      }
      if (bbox) {
        conditions.push(
          `TRY_CAST(split_part("Geo Point", ',', 1) AS DOUBLE) BETWEEN ? AND ?`
        );
        params.push(bbox.swLat, bbox.neLat);
        conditions.push(
          `TRY_CAST(split_part("Geo Point", ',', 2) AS DOUBLE) BETWEEN ? AND ?`
        );
        params.push(bbox.swLng, bbox.neLng);
      }

      const where = `WHERE ${conditions.join(" AND ")}`;

      const rows = await query<Record<string, unknown>>(
        `SELECT
          COALESCE(CAST("ID" AS VARCHAR), '') AS id,
          COALESCE("Street Address", '') AS address,
          COALESCE("Market", '') AS market,
          COALESCE("Property Type", '') AS property_type,
          COALESCE("Building Class", '') AS building_class,
          TRY_CAST("Sale Price (PSF)" AS DOUBLE) AS sale_price_psf,
          TRY_CAST("Cap Rate" AS DOUBLE) AS cap_rate,
          TRY_CAST("Transaction SQFT" AS DOUBLE) AS sqft,
          COALESCE(CAST("Sale Date" AS VARCHAR), '') AS sale_date,
          TRY_CAST(split_part("Geo Point", ',', 1) AS DOUBLE) AS lat,
          TRY_CAST(split_part("Geo Point", ',', 2) AS DOUBLE) AS lng
        FROM sales
        ${where}
        ORDER BY "Sale Date" DESC NULLS LAST
        LIMIT ${limit}`,
        params
      );

      for (const row of rows) {
        const lat = Number(row.lat);
        const lng = Number(row.lng);
        if (lat && lng && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
          saleMarkers.push({
            id: String(row.id ?? ""),
            lat,
            lng,
            address: String(row.address ?? ""),
            market: String(row.market ?? ""),
            propertyType: String(row.property_type ?? ""),
            buildingClass: String(row.building_class ?? ""),
            salePricePSF: row.sale_price_psf != null ? Number(row.sale_price_psf) : null,
            capRate: row.cap_rate != null ? Number(row.cap_rate) : null,
            sqft: row.sqft != null ? Number(row.sqft) : null,
            saleDate: String(row.sale_date ?? ""),
          });
        }
      }
    }

    if (layers.properties) {
      const conditions: string[] = [
        `LATITUDE IS NOT NULL`,
        `LONGITUDE IS NOT NULL`,
        `LATITUDE != 0`,
        `LONGITUDE != 0`,
      ];
      const params: (string | number)[] = [];

      if (market) {
        conditions.push(`MARKET = ?`);
        params.push(market);
      }
      if (propertyTypes && propertyTypes.length > 0) {
        conditions.push(`PROPERTY_TYPE IN (${propertyTypes.map(() => "?").join(",")})`);
        params.push(...propertyTypes);
      }
      if (buildingClass) {
        conditions.push(`BUILDING_CLASS = ?`);
        params.push(buildingClass);
      }
      if (bbox) {
        conditions.push(`LATITUDE BETWEEN ? AND ?`);
        params.push(bbox.swLat, bbox.neLat);
        conditions.push(`LONGITUDE BETWEEN ? AND ?`);
        params.push(bbox.swLng, bbox.neLng);
      }

      const where = `WHERE ${conditions.join(" AND ")}`;

      const rows = await query<Record<string, unknown>>(
        `SELECT
          COALESCE(CAST(ID AS VARCHAR), '') AS id,
          COALESCE(ADDRESS, '') AS address,
          COALESCE(MARKET, '') AS market,
          COALESCE(PROPERTY_TYPE, '') AS property_type,
          COALESCE(BUILDING_CLASS, '') AS building_class,
          COALESCE(PROPERTY_NAME, '') AS property_name,
          TRY_CAST(PROPERTY_SIZE AS DOUBLE) AS property_size,
          TRY_CAST(PROPERTY_MARKET_STARTING_RENT_ESTIMATE AS DOUBLE) AS starting_rent_estimate,
          TRY_CAST(LATITUDE AS DOUBLE) AS lat,
          TRY_CAST(LONGITUDE AS DOUBLE) AS lng
        FROM properties
        ${where}
        LIMIT ${limit}`,
        params
      );

      for (const row of rows) {
        const lat = Number(row.lat);
        const lng = Number(row.lng);
        if (lat && lng && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
          propertyMarkers.push({
            id: String(row.id ?? ""),
            lat,
            lng,
            address: String(row.address ?? ""),
            market: String(row.market ?? ""),
            propertyType: String(row.property_type ?? ""),
            buildingClass: String(row.building_class ?? ""),
            propertyName: String(row.property_name ?? ""),
            propertySize: row.property_size != null ? Number(row.property_size) : null,
            startingRentEstimate:
              row.starting_rent_estimate != null
                ? Number(row.starting_rent_estimate)
                : null,
          });
        }
      }
    }

    return {
      leases: leaseMarkers,
      sales: saleMarkers,
      properties: propertyMarkers,
    };
  }),
});
