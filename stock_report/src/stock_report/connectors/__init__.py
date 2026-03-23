"""External data connectors."""

from stock_report.connectors.etf_data import EtfDataClient
from stock_report.connectors.etf_data import EtfSnapshot
from stock_report.connectors.etf_data import StockAnalysisEtfClient
from stock_report.connectors.fundamentals import FundamentalsClient
from stock_report.connectors.fundamentals import FundamentalsSnapshot
from stock_report.connectors.fundamentals import NaverKoreaFundamentalsClient
from stock_report.connectors.fundamentals import StockAnalysisFundamentalsClient
from stock_report.connectors.market_data import MarketDataClient
from stock_report.connectors.market_data import NaverKoreaChartClient
from stock_report.connectors.market_data import StooqUsChartClient
from stock_report.connectors.market_data import YahooChartClient
from stock_report.connectors.news import GoogleNewsClient

__all__ = [
    "EtfDataClient",
    "EtfSnapshot",
    "FundamentalsClient",
    "FundamentalsSnapshot",
    "GoogleNewsClient",
    "MarketDataClient",
    "NaverKoreaFundamentalsClient",
    "NaverKoreaChartClient",
    "StockAnalysisEtfClient",
    "StockAnalysisFundamentalsClient",
    "StooqUsChartClient",
    "YahooChartClient",
]
