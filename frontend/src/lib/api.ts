// Client-side API helpers. All calls go through Next.js rewrites (/api/*)
// which proxy to the FastAPI backend - see next.config.ts.

export interface StockBase {
  ticker: string;
  sector: string;
  sleeve: string;
  last_price: number;
  mom_12m: number | null;
  ratio_52w: number | null;
  rsi: number | null;
  volatility: number | null;
  sentiment_score?: number | null;
  ai_score: number;
  value_score?: number | null;
  action: "BUY" | "HOLD" | "AVOID";
  under_radar?: boolean;
  confidence_pct?: number;
  // fundamentals etc. come through with unknown extra keys
  pe_forward?: number | null;
  roe?: number | null;
  gross_margin?: number | null;
  debt_equity?: number | null;
}

export interface Stock extends StockBase {
  price_trend: number[];
  [key: string]: unknown;
}

export interface ScreenerResponse {
  as_of: string;
  count: number;
  stocks: Stock[];
}

export interface StockDetail extends StockBase {
  as_of: string;
  prices: { dates: string[]; close: number[] };
}

export interface Position {
  ticker: string;
  t212_ticker: string;
  quantity: number | null;
  average_price: number | null;
  current_price: number | null;
  ppl: number | null;
  ai_score: number | null;
  action: string | null;
  in_universe: boolean;
}

export interface PortfolioResponse {
  connected: boolean;
  message?: string;
  as_of?: string;
  positions?: Position[];
}

export interface Meta {
  as_of: string;
  sleeves: string[];
  sectors: string[];
  buy: number;
  hold: number;
  avoid: number;
  avg_score: number;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} failed (${r.status})`);
  return r.json();
}

export const fetchScreener = () => get<ScreenerResponse>("/api/screener");
export const fetchMeta = () => get<Meta>("/api/meta");
export const fetchStock = (t: string) => get<StockDetail>(`/api/stock/${t}`);
export const fetchPortfolio = () => get<PortfolioResponse>("/api/portfolio");

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? "-" : `${(v * 100).toFixed(digits)}%`;

export const fmtNum = (v: number | null | undefined, digits = 2) =>
  v == null ? "-" : v.toFixed(digits);
