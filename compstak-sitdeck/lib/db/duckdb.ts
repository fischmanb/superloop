import path from "path";
import duckdb from "duckdb";

// Persistent DuckDB file — created on first connection
const DB_PATH = path.join(process.cwd(), "data", "sitdeck.duckdb");

// Shared CSV data paths — configure via SITDECK_DATA_DIR env var, or defaults to ~/compstak-sitdeck/_shared-csv-data
const CSV_BASE = process.env.SITDECK_DATA_DIR ?? (() => {
  const home = process.env.HOME;
  if (!home) throw new Error("SITDECK_DATA_DIR env var is not set and HOME is unavailable. Set SITDECK_DATA_DIR to the absolute path of the _shared-csv-data directory.");
  return path.join(home, "compstak-sitdeck/_shared-csv-data");
})();

export const CSV_PATHS = {
  leases: path.join(CSV_BASE, "snowflake-full-leases-2026-03-04.csv"),
  sales: path.join(CSV_BASE, "snowflake-full-sales-2026-03-04.csv"),
  properties: path.join(CSV_BASE, "snowflake-full-properties-2025-03-17.csv"),
} as const;

let _db: duckdb.Database | null = null;

export function getDB(): duckdb.Database {
  if (_db) return _db;
  _db = new duckdb.Database(DB_PATH);
  return _db;
}

export function query<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = []
): Promise<T[]> {
  return new Promise((resolve, reject) => {
    const db = getDB();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (db as any).all(sql, ...params, (err: Error | null, rows: T[]) => {
      if (err) reject(err);
      else resolve(rows);
    });
  });
}

export function run(sql: string, params: unknown[] = []): Promise<void> {
  return new Promise((resolve, reject) => {
    const db = getDB();
    db.run(sql, ...params, (err: Error | null) => {
      if (err) reject(err);
      else resolve();
    });
  });
}

// Register CSV views — called once on server startup
let _viewsInitialized = false;

export async function initDuckDBViews(): Promise<void> {
  if (_viewsInitialized) return;

  const db = getDB();

  await run(`
    CREATE OR REPLACE VIEW leases AS
    SELECT * FROM read_csv_auto('${CSV_PATHS.leases}', header=true, ignore_errors=true)
  `);

  await run(`
    CREATE OR REPLACE VIEW sales AS
    SELECT * FROM read_csv_auto('${CSV_PATHS.sales}', header=true, ignore_errors=true)
  `);

  await run(`
    CREATE OR REPLACE VIEW properties AS
    SELECT * FROM read_csv_auto('${CSV_PATHS.properties}', header=true, ignore_errors=true)
  `);

  _viewsInitialized = true;
}
