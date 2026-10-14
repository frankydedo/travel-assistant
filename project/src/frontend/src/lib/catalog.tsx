import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getCatalog } from "../api/client";
import type { Catalog } from "../api/types";

export interface CatalogLookup {
  catalog: Catalog | null;
  countryName: (code: string) => string;
  airportLabel: (code: string) => string;
  categoryLabel: (code: string) => string;
}

const EMPTY: Catalog = { countries: [], departure_airports: [], categories: [] };

function buildLookup(catalog: Catalog | null): CatalogLookup {
  const c = catalog ?? EMPTY;
  const countries = new Map(c.countries.map((x) => [x.code, x.name]));
  const airports = new Map(c.departure_airports.map((x) => [x.code, `${x.city} ${x.name}`]));
  const categories = new Map(c.categories.map((x) => [x.code, x.label]));
  return {
    catalog,
    countryName: (code) => countries.get(code) ?? code,
    airportLabel: (code) => {
      const label = airports.get(code);
      return label ? `${label} (${code})` : code;
    },
    categoryLabel: (code) => categories.get(code) ?? code,
  };
}

const CatalogContext = createContext<CatalogLookup>(buildLookup(null));

/** Carica il catalogo una sola volta; se fallisce si mostrano i codici grezzi. */
export function CatalogProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => {
    getCatalog().then(setCatalog).catch(() => setCatalog(null));
  }, []);
  const value = useMemo(() => buildLookup(catalog), [catalog]);
  return <CatalogContext.Provider value={value}>{children}</CatalogContext.Provider>;
}

export const useCatalog = (): CatalogLookup => useContext(CatalogContext);
