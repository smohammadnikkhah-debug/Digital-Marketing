"""User Portfolio Service.

Provides persistent, user-scoped real portfolio management:
- Multi-lot FIFO cost basis tracking
- Purchases, partial/full sales, cash deposits, withdrawals, dividends
- Realized and unrealized P/L calculation
- Mark-to-market daily portfolio valuation and true Time-Weighted Return (TWR)
- Fair SPY benchmark comparison and rebasing for Day, MTD, YTD, 1Y, All Time
- Annual performance scorecard (Return %, SPY %, Excess pp, Annual P/L, Year-End Equity, Max DD)
- Zero fabricated prices: uses price cache with live timestamp display
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config import PRICE_CACHE_DIR, ROLLING_PRICE_CACHE_DIR
from app.models import Portfolio, PortfolioTransaction, PortfolioLot, User


def get_or_create_portfolio(db: Session, user_id: Optional[int] = None) -> Portfolio:
    """Retrieve existing user portfolio or create primary portfolio."""
    portfolio = None
    if user_id is not None:
        portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
    else:
        # Default portfolio
        portfolio = db.query(Portfolio).first()

    if not portfolio:
        portfolio = Portfolio(
            user_id=user_id,
            name="Primary Investment Portfolio",
            base_currency="USD",
            cash_balance=0.0,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)

    return portfolio


def get_latest_price_and_date(ticker: str) -> Tuple[float, str, str]:
    """Retrieve the latest available close price, date, and source for a ticker."""
    ticker_clean = ticker.strip().upper()

    # 1. Check rolling price cache
    for dir_path in [ROLLING_PRICE_CACHE_DIR, PRICE_CACHE_DIR]:
        if not dir_path.exists():
            continue
        csv_file = dir_path / f"{ticker_clean}.csv"
        if not csv_file.exists():
            csv_file = dir_path / f"{ticker_clean.replace('^', 'IDX_')}.csv"
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file)
                if not df.empty and "Close" in df.columns:
                    latest_row = df.iloc[-1]
                    price = float(latest_row["Close"])
                    dt_str = str(latest_row.get("Date", "Latest Close"))
                    return price, dt_str, f"Price Cache ({dt_str})"
            except Exception:
                pass

    # Fallback to yfinance if online
    try:
        import yfinance as yf
        t = yf.Ticker(ticker_clean)
        hist = t.history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            dt_str = hist.index[-1].strftime("%Y-%m-%d")
            return price, dt_str, f"Market Close ({dt_str})"
    except Exception:
        pass

    return 0.0, "N/A", "Unavailable"


def recalculate_portfolio(db: Session, portfolio_id: int) -> Dict[str, Any]:
    """Re-runs chronological transaction matching (FIFO), lots, cash balance, and realized P/L."""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    # Fetch all transactions ordered chronologically
    txs = (
        db.query(PortfolioTransaction)
        .filter(PortfolioTransaction.portfolio_id == portfolio_id)
        .order_by(PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc())
        .all()
    )

    # Clear existing lots to recompute pure state
    db.query(PortfolioLot).filter(PortfolioLot.portfolio_id == portfolio_id).delete()
    db.commit()

    cash_balance = 0.0
    total_realized_pnl = 0.0
    open_lots_by_ticker: Dict[str, List[PortfolioLot]] = {}

    for tx in txs:
        t_type = tx.transaction_type.upper()
        ticker = tx.ticker.upper()

        if t_type == "DEPOSIT":
            cash_balance += tx.amount
        elif t_type == "WITHDRAWAL":
            cash_balance -= abs(tx.amount)
        elif t_type == "DIVIDEND":
            cash_balance += abs(tx.amount)
        elif t_type == "BUY":
            cost_basis_per_share = (tx.quantity * tx.price_per_share + tx.fee) / tx.quantity if tx.quantity > 0 else tx.price_per_share
            total_cash_out = (tx.quantity * tx.price_per_share) + tx.fee
            cash_balance -= total_cash_out

            new_lot = PortfolioLot(
                portfolio_id=portfolio_id,
                buy_transaction_id=tx.id,
                ticker=ticker,
                exchange=tx.exchange,
                initial_quantity=tx.quantity,
                remaining_quantity=tx.quantity,
                cost_per_share=cost_basis_per_share,
                fee_allocated=tx.fee,
                purchase_date=tx.trade_date,
            )
            db.add(new_lot)
            db.flush()  # assign ID

            if ticker not in open_lots_by_ticker:
                open_lots_by_ticker[ticker] = []
            open_lots_by_ticker[ticker].append(new_lot)

        elif t_type == "SELL":
            shares_to_sell = tx.quantity
            total_cash_in = (tx.quantity * tx.price_per_share) - tx.fee
            cash_balance += total_cash_in

            available_lots = open_lots_by_ticker.get(ticker, [])
            total_available = sum(lot.remaining_quantity for lot in available_lots)

            if shares_to_sell > total_available + 1e-6:
                shares_to_sell = total_available

            shares_remaining_to_deduct = shares_to_sell
            sale_realized_pnl = 0.0

            for lot in list(available_lots):
                if shares_remaining_to_deduct <= 0:
                    break
                deduct = min(lot.remaining_quantity, shares_remaining_to_deduct)
                lot.remaining_quantity -= deduct
                shares_remaining_to_deduct -= deduct

                lot_cost = deduct * lot.cost_per_share
                lot_proceeds = deduct * tx.price_per_share
                sale_realized_pnl += (lot_proceeds - lot_cost)

                if lot.remaining_quantity <= 1e-6:
                    available_lots.remove(lot)

            sale_realized_pnl -= tx.fee
            total_realized_pnl += sale_realized_pnl

        elif t_type == "SPLIT":
            # Quantity holds the split ratio (e.g. 2.0 for 2-for-1 split, 10.0 for 10-for-1)
            split_ratio = tx.quantity if tx.quantity > 0 else 1.0
            available_lots = open_lots_by_ticker.get(ticker, [])
            for lot in available_lots:
                lot.remaining_quantity = round(lot.remaining_quantity * split_ratio, 4)
                lot.initial_quantity = round(lot.initial_quantity * split_ratio, 4)
                lot.cost_per_share = round(lot.cost_per_share / split_ratio, 4)

    # Update portfolio cash balance
    portfolio.cash_balance = round(float(cash_balance), 2)
    portfolio.updated_at = datetime.utcnow()
    db.commit()

    # Build active holdings summary
    holdings: List[Dict[str, Any]] = []
    total_market_value = 0.0

    for ticker, lots in open_lots_by_ticker.items():
        active_lots = [lot for lot in lots if lot.remaining_quantity > 1e-6]
        if not active_lots:
            continue

        total_shares = sum(lot.remaining_quantity for lot in active_lots)
        total_cost = sum(lot.remaining_quantity * lot.cost_per_share for lot in active_lots)
        avg_cost = total_cost / total_shares if total_shares > 0 else 0.0

        current_price, price_date, price_source = get_latest_price_and_date(ticker)
        market_val = total_shares * current_price
        total_market_value += market_val

        unrealized_pnl = market_val - total_cost
        unrealized_pnl_pct = (unrealized_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

        holdings.append({
            "ticker": ticker,
            "exchange": active_lots[0].exchange,
            "shares": round(float(total_shares), 4),
            "average_cost_basis": round(float(avg_cost), 2),
            "total_cost": round(float(total_cost), 2),
            "current_price": round(float(current_price), 2),
            "market_value": round(float(market_val), 2),
            "unrealized_pnl": round(float(unrealized_pnl), 2),
            "unrealized_pnl_pct": round(float(unrealized_pnl_pct), 2),
            "price_as_of": price_date,
            "price_source": price_source,
            "lots": [
                {
                    "lot_id": lot.id,
                    "buy_transaction_id": lot.buy_transaction_id,
                    "purchase_date": lot.purchase_date,
                    "initial_shares": round(float(lot.initial_quantity), 4),
                    "remaining_shares": round(float(lot.remaining_quantity), 4),
                    "cost_per_share": round(float(lot.cost_per_share), 2),
                    "fee_allocated": round(float(lot.fee_allocated), 2),
                }
                for lot in active_lots
            ],
        })

    # Add weight percentage
    total_equity = total_market_value + portfolio.cash_balance
    for h in holdings:
        h["weight_pct"] = round(float((h["market_value"] / total_equity * 100.0)), 2) if total_equity > 0 else 0.0

    # Sort holdings descending by market value
    holdings.sort(key=lambda x: x["market_value"], reverse=True)

    return {
        "portfolio_id": portfolio.id,
        "base_currency": portfolio.base_currency,
        "cash_balance": round(float(portfolio.cash_balance), 2),
        "holdings_market_value": round(float(total_market_value), 2),
        "total_equity": round(float(total_equity), 2),
        "total_realized_pnl": round(float(total_realized_pnl), 2),
        "total_unrealized_pnl": round(float(sum(h["unrealized_pnl"] for h in holdings)), 2),
        "holdings": holdings,
    }


def add_transaction(
    db: Session,
    portfolio_id: int,
    ticker: str,
    exchange: str,
    transaction_type: str,
    quantity: float,
    price_per_share: float,
    fee: float,
    trade_date: str,
    notes: str = "",
    currency: str = "USD",
) -> PortfolioTransaction:
    """Add a new transaction and automatically trigger portfolio recalculation."""
    t_type = transaction_type.upper().strip()
    ticker_clean = ticker.strip().upper() if ticker else "CASH"

    if t_type not in ("BUY", "SELL", "DEPOSIT", "WITHDRAWAL", "DIVIDEND", "SPLIT"):
        raise ValueError(f"Unknown transaction type: {transaction_type}. Supported: BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND, SPLIT")

    if t_type in ("BUY", "SELL"):
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0 for BUY or SELL")
        if price_per_share < 0:
            raise ValueError("Price per share cannot be negative")
    elif t_type in ("DEPOSIT", "WITHDRAWAL", "DIVIDEND"):
        amount_check = price_per_share if price_per_share > 0 else quantity
        if amount_check <= 0:
            raise ValueError("Amount must be greater than 0 for cash operations")
    elif t_type == "SPLIT":
        if quantity <= 0:
            raise ValueError("Split ratio must be greater than 0")

    fee = max(0.0, float(fee))

    # Validate against selling more shares than currently owned
    if t_type == "SELL":
        # Recalculate up to this point to check owned shares
        portfolio_summary = recalculate_portfolio(db, portfolio_id)
        holding = next((h for h in portfolio_summary["holdings"] if h["ticker"] == ticker_clean), None)
        owned_shares = holding["shares"] if holding else 0.0
        if quantity > owned_shares + 1e-6:
            raise ValueError(f"Insufficient shares to sell. You currently own {owned_shares:.4f} shares of {ticker_clean}, cannot sell {quantity:.4f} shares.")

    # Validate against over-withdrawing cash
    if t_type == "WITHDRAWAL":
        portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        withdraw_amount = price_per_share if price_per_share > 0 else quantity
        if portfolio and withdraw_amount > portfolio.cash_balance + 1e-6:
            raise ValueError(f"Insufficient cash for withdrawal. Available cash is ${portfolio.cash_balance:.2f}, requested withdrawal is ${withdraw_amount:.2f}.")

    # Compute cash impact amount
    if t_type == "BUY":
        amount = -(quantity * price_per_share + fee)
    elif t_type == "SELL":
        amount = (quantity * price_per_share - fee)
    elif t_type == "DEPOSIT":
        amount = price_per_share if price_per_share > 0 else quantity
        quantity = 0.0
        price_per_share = 0.0
    elif t_type == "WITHDRAWAL":
        amount = -(price_per_share if price_per_share > 0 else quantity)
        quantity = 0.0
        price_per_share = 0.0
    elif t_type == "DIVIDEND":
        amount = price_per_share if price_per_share > 0 else quantity
        quantity = 0.0
        price_per_share = 0.0
    elif t_type == "SPLIT":
        amount = 0.0
        price_per_share = 0.0

    tx = PortfolioTransaction(
        portfolio_id=portfolio_id,
        ticker=ticker_clean,
        exchange=exchange or "NASDAQ",
        transaction_type=t_type,
        quantity=round(float(quantity), 4),
        price_per_share=round(float(price_per_share), 4),
        fee=round(float(fee), 2),
        amount=round(float(amount), 2),
        currency=currency or "USD",
        trade_date=trade_date.strip(),
        notes=notes or "",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    # Recompute portfolio lots and cash
    recalculate_portfolio(db, portfolio_id)
    return tx


def update_transaction(
    db: Session,
    transaction_id: int,
    **updates,
) -> PortfolioTransaction:
    """Update an existing transaction and recalculate."""
    tx = db.query(PortfolioTransaction).filter(PortfolioTransaction.id == transaction_id).first()
    if not tx:
        raise ValueError(f"Transaction {transaction_id} not found")

    if "ticker" in updates and updates["ticker"]:
        tx.ticker = updates["ticker"].strip().upper()
    if "exchange" in updates and updates["exchange"]:
        tx.exchange = updates["exchange"]
    if "transaction_type" in updates and updates["transaction_type"]:
        tx.transaction_type = updates["transaction_type"].upper().strip()
    if "quantity" in updates:
        tx.quantity = round(float(updates["quantity"]), 4)
    if "price_per_share" in updates:
        tx.price_per_share = round(float(updates["price_per_share"]), 4)
    if "fee" in updates:
        tx.fee = round(max(0.0, float(updates["fee"])), 2)
    if "trade_date" in updates and updates["trade_date"]:
        tx.trade_date = updates["trade_date"].strip()
    if "notes" in updates:
        tx.notes = updates["notes"]

    # Recompute amount
    t_type = tx.transaction_type
    if t_type == "BUY":
        tx.amount = -(tx.quantity * tx.price_per_share + tx.fee)
    elif t_type == "SELL":
        tx.amount = (tx.quantity * tx.price_per_share - tx.fee)
    elif t_type == "DEPOSIT":
        tx.amount = tx.price_per_share if tx.price_per_share > 0 else tx.quantity
        tx.quantity = 0.0
        tx.price_per_share = 0.0
    elif t_type == "WITHDRAWAL":
        tx.amount = -abs(tx.price_per_share if tx.price_per_share > 0 else tx.quantity)
        tx.quantity = 0.0
        tx.price_per_share = 0.0
    elif t_type == "DIVIDEND":
        tx.amount = abs(tx.price_per_share if tx.price_per_share > 0 else tx.quantity)
        tx.quantity = 0.0
        tx.price_per_share = 0.0
    elif t_type == "SPLIT":
        tx.amount = 0.0
        tx.price_per_share = 0.0

    db.commit()
    db.refresh(tx)

    recalculate_portfolio(db, tx.portfolio_id)
    return tx


def delete_transaction(db: Session, transaction_id: int) -> int:
    """Delete a transaction and recalculate portfolio state."""
    tx = db.query(PortfolioTransaction).filter(PortfolioTransaction.id == transaction_id).first()
    if not tx:
        raise ValueError(f"Transaction {transaction_id} not found")

    portfolio_id = tx.portfolio_id
    db.delete(tx)
    db.commit()

    recalculate_portfolio(db, portfolio_id)
    return portfolio_id


def reset_portfolio(db: Session, portfolio_id: int) -> Dict[str, Any]:
    """Clear all transactions and lots for a portfolio (returns fresh empty state)."""
    db.query(PortfolioLot).filter(PortfolioLot.portfolio_id == portfolio_id).delete()
    db.query(PortfolioTransaction).filter(PortfolioTransaction.portfolio_id == portfolio_id).delete()
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if portfolio:
        portfolio.cash_balance = 0.0
        portfolio.updated_at = datetime.utcnow()
    db.commit()
    return recalculate_portfolio(db, portfolio_id)


def load_price_series(ticker: str) -> pd.Series:
    """Load historical daily close prices for a ticker indexed by Date (str YYYY-MM-DD)."""
    ticker_clean = ticker.strip().upper()
    for dir_path in [ROLLING_PRICE_CACHE_DIR, PRICE_CACHE_DIR]:
        if not dir_path.exists():
            continue
        csv_file = dir_path / f"{ticker_clean}.csv"
        if not csv_file.exists():
            csv_file = dir_path / f"{ticker_clean.replace('^', 'IDX_')}.csv"
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file)
                if not df.empty and "Date" in df.columns and "Close" in df.columns:
                    df["Date"] = df["Date"].astype(str)
                    df = df.drop_duplicates(subset=["Date"]).sort_values("Date")
                    return pd.Series(df["Close"].values, index=df["Date"].values)
            except Exception:
                pass
    return pd.Series(dtype=float)


def build_historical_equity_and_twr(
    db: Session,
    portfolio_id: int,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Calculate daily marked-to-market valuations, cash flows, TWR index, and SPY benchmark."""
    txs = (
        db.query(PortfolioTransaction)
        .filter(PortfolioTransaction.portfolio_id == portfolio_id)
        .order_by(PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc())
        .all()
    )

    if not txs:
        return pd.DataFrame(), pd.Series(dtype=float)

    # Load SPY series as benchmark date backbone
    spy_series = load_price_series("SPY")
    if spy_series.empty:
        start_dt = txs[0].trade_date
        end_dt = datetime.utcnow().strftime("%Y-%m-%d")
        dates = pd.date_range(start_dt, end_dt, freq="B").strftime("%Y-%m-%d").tolist()
        spy_series = pd.Series([100.0] * len(dates), index=dates)

    first_tx_date = txs[0].trade_date
    trading_dates = [d for d in spy_series.index if d >= first_tx_date]

    if not trading_dates:
        trading_dates = [first_tx_date]

    # Preload price series for all tickers involved
    all_tickers = {tx.ticker.upper() for tx in txs if tx.transaction_type in ("BUY", "SELL", "SPLIT")}
    ticker_prices: Dict[str, pd.Series] = {}
    for sym in all_tickers:
        ticker_prices[sym] = load_price_series(sym)

    # Process transactions by date
    tx_by_date: Dict[str, List[PortfolioTransaction]] = {}
    for tx in txs:
        tx_by_date.setdefault(tx.trade_date, []).append(tx)

    daily_records = []
    current_shares: Dict[str, float] = {sym: 0.0 for sym in all_tickers}
    current_cash = 0.0
    twr_index = 1.0  # Compound index starting at 1.0
    prev_equity = 0.0

    for d in trading_dates:
        # External cash flow on day d (Deposits - Withdrawals)
        day_external_cash_flow = 0.0

        # Apply transactions on day d
        if d in tx_by_date:
            for tx in tx_by_date[d]:
                t_type = tx.transaction_type.upper()
                sym = tx.ticker.upper()
                if t_type == "DEPOSIT":
                    current_cash += tx.amount
                    day_external_cash_flow += tx.amount
                elif t_type == "WITHDRAWAL":
                    current_cash -= abs(tx.amount)
                    day_external_cash_flow -= abs(tx.amount)
                elif t_type == "DIVIDEND":
                    current_cash += abs(tx.amount)
                elif t_type == "BUY":
                    current_cash += tx.amount  # amount is negative
                    current_shares[sym] = current_shares.get(sym, 0.0) + tx.quantity
                elif t_type == "SELL":
                    current_cash += tx.amount  # amount is positive
                    current_shares[sym] = max(0.0, current_shares.get(sym, 0.0) - tx.quantity)
                elif t_type == "SPLIT":
                    split_ratio = tx.quantity if tx.quantity > 0 else 1.0
                    current_shares[sym] = current_shares.get(sym, 0.0) * split_ratio

        # Holdings value at close of day d
        day_holdings_val = 0.0
        for sym, shares in current_shares.items():
            if shares > 1e-6:
                prices = ticker_prices.get(sym)
                price = 0.0
                if prices is not None and not prices.empty:
                    as_of_prices = prices.loc[:d]
                    if not as_of_prices.empty:
                        price = float(as_of_prices.iloc[-1])
                day_holdings_val += shares * price

        total_equity = day_holdings_val + current_cash

        # Time-Weighted Return (TWR) daily return:
        # Strictly isolates pure investment returns from external cash injections/withdrawals.
        # R_t = (V_t - ExternalCashFlow - V_{t-1}) / (V_{t-1} + max(0, ExternalCashFlow))
        if prev_equity > 0.0:
            effective_base = prev_equity + max(0.0, day_external_cash_flow)
            daily_gain = (total_equity - day_external_cash_flow) - prev_equity
            daily_return = (daily_gain / effective_base) if effective_base > 0 else 0.0
            twr_index *= (1.0 + daily_return)
        else:
            daily_return = 0.0

        prev_equity = total_equity

        daily_records.append({
            "date": d,
            "total_equity": round(float(total_equity), 2),
            "holdings_value": round(float(day_holdings_val), 2),
            "cash_balance": round(float(current_cash), 2),
            "external_cash_flow": round(float(day_external_cash_flow), 2),
            "daily_return": float(daily_return),
            "twr_index": float(twr_index),
            "spy_price": float(spy_series.loc[d]) if d in spy_series.index else 0.0,
        })

    df_port = pd.DataFrame(daily_records)
    return df_port, spy_series


def calculate_dashboard_data(
    db: Session,
    portfolio_id: int,
    period: str = "ytd",
) -> Dict[str, Any]:
    """Compile comprehensive portfolio overview, summary cards, rebased chart, and scorecard."""
    portfolio_summary = recalculate_portfolio(db, portfolio_id)
    df_port, spy_series = build_historical_equity_and_twr(db, portfolio_id)

    period_clean = period.lower().strip()
    if period_clean not in ("day", "mtd", "ytd", "1y", "all"):
        period_clean = "ytd"

    if df_port.empty:
        # Empty portfolio state
        return {
            "period": period_clean,
            "portfolio_summary": portfolio_summary,
            "summary_cards": {
                "total_equity": 0.0,
                "holdings_value": 0.0,
                "cash_balance": 0.0,
                "period_pnl": 0.0,
                "period_return_pct": 0.0,
                "spy_return_pct": 0.0,
                "outperformance_pp": 0.0,
                "total_unrealized_pnl": 0.0,
                "total_realized_pnl": 0.0,
                "base_currency": portfolio_summary["base_currency"],
            },
            "performance_chart": [],
            "annual_scorecard": [],
            "is_empty": True,
            "latest_price_timestamp": datetime.utcnow().strftime("%Y-%m-%d"),
        }

    latest_date_str = str(df_port["date"].iloc[-1])
    latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d")

    # Determine start date for period
    if period_clean == "day":
        if len(df_port) >= 2:
            start_idx = len(df_port) - 2
        else:
            start_idx = 0
    elif period_clean == "mtd":
        target_start = latest_dt.replace(day=1).strftime("%Y-%m-%d")
        sub = df_port[df_port["date"] >= target_start]
        start_idx = sub.index[0] if not sub.empty else 0
    elif period_clean == "ytd":
        target_start = latest_dt.replace(month=1, day=1).strftime("%Y-%m-%d")
        sub = df_port[df_port["date"] >= target_start]
        start_idx = sub.index[0] if not sub.empty else 0
    elif period_clean == "1y":
        target_start = (latest_dt - timedelta(days=365)).strftime("%Y-%m-%d")
        sub = df_port[df_port["date"] >= target_start]
        start_idx = sub.index[0] if not sub.empty else 0
    else:  # "all"
        start_idx = 0

    df_period = df_port.iloc[start_idx:].copy().reset_index(drop=True)

    # Rebase Portfolio TWR and SPY to 0% at start of period
    base_twr_index = float(df_period["twr_index"].iloc[0])
    base_spy_price = float(df_period["spy_price"].iloc[0])
    start_equity = float(df_period["total_equity"].iloc[0])

    chart_points: List[Dict[str, Any]] = []
    for _, row in df_period.iterrows():
        row_twr = float(row["twr_index"])
        row_spy = float(row["spy_price"])
        port_ret = ((row_twr / base_twr_index) - 1.0) * 100.0 if base_twr_index > 0 else 0.0
        spy_ret = ((row_spy / base_spy_price) - 1.0) * 100.0 if base_spy_price > 0 else 0.0
        excess = port_ret - spy_ret

        chart_points.append({
            "date": str(row["date"]),
            "portfolio_return_pct": round(float(port_ret), 2),
            "spy_return_pct": round(float(spy_ret), 2),
            "excess_pp": round(float(excess), 2),
            "portfolio_equity": round(float(row["total_equity"]), 2),
        })

    # Period metrics
    latest_row = df_period.iloc[-1]
    final_port_ret = chart_points[-1]["portfolio_return_pct"] if chart_points else 0.0
    final_spy_ret = chart_points[-1]["spy_return_pct"] if chart_points else 0.0
    final_excess = round(float(final_port_ret - final_spy_ret), 2)

    # Period P/L = End Equity - Start Equity - External Cash Flows in period
    external_flows_in_period = float(df_period["external_cash_flow"].iloc[1:].sum()) if len(df_period) > 1 else 0.0
    period_pnl = float(latest_row["total_equity"]) - start_equity - external_flows_in_period

    # Annual Scorecard grouped by calendar year
    df_port["year"] = df_port["date"].str[:4].astype(int)
    annual_scorecard: List[Dict[str, Any]] = []

    for year, y_group in df_port.groupby("year"):
        y_start_row = y_group.iloc[0]
        y_end_row = y_group.iloc[-1]

        y_base_twr = float(y_start_row["twr_index"])
        y_end_twr = float(y_end_row["twr_index"])
        y_port_ret = ((y_end_twr / y_base_twr) - 1.0) * 100.0 if y_base_twr > 0 else 0.0

        y_base_spy = float(y_start_row["spy_price"])
        y_end_spy = float(y_end_row["spy_price"])
        y_spy_ret = ((y_end_spy / y_base_spy) - 1.0) * 100.0 if y_base_spy > 0 else 0.0

        y_excess = y_port_ret - y_spy_ret

        y_flows = float(y_group["external_cash_flow"].iloc[1:].sum()) if len(y_group) > 1 else 0.0
        y_pnl = float(y_end_row["total_equity"]) - float(y_start_row["total_equity"]) - y_flows

        # Calculate max drawdown in year
        equities = y_group["total_equity"].values.astype(float)
        peaks = np.maximum.accumulate(equities)
        dds = (equities - peaks) / np.where(peaks > 0, peaks, 1.0) * 100.0
        y_max_dd = float(np.min(dds)) if len(dds) > 0 else 0.0

        label = "Full Year"
        if year == latest_dt.year:
            label = "YTD"
        elif str(y_start_row["date"]) > f"{year}-01-15":
            label = f"Partial (from {y_start_row['date']})"

        annual_scorecard.append({
            "year": int(year),
            "period_label": label,
            "portfolio_return_pct": round(float(y_port_ret), 2),
            "spy_return_pct": round(float(y_spy_ret), 2),
            "excess_pp": round(float(y_excess), 2),
            "annual_pnl": round(float(y_pnl), 2),
            "year_end_equity": round(float(y_end_row["total_equity"]), 2),
            "max_drawdown_pct": round(float(y_max_dd), 2),
            "from_date": str(y_start_row["date"]),
            "through_date": str(y_end_row["date"]),
        })

    # Summary cards
    summary_cards = {
        "total_equity": round(float(portfolio_summary["total_equity"]), 2),
        "holdings_value": round(float(portfolio_summary["holdings_market_value"]), 2),
        "cash_balance": round(float(portfolio_summary["cash_balance"]), 2),
        "period_pnl": round(float(period_pnl), 2),
        "period_return_pct": round(float(final_port_ret), 2),
        "spy_return_pct": round(float(final_spy_ret), 2),
        "outperformance_pp": round(float(final_excess), 2),
        "total_unrealized_pnl": round(float(portfolio_summary["total_unrealized_pnl"]), 2),
        "total_realized_pnl": round(float(portfolio_summary["total_realized_pnl"]), 2),
        "base_currency": portfolio_summary["base_currency"],
    }

    return {
        "period": period_clean,
        "portfolio_summary": portfolio_summary,
        "summary_cards": summary_cards,
        "performance_chart": chart_points,
        "annual_scorecard": annual_scorecard,
        "is_empty": False,
        "latest_price_timestamp": latest_date_str,
    }


