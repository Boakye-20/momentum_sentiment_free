AI-Driven Equity Screener & Performance Forecasting PlatformAn enterprise-grade quantitative research engine and web platform that combines multi-horizon macro price momentum with programmatic natural language sentiment extraction. Designed to automate equity screening and signal generation across global large-cap universes with zero reliance on costly institutional data feeds.System ArchitectureThe platform is split into two decoupled layers to isolate intensive quantitative math from client-side visualization:Quantitative Analytics Engine (Python Core): Orchestrates data ingestion via yfinance, statistical panel creation (TSM, RSI pullbacks, Moving Average crossovers), and natural language sentiment parsing via VADER and Alpha Vantage.Performance Dashboard (Next.js & Tailwind CSS): A high-performance web interface designed for rapid asset screening, utilizing circular scoring badges, dynamic metrics sorting, and inline vector sparklines to visualize 3-month price/sentiment trends.Technical Features & Signal Matrix1. The Operational Strategy MatrixThe model monitors structural market regimes to protect capital while executing a unique pullback-within-an-uptrend entry mechanism.FactorMetric / IndicatorSystem Entry TargetEngineering LogicTrend Foundation12-Month Return / MA> 5% and above long MAEnsures the asset is in a long-term institutional uptrend.Value Buffer52-Week High CrossoverWithin 25% of highCaptures names with strong market leadership without buying the absolute peak.Pullback EntryRelative Strength (RSI)30 - 50 BandTriggers on healthy technical dips, systematically avoiding asset crashes.Sentiment FilterNLP Momentum OverlayNon-negative composite scoreValidates execution with real-time aggregated news and RSS feeds.2. Engineering Safety Guards (Hard-Won Invariants)No Forward-Looking Data Leakage: Point-in-time calculation constraints ensure that historical backtests strictly evaluate historical data matrices. Future price actions cannot bleed into past scoring frames.Daily Mark-to-Market Evaluation: Portfolio equity curves are re-marked daily before computing Sharpe, Sortino, or Drawdown metrics. Annualizing from low-frequency monthly rebalance windows is hard-blocked to avoid artificial Sharpe inflation.Data Integrity over Fabrication: If historical sentiment data is missing, the engine outputs genuinely neutral values rather than randomized placeholders. Note that neutral means the cross-sectional MEAN, not 0.0: sentiment scores are mildly positive by nature (mean ~+0.17), so zero-filling a gap reads as bad news and penalises any ticker lacking coverage.Quick Start & Local Deployment1. Backend Ingestion & Analytics PipelineBashcd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the core quantitative test suites
python -m pytest tests/

# Execute data ingestion and run local scoring models
python main.py run-pipeline --dev
2. Frontend Next.js Web InterfaceBashcd frontend
npm install
npm run dev  # Launches local development server at http://localhost:3000
Directory Architecture├── backend/
│   ├── config.py             # Global dataclasses, scoring weights, and horizon maps
│   ├── main.py               # Ingestion pipeline routing and orchestration core
│   └── src/
│       ├── data.py           # Multi-source market ingestion, parquet caching layers
│       ├── scoring.py        # Core algorithm logic (Generates AI Score 1-10 & Risk profiles)
│       ├── forecasting.py    # Multi-horizon return forecasts and point-in-time win rates
│       └── av_sentiment.py   # Alpha Vantage historical NLP ingestion engine
├── frontend/
│   ├── src/
│   │   ├── components/       # Next.js interactive UI modules (ScreenerTable, Sparklines)
│   │   └── pages/            # Core views: Active Signals, Performance Heatmaps, Config Panels
└── data/                     # Local price parquet caches & historical sentiment ledger logs
Value Creation & Portfolio Advisory PositioningInstitutional Note for Deal Teams & Portfolio Operations:This architecture demonstrates a practical, high-leverage application of deploying custom AI layers over legacy or messy data footprints to extract operational alpha. By translating raw operational outputs (news text, market trends) into immediate boardroom KPIs (AI Score, Performance Probability Matrix), the application models the exact automated data workflows used to streamline target company due diligence and drive margin efficiency across Private Equity portfolio assets.DisclaimerThis platform is a quantitative research and educational tool. Simulated performance models do not predict actual market results, and financial analytics outputs are provided strictly without warranty. Validate independently before executing live capital allocation strategies.