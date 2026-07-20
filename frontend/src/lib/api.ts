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
const SLEEVE_LABELS: Record<string, string> = {
  core: "Core",
  quality_value: "Quality Value",
  niche_growth: "Niche Growth",
  global: "Global",
};

export const sleeveLabel = (s: string) =>
  SLEEVE_LABELS[s] ??
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