def seed_sample_portfolio(db: Session, portfolio_id: int) -> Dict[str, Any]:
    """Seed a realistic multi-year, multi-lot portfolio with purchases, sales, deposits, and dividends."""
    # Clear existing transactions and lots
    db.query(PortfolioLot).filter(PortfolioLot.portfolio_id == portfolio_id).delete()
    db.query(PortfolioTransaction).filter(PortfolioTransaction.portfolio_id == portfolio_id).delete()
    db.commit()

    sample_txs = [
        # Inception: $100,000 cash deposit on 2024-01-08
        ("CASH", "CASH", "DEPOSIT", 0.0, 100000.0, 0.0, "2024-01-08", "Initial Portfolio Capital Allocation"),
        # Multi-lot NVDA purchase: Lot 1
        ("NVDA", "NASDAQ", "BUY", 100.0, 55.0, 5.0, "2024-02-12", "Initial NVDA position, AI infrastructure thesis"),
        # AAPL purchase
        ("AAPL", "NASDAQ", "BUY", 100.0, 180.0, 5.0, "2024-03-05", "Core consumer tech compounder"),
        # MSFT purchase
        ("MSFT", "NASDAQ", "BUY", 50.0, 415.0, 5.0, "2024-04-10", "Cloud enterprise & Copilot growth"),
        # Multi-lot NVDA purchase: Lot 2 (higher price)
        ("NVDA", "NASDAQ", "BUY", 60.0, 88.0, 5.0, "2024-05-22", "NVDA lot add after strong earnings report"),
        # Partial sale of NVDA (FIFO will sell from Lot 1 @ $55)
        ("NVDA", "NASDAQ", "SELL", 40.0, 122.0, 5.0, "2024-07-16", "Profit take on NVDA breakout (40 shares @ $122)"),
        # AAPL Dividend
        ("AAPL", "NASDAQ", "DIVIDEND", 0.0, 110.0, 0.0, "2024-08-15", "AAPL Q3 cash dividend"),
        # Secondary deposit in 2025
        ("CASH", "CASH", "DEPOSIT", 0.0, 20000.0, 0.0, "2025-01-14", "Annual retirement contribution addition"),
        # AMZN purchase
        ("AMZN", "NASDAQ", "BUY", 80.0, 195.0, 5.0, "2025-02-18", "AWS cloud reacceleration & e-commerce margin"),
        # GOOGL purchase
        ("GOOGL", "NASDAQ", "BUY", 75.0, 172.0, 5.0, "2025-06-05", "Search & YouTube advertising cash generator"),
    ]

    for ticker, exchange, t_type, qty, price, fee, trade_date, notes in sample_txs:
        add_transaction(
            db=db,
            portfolio_id=portfolio_id,
            ticker=ticker,
            exchange=exchange,
            transaction_type=t_type,
            quantity=qty,
            price_per_share=price,
            fee=fee,
            trade_date=trade_date,
            notes=notes,
        )

    return recalculate_portfolio(db, portfolio_id)

