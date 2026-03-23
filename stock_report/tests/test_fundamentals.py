"""Fundamentals connector tests."""

import unittest

from stock_report.connectors.fundamentals import NAVER_MAIN_URL
from stock_report.connectors.fundamentals import STOCKANALYSIS_FINANCIALS_URL
from stock_report.connectors.fundamentals import STOCKANALYSIS_RATIOS_URL
from stock_report.connectors.fundamentals import NaverKoreaFundamentalsClient
from stock_report.connectors.fundamentals import StockAnalysisFundamentalsClient


class StubHttpClient:
    def __init__(self, responses):
        self.responses = responses

    def get_text(self, url, params=None, headers=None):
        key = url
        if params:
            key = (url, tuple(sorted(params.items())))
        return self.responses[key]


class FundamentalsTests(unittest.TestCase):
    def test_stockanalysis_client_parses_metrics(self) -> None:
        client = StockAnalysisFundamentalsClient(
            http_client=StubHttpClient(
                {
                    STOCKANALYSIS_FINANCIALS_URL.format(symbol="nvda"): _stockanalysis_financials_html(),
                    STOCKANALYSIS_RATIOS_URL.format(symbol="nvda"): _stockanalysis_ratios_html(),
                }
            )
        )

        snapshot = client.fetch_fundamentals("NVDA")

        self.assertEqual(snapshot.as_of, "2026-01-25")
        self.assertEqual(snapshot.source, "StockAnalysis")
        self.assertAlmostEqual(snapshot.metrics["revenue_growth"], 65.47, places=2)
        self.assertAlmostEqual(snapshot.metrics["earnings_growth"], 64.75, places=2)
        self.assertAlmostEqual(snapshot.metrics["operating_margin"], 60.38, places=2)
        self.assertAlmostEqual(snapshot.metrics["forward_pe"], 22.05, places=2)
        self.assertAlmostEqual(snapshot.metrics["ev_to_sales"], 20.24, places=2)
        self.assertAlmostEqual(snapshot.metrics["net_debt_to_ebitda"], -0.39, places=2)
        self.assertAlmostEqual(snapshot.metrics["roe"], 86.95, places=2)

    def test_naver_client_parses_metrics(self) -> None:
        client = NaverKoreaFundamentalsClient(
            http_client=StubHttpClient(
                {
                    (NAVER_MAIN_URL, (("code", "005930"),)): _naver_main_html(),
                }
            )
        )

        snapshot = client.fetch_fundamentals("005930.KS")

        self.assertEqual(snapshot.as_of, "2025-12-31")
        self.assertEqual(snapshot.source, "Naver Finance")
        self.assertAlmostEqual(snapshot.metrics["revenue_growth"], 10.88, places=2)
        self.assertAlmostEqual(snapshot.metrics["earnings_growth"], 31.22, places=2)
        self.assertAlmostEqual(snapshot.metrics["operating_margin"], 13.07, places=2)
        self.assertAlmostEqual(snapshot.metrics["roe"], 10.85, places=2)
        self.assertAlmostEqual(snapshot.metrics["forward_pe"], 9.0, places=2)
        self.assertAlmostEqual(snapshot.metrics["quick_ratio"], 1.8327, places=4)
        self.assertAlmostEqual(snapshot.metrics["pbr"], 3.26, places=2)


def _stockanalysis_financials_html() -> str:
    return """
    <html>
      <body>
        data:{statement:"income-statement",financialData:{revenueGrowth:[.65474,.65474],netIncomeGrowth:[.64746,.64746],grossMargin:[.7106808435754708,.7106808435754708],operatingMargin:[.6038168363141272,.6038168363141272]},map:[{id:"revenue"}],details:{lastTrailingDate:"Jan 25, 2026"}}}
      </body>
    </html>
    """


def _stockanalysis_ratios_html() -> str:
    return """
    <html>
      <body>
        data:{statement:"ratios",financialData:{marketCap:[4420899000000],peForward:[22.052522167069704],evrevenue:[20.23616],netdebtebitda:[-.387],currentratio:[3.905263812455306],roe:[.8694521887106702]},map:[{id:"marketCap"}],details:{lastTrailingDate:"Jan 25, 2026",sourceText:"Updated Feb 25, 2026."}}}
      </body>
    </html>
    """


def _naver_main_html() -> str:
    return """
    <html>
      <body>
        <table summary="기업실적분석에 관한표이며 주요재무정보를 최근 연간 실적, 분기 실적에 따라 정보를 제공합니다." class="tb_type1 tb_num tb_type1_ifrs">
          <thead>
            <tr class="t_line">
              <th rowspan="3"><strong>주요재무정보</strong></th>
              <th scope="col" colspan="4"><strong>최근 연간 실적</strong></th>
              <th scope="col" colspan="6"><strong>최근 분기 실적</strong></th>
            </tr>
            <tr>
              <th scope="col">2023.12</th>
              <th scope="col">2024.12</th>
              <th scope="col">2025.12</th>
              <th scope="col">2026.12(E)</th>
              <th scope="col">2024.12</th>
              <th scope="col">2025.03</th>
              <th scope="col">2025.06</th>
              <th scope="col">2025.09</th>
              <th scope="col">2025.12</th>
              <th scope="col">2026.03(E)</th>
            </tr>
            <tr class="b_line">
              <th scope="col"><span>IFRS연결</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row"><strong>매출액</strong></th>
              <td>2,589,355</td>
              <td>3,008,709</td>
              <td>3,336,059</td>
              <td>5,215,749</td>
            </tr>
            <tr>
              <th scope="row"><strong>당기순이익</strong></th>
              <td>154,871</td>
              <td>344,514</td>
              <td>452,068</td>
              <td>1,651,145</td>
            </tr>
            <tr>
              <th scope="row"><strong>영업이익률</strong></th>
              <td>2.54</td>
              <td>10.88</td>
              <td>13.07</td>
              <td>37.77</td>
            </tr>
            <tr>
              <th scope="row"><strong>ROE(지배주주)</strong></th>
              <td>4.15</td>
              <td>9.03</td>
              <td>10.85</td>
              <td>32.84</td>
            </tr>
            <tr>
              <th scope="row"><strong>당좌비율</strong></th>
              <td>189.46</td>
              <td>187.80</td>
              <td>183.27</td>
              <td></td>
            </tr>
          </tbody>
        </table>
        <table summary="PER/EPS 정보" class="per_table">
          <tbody>
            <tr><td><em id="_per">31.76</em><em id="_eps">6,564</em></td></tr>
            <tr><td><em id="_cns_per">9.00</em><em id="_cns_eps">24,341</em></td></tr>
            <tr><td><em id="_pbr">3.26</em></td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """


if __name__ == "__main__":
    unittest.main()
