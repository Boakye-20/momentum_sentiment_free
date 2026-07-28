// Client-side API helpers. All calls go through Next.js rewrites (/api/*)
// which proxy to the FastAPI backend - see next.config.ts.

export interface StockBase {
  ticker: string;
  name?: string;
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
  market_value: number | null;
  opened_at: string | null;
  ppl: number | null;
  signal_weight: number | null;
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
  universe_size: number;
  sleeves: string[];
  sectors: string[];
  signal_count: number;
  gross_long_pct: number;
}

export interface BacktestMetrics {
  total_return_pct: number;
  cagr_pct: number;
  benchmark_cagr_pct: number;
  active_return_pct: number;
  ann_vol_pct: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  max_drawdown_pct: number;
  beta: number;
  alpha_ann_pct: number;
  information_ratio: number;
  n_trades: number;
  win_rate_pct: number;
  avg_trade_pct: number;
  avg_hold_days: number;
}

export interface BacktestTrade {
  ticker: string;
  direction: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  hold_days: number;
}

export interface WalkForwardFold {
  window: string;
  in_cagr: number;
  out_cagr: number;
  out_bench: number;
}

export interface DurationBucket {
  label: string;
  n: number;
  win_rate_pct: number;
  avg_return_pct: number;
}

export interface DurationAnalytics {
  duration_buckets: DurationBucket[];
  time_to_peak: {
    avg_days_to_peak: number;
    median_days_to_peak: number;
    avg_hold_days_winners: number;
    avg_mfe_pct: number;
  };
  drawdown_duration: {
    longest_recovery_days: number;
    avg_recovery_days: number;
    n_drawdowns: number;
    currently_underwater_days: number;
  };
  // [hold_days, return_pct] for every trade; drives the interactive slider.
  hold_returns: [number, number][];
}

export interface BacktestResponse {
  status: "running" | "done" | "error";
  message?: string;
  as_of?: string;
  use_sentiment?: boolean;
  metrics?: BacktestMetrics;
  equity?: { dates: string[]; strategy: number[]; benchmark: number[] };
  walk_forward?: WalkForwardFold[];
  duration?: DurationAnalytics;
  trades?: BacktestTrade[];
}

export const fetchBacktest = (sentiment: boolean) =>
  get<BacktestResponse>(`/api/backtest?sentiment=${sentiment}`);

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CopilotResponse {
  reply: string | null;
  message?: string;
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

export interface SignalPosition {
  ticker: string;
  name?: string;
  sector: string;
  sleeve: string;
  weight_pct: number;
  last_price: number;
  alloc_gbp: number;
  suggested_shares: number;
  mom_12m: number | null;
  ratio_52w: number | null;
  rsi: number | null;
  sentiment_score: number | null;
}

export interface SignalsResponse {
  as_of: string;
  capital: number;
  gross_long_pct: number;
  count: number;
  positions: SignalPosition[];
}

export const fetchSignals = (capital: number) =>
  get<SignalsResponse>(`/api/signals?capital=${capital}`);

export interface JournalTrade {
  id: string | number | null;
  ticker: string;
  t212_ticker: string;
  status: string | null;
  side: "BUY" | "SELL";
  quantity: number | null;
  fill_price: number | null;
  fill_value: number | null;
  date: string | null;
  order_type: string | null;
  signal_weight_at_trade: number | null;
  signal_weight_now: number | null;
  in_universe: boolean;
  is_bot?: boolean;
  raw: Record<string, unknown>;
}

export interface JournalResponse {
  connected: boolean;
  message?: string;
  env?: string;
  as_of?: string;
  count?: number;
  trades?: JournalTrade[];
}

export const fetchJournal = () => get<JournalResponse>("/api/journal");

export async function askCopilot(messages: ChatMessage[]): Promise<CopilotResponse> {
  const r = await fetch("/api/copilot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!r.ok) throw new Error(`/api/copilot failed (${r.status})`);
  return r.json();
}

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? "-" : `${(v * 100).toFixed(digits)}%`;

export const fmtNum = (v: number | null | undefined, digits = 2) =>
  v == null ? "-" : v.toFixed(digits);

// Machine sleeve keys to display labels. Never show raw underscores in the UI.
// Sleeve display order AND labels, kept side by side deliberately: adding a
// sleeve to config.SLEEVES means adding it in these two places and nowhere
// else. Browse derives both its filter chips and its group ordering from
// SLEEVE_ORDER, so a sleeve missing from this list renders its stocks with no
// way to filter to them — which is exactly what happened when the `em` sleeve
// was added and this list still had only four entries.
export const SLEEVE_ORDER: string[] = [
  "core",
  "quality_value",
  "niche_growth",
  "global",
  "em",
];

const SLEEVE_LABELS: Record<string, string> = {
  core: "Core",
  quality_value: "Quality Value",
  niche_growth: "Niche Growth",
  global: "Global",
  em: "Emerging Markets",
};

export const sleeveLabel = (s: string) =>
  SLEEVE_LABELS[s] ??
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
