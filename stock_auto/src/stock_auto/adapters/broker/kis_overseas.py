from __future__ import annotations

from datetime import date
from typing import Dict, List

from stock_auto.adapters.auth.kis_auth import KISAuthSession


class KISOverseasStockBrokerClient:
    PRESENT_BALANCE_ENDPOINT = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
    OPEN_ORDERS_ENDPOINT = "/uapi/overseas-stock/v1/trading/inquire-nccs"
    ORDER_HISTORY_ENDPOINT = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
    BUYING_POWER_ENDPOINT = "/uapi/overseas-stock/v1/trading/inquire-psamount"
    ORDER_ENDPOINT = "/uapi/overseas-stock/v1/trading/order"
    CANCEL_ENDPOINT = "/uapi/overseas-stock/v1/trading/order-rvsecncl"

    def __init__(self, auth_session: KISAuthSession) -> None:
        self.auth_session = auth_session
        self.credentials = auth_session.credentials

    def get_present_balance(
        self,
        *,
        country_code: str = "840",
        market_code: str = "01",
        currency_division_code: str = "01",
        inquiry_division_code: str = "00",
    ) -> Dict[str, object]:
        response = self.auth_session.request(
            "GET",
            self.PRESENT_BALANCE_ENDPOINT,
            tr_id="CTRP6504R",
            params={
                "CANO": self.credentials.cano,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "WCRC_FRCR_DVSN_CD": currency_division_code,
                "NATN_CD": country_code,
                "TR_MKET_CD": market_code,
                "INQR_DVSN_CD": inquiry_division_code,
            },
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS balance request failed: {response.error_code()} {response.error_message()}"
            )
        return {
            "positions": response.body.get("output1") or [],
            "detail": response.body.get("output2") or [],
            "summary": response.body.get("output3") or [],
            "raw": response.body,
        }

    def list_open_orders(
        self,
        *,
        order_exchange_code: str = "NASD",
        sort_sequence: str = "DS",
    ) -> List[dict]:
        response = self.auth_session.request(
            "GET",
            self.OPEN_ORDERS_ENDPOINT,
            tr_id="TTTS3018R",
            params={
                "CANO": self.credentials.cano,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": order_exchange_code,
                "SORT_SQN": sort_sequence,
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS open orders request failed: {response.error_code()} {response.error_message()}"
            )
        return response.body.get("output") or []

    def inquire_order_history(
        self,
        *,
        order_start_date: date,
        order_end_date: date,
        symbol: str = "%",
        order_exchange_code: str = "NASD",
        side_division: str = "00",
        execution_division: str = "00",
        sort_sequence: str = "DS",
    ) -> List[dict]:
        collected: List[dict] = []
        next_key = ""
        filter_key = ""
        request_symbol = symbol
        request_exchange = order_exchange_code
        request_side = side_division
        request_execution = execution_division

        if self.credentials.env == "demo":
            request_symbol = ""
            request_exchange = ""
            request_side = "00"
            request_execution = "00"

        while True:
            response = self.auth_session.request(
                "GET",
                self.ORDER_HISTORY_ENDPOINT,
                tr_id="TTTS3035R",
                params={
                    "CANO": self.credentials.cano,
                    "ACNT_PRDT_CD": self.credentials.account_product_code,
                    "PDNO": request_symbol,
                    "ORD_STRT_DT": order_start_date.strftime("%Y%m%d"),
                    "ORD_END_DT": order_end_date.strftime("%Y%m%d"),
                    "SLL_BUY_DVSN": request_side,
                    "CCLD_NCCS_DVSN": request_execution,
                    "OVRS_EXCG_CD": request_exchange,
                    "SORT_SQN": sort_sequence,
                    "ORD_DT": "",
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "CTX_AREA_NK200": next_key,
                    "CTX_AREA_FK200": filter_key,
                },
                tr_cont="N" if next_key or filter_key else "",
            )
            if not response.is_ok():
                raise RuntimeError(
                    f"KIS order history request failed: {response.error_code()} {response.error_message()}"
                )

            rows = response.body.get("output") or []
            collected.extend(rows)

            tr_cont = response.headers.get("tr_cont", "")
            next_key = str(response.body.get("ctx_area_nk200", ""))
            filter_key = str(response.body.get("ctx_area_fk200", ""))
            if tr_cont not in ("M", "F") or not next_key or not filter_key:
                break

        if self.credentials.env == "demo" and symbol:
            return [row for row in collected if str(row.get("pdno", "")).upper() == symbol.upper()]
        return collected

    def inquire_buying_power(
        self,
        *,
        order_exchange_code: str,
        symbol: str,
        limit_price: float,
    ) -> Dict[str, object]:
        response = self.auth_session.request(
            "GET",
            self.BUYING_POWER_ENDPOINT,
            tr_id="TTTS3007R",
            params={
                "CANO": self.credentials.cano,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": order_exchange_code,
                "OVRS_ORD_UNPR": f"{limit_price:.4f}",
                "ITEM_CD": symbol,
            },
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS buying power request failed: {response.error_code()} {response.error_message()}"
            )
        output = response.body.get("output") or []
        if isinstance(output, list):
            return output[0] if output else {}
        return output

    def place_limit_order(
        self,
        *,
        symbol: str,
        order_exchange_code: str,
        quantity: int,
        limit_price: float,
        side: str,
        order_division: str = "00",
    ) -> Dict[str, object]:
        tr_id = self._order_tr_id(side, order_exchange_code)
        sell_type = "" if side == "buy" else "00"
        response = self.auth_session.request(
            "POST",
            self.ORDER_ENDPOINT,
            tr_id=tr_id,
            body={
                "CANO": self.credentials.cano,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": order_exchange_code,
                "PDNO": symbol,
                "ORD_QTY": str(quantity),
                "OVRS_ORD_UNPR": f"{limit_price:.4f}",
                "CTAC_TLNO": "",
                "MGCO_APTM_ODNO": "",
                "SLL_TYPE": sell_type,
                "ORD_SVR_DVSN_CD": "0",
                "ORD_DVSN": order_division,
            },
            use_hash=False,
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS order request failed: {response.error_code()} {response.error_message()}"
            )
        return response.body.get("output") or response.body

    def cancel_order(
        self,
        *,
        symbol: str,
        order_exchange_code: str,
        original_order_number: str,
        quantity: int,
    ) -> Dict[str, object]:
        response = self.auth_session.request(
            "POST",
            self.CANCEL_ENDPOINT,
            tr_id="TTTT1004U",
            body={
                "CANO": self.credentials.cano,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": order_exchange_code,
                "PDNO": symbol,
                "ORGN_ODNO": original_order_number,
                "RVSE_CNCL_DVSN_CD": "02",
                "ORD_QTY": str(quantity),
                "OVRS_ORD_UNPR": "0",
                "MGCO_APTM_ODNO": "",
                "ORD_SVR_DVSN_CD": "0",
            },
            use_hash=False,
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS cancel request failed: {response.error_code()} {response.error_message()}"
            )
        return response.body.get("output") or response.body

    def extract_total_assets(self, balance: Dict[str, object]) -> float | None:
        for section in ("summary", "detail"):
            rows = balance.get(section) or []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in (
                    "tot_asst_amt",
                    "tot_dncl_amt",
                    "wdrw_psbl_tot_amt",
                    "frcr_evlu_tota",
                    "evlu_amt_smtl",
                ):
                    value = row.get(key)
                    if value in (None, ""):
                        continue
                    try:
                        return float(str(value))
                    except ValueError:
                        continue
        return None

    def _order_tr_id(self, side: str, order_exchange_code: str) -> str:
        if side == "buy":
            if order_exchange_code in ("NASD", "NYSE", "AMEX"):
                return "TTTT1002U"
        elif side == "sell":
            if order_exchange_code in ("NASD", "NYSE", "AMEX"):
                return "TTTT1006U"
        raise ValueError(f"Unsupported side/exchange for KIS overseas order: {side} / {order_exchange_code}")
