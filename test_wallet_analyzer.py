"""
Test Suite for Wallet Analyzer Module

Tests all major functions with sample data. Does not hit real APIs.

Test Coverage:
    - FIFO trade matching (simple, partial fills, multiple tokens)
    - Win rate calculation
    - Sharpe ratio calculation (with capping)
    - Max drawdown calculation
    - Profit factor calculation
    - Consistency score calculation
    - Ranking and filtering logic
    - Capital allocation
    - Gas fee handling in P&L
    - Token tradability filtering

Usage:
    pytest test_wallet_analyzer.py -v
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import tempfile
import csv
import sqlite3

from wallet_analyzer import (
    Trade,
    ClosedTrade,
    PerformanceMetrics,
    RankedWallet,
    match_trades_fifo,
    group_by_token,
    match_all_trades,
    calculate_win_rate,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_consistency_score,
    calculate_metrics,
    allocate_capital,
    is_token_tradeable,
    filter_tradeable_tokens,
    MIN_TRADE_VALUE_USD,
    SHARPE_CAP
)


class TestTradeMatching:
    """Test FIFO trade matching algorithm."""

    def test_simple_fifo_match(self):
        """Test basic buy-sell matching."""
        trades = [
            Trade(
                timestamp=datetime(2025, 1, 1),
                action='BUY',
                token_address='0xTOKEN',
                token_symbol='TEST',
                amount=1000.0,
                price_usd=1.0,
                value_usd=1000.0,
                gas_fee_usd=5.0,
                tx_hash='0x1'
            ),
            Trade(
                timestamp=datetime(2025, 1, 2),
                action='SELL',
                token_address='0xTOKEN',
                token_symbol='TEST',
                amount=1000.0,
                price_usd=2.0,
                value_usd=2000.0,
                gas_fee_usd=10.0,
                tx_hash='0x2'
            )
        ]

        closed = match_trades_fifo(trades)

        assert len(closed) == 1
        assert closed[0].amount == 1000.0

        # P&L with gas fees:
        # Buy cost: 1000 + 5 = 1005
        # Sell proceeds: 2000 - 10 = 1990
        # P&L: 1990 - 1005 = 985
        assert abs(closed[0].pnl - 985.0) < 0.01
        assert abs(closed[0].pnl_pct - 98.01) < 0.1  # (985 / 1005) * 100

    def test_partial_buy_fill(self):
        """Test selling less than bought (partial fill)."""
        trades = [
            Trade(datetime(2025, 1, 1), 'BUY', '0xTOKEN', 'TEST',
                  1000.0, 1.0, 1000.0, 5.0, '0x1'),
            Trade(datetime(2025, 1, 2), 'SELL', '0xTOKEN', 'TEST',
                  500.0, 2.0, 1000.0, 5.0, '0x2')
        ]

        closed = match_trades_fifo(trades)

        assert len(closed) == 1
        assert closed[0].amount == 500.0  # Only 500 matched

        # Buy cost for 500: (1000 + 5) * 0.5 = 502.5
        # Sell proceeds for 500: 1000 - 5 = 995
        # P&L: 995 - 502.5 = 492.5
        assert abs(closed[0].pnl - 492.5) < 0.1

    def test_multiple_buys_one_sell(self):
        """Test FIFO with multiple buys matched to one large sell."""
        trades = [
            Trade(datetime(2025, 1, 1), 'BUY', '0xTOKEN', 'TEST',
                  1000.0, 1.0, 1000.0, 5.0, '0x1'),
            Trade(datetime(2025, 1, 2), 'BUY', '0xTOKEN', 'TEST',
                  500.0, 2.0, 1000.0, 5.0, '0x2'),
            Trade(datetime(2025, 1, 3), 'SELL', '0xTOKEN', 'TEST',
                  1200.0, 3.0, 3600.0, 10.0, '0x3')
        ]

        closed = match_trades_fifo(trades)

        # Should create 2 closed trades:
        # 1. 1000 tokens from first buy @ $1
        # 2. 200 tokens from second buy @ $2
        assert len(closed) == 2

        # First closed trade: 1000 tokens
        assert closed[0].amount == 1000.0
        assert closed[0].buy_trade.price_usd == 1.0

        # Second closed trade: 200 tokens
        assert closed[1].amount == 200.0
        assert closed[1].buy_trade.price_usd == 2.0

    def test_only_buys_no_sells(self):
        """Test that only buys result in no closed trades."""
        trades = [
            Trade(datetime(2025, 1, 1), 'BUY', '0xTOKEN', 'TEST',
                  1000.0, 1.0, 1000.0, 5.0, '0x1'),
            Trade(datetime(2025, 1, 2), 'BUY', '0xTOKEN', 'TEST',
                  500.0, 2.0, 1000.0, 5.0, '0x2')
        ]

        closed = match_trades_fifo(trades)

        assert len(closed) == 0  # No sells to match

    def test_only_sells_no_buys(self):
        """Test that only sells result in no closed trades."""
        trades = [
            Trade(datetime(2025, 1, 1), 'SELL', '0xTOKEN', 'TEST',
                  1000.0, 2.0, 2000.0, 10.0, '0x1')
        ]

        closed = match_trades_fifo(trades)

        assert len(closed) == 0  # No buys to match

    def test_fifo_order_respected(self):
        """Test that FIFO order is respected (oldest buy matched first)."""
        trades = [
            Trade(datetime(2025, 1, 1), 'BUY', '0xTOKEN', 'TEST',
                  1000.0, 1.0, 1000.0, 5.0, '0x1'),  # Oldest
            Trade(datetime(2025, 1, 2), 'BUY', '0xTOKEN', 'TEST',
                  1000.0, 2.0, 2000.0, 5.0, '0x2'),  # Newer
            Trade(datetime(2025, 1, 3), 'SELL', '0xTOKEN', 'TEST',
                  1000.0, 3.0, 3000.0, 10.0, '0x3')
        ]

        closed = match_trades_fifo(trades)

        assert len(closed) == 1
        # Should match oldest buy (price $1, not $2)
        assert closed[0].buy_trade.price_usd == 1.0


class TestGroupByToken:
    """Test token grouping functionality."""

    def test_group_multiple_tokens(self):
        """Test grouping trades by token address."""
        trades = [
            Trade(datetime(2025, 1, 1), 'BUY', '0xTOKEN1', 'A',
                  100.0, 1.0, 100.0, 1.0, '0x1'),
            Trade(datetime(2025, 1, 1), 'BUY', '0xTOKEN2', 'B',
                  200.0, 2.0, 400.0, 2.0, '0x2'),
            Trade(datetime(2025, 1, 2), 'SELL', '0xTOKEN1', 'A',
                  50.0, 1.5, 75.0, 1.0, '0x3'),
        ]

        grouped = group_by_token(trades)

        assert len(grouped) == 2
        assert '0xTOKEN1' in grouped
        assert '0xTOKEN2' in grouped
        assert len(grouped['0xTOKEN1']) == 2  # 1 buy + 1 sell
        assert len(grouped['0xTOKEN2']) == 1  # 1 buy only


class TestWinRate:
    """Test win rate calculation."""

    def test_win_rate_100_percent(self):
        """Test 100% win rate."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 120, 20, 20.0, timedelta(hours=24)),
        ]

        win_rate = calculate_win_rate(closed_trades)
        assert win_rate == 100.0

    def test_win_rate_75_percent(self):
        """Test 75% win rate (3 wins, 1 loss)."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24)),  # Win
            ClosedTrade(None, None, 100, 100, 120, 20, 20.0, timedelta(hours=24)),  # Win
            ClosedTrade(None, None, 100, 100, 80, -20, -20.0, timedelta(hours=24)), # Loss
            ClosedTrade(None, None, 100, 100, 110, 10, 10.0, timedelta(hours=24)),  # Win
        ]

        win_rate = calculate_win_rate(closed_trades)
        assert win_rate == 75.0

    def test_win_rate_empty(self):
        """Test win rate with no trades."""
        win_rate = calculate_win_rate([])
        assert win_rate == 0.0


class TestSharpeRatio:
    """Test Sharpe ratio calculation."""

    def test_sharpe_consistent_profits(self):
        """Test Sharpe with consistent positive returns."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 110, 10, 10.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 112, 12, 12.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 108, 8, 8.0, timedelta(hours=24)),
        ]

        sharpe = calculate_sharpe_ratio(closed_trades)

        # Mean return = 10%, Std dev = ~2%, Sharpe = ~5
        assert sharpe > 0
        assert sharpe <= SHARPE_CAP  # Should be capped at 3.0

    def test_sharpe_high_volatility(self):
        """Test Sharpe with high volatility (lower Sharpe)."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 200, 100, 100.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 50, -50, -50.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24)),
        ]

        sharpe = calculate_sharpe_ratio(closed_trades)

        # High volatility should result in lower Sharpe
        assert sharpe < 2.0

    def test_sharpe_negative_returns(self):
        """Test Sharpe with negative mean return."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 90, -10, -10.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 85, -15, -15.0, timedelta(hours=24)),
        ]

        sharpe = calculate_sharpe_ratio(closed_trades)
        assert sharpe < 0  # Negative Sharpe for losing strategy

    def test_sharpe_single_trade(self):
        """Test Sharpe with only one trade (no variance)."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24))
        ]

        sharpe = calculate_sharpe_ratio(closed_trades)
        assert sharpe == 0.0  # Need at least 2 trades for variance

    def test_sharpe_capped_at_3(self):
        """Test that Sharpe is capped at 3.0."""
        # Create unrealistically consistent returns
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24))
            for _ in range(10)
        ]

        sharpe = calculate_sharpe_ratio(closed_trades)
        assert sharpe <= SHARPE_CAP


class TestMaxDrawdown:
    """Test maximum drawdown calculation."""

    def test_no_drawdown(self):
        """Test with always increasing P&L (no drawdown)."""
        buy = Trade(datetime(2025, 1, 1), 'BUY', '0xT', 'T', 100, 1, 100, 1, '0x1')

        closed_trades = [
            ClosedTrade(buy, None, 100, 100, 110, 10, 10.0, timedelta(hours=1)),
            ClosedTrade(buy, None, 100, 110, 120, 10, 9.09, timedelta(hours=2)),
            ClosedTrade(buy, None, 100, 120, 130, 10, 8.33, timedelta(hours=3)),
        ]

        max_dd = calculate_max_drawdown(closed_trades)
        assert max_dd == 0.0  # No drawdown

    def test_50_percent_drawdown(self):
        """Test with 50% drawdown."""
        buy = Trade(datetime(2025, 1, 1), 'BUY', '0xT', 'T', 100, 1, 100, 1, '0x1')
        sell1 = Trade(datetime(2025, 1, 2), 'SELL', '0xT', 'T', 100, 2, 200, 1, '0x2')
        sell2 = Trade(datetime(2025, 1, 3), 'SELL', '0xT', 'T', 100, 1.5, 150, 1, '0x3')

        closed_trades = [
            ClosedTrade(buy, sell1, 100, 101, 199, 98, 97.0, timedelta(hours=1)),  # Cumul: +98
            ClosedTrade(buy, sell2, 100, 101, 149, 48, 47.5, timedelta(hours=2)),  # Cumul: +146
            ClosedTrade(buy, sell2, 100, 146, 73, -73, -50.0, timedelta(hours=3)), # Cumul: +73
        ]

        max_dd = calculate_max_drawdown(closed_trades)

        # Peak: 146, Trough: 73, Drawdown: (146-73)/146 = 50%
        assert abs(max_dd - 0.5) < 0.01

    def test_drawdown_empty_trades(self):
        """Test drawdown with no trades."""
        max_dd = calculate_max_drawdown([])
        assert max_dd == 0.0


class TestProfitFactor:
    """Test profit factor calculation."""

    def test_profit_factor_2x(self):
        """Test 2:1 profit factor."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 200, 100, 100.0, timedelta(hours=24)),  # +100
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24)),    # +50
            ClosedTrade(None, None, 100, 100, 50, -50, -50.0, timedelta(hours=24)),   # -50
            ClosedTrade(None, None, 100, 100, 75, -25, -25.0, timedelta(hours=24)),   # -25
        ]

        pf = calculate_profit_factor(closed_trades)

        # Gross profit: 150, Gross loss: 75, PF = 2.0
        assert abs(pf - 2.0) < 0.01

    def test_profit_factor_no_losses(self):
        """Test profit factor with no losing trades."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 120, 20, 20.0, timedelta(hours=24)),
        ]

        pf = calculate_profit_factor(closed_trades)
        assert pf == 999.0  # Perfect performance (capped)

    def test_profit_factor_only_losses(self):
        """Test profit factor with only losing trades."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 80, -20, -20.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 90, -10, -10.0, timedelta(hours=24)),
        ]

        pf = calculate_profit_factor(closed_trades)
        assert pf == 0.0


class TestConsistencyScore:
    """Test consistency score calculation."""

    def test_high_consistency(self):
        """Test high win rate with low volatility."""
        # 80% win rate with consistent returns
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 110, 10, 10.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 112, 12, 12.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 111, 11, 11.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 109, 9, 9.0, timedelta(hours=24)),
            ClosedTrade(None, None, 100, 100, 95, -5, -5.0, timedelta(hours=24)),  # 1 loss
        ]

        consistency = calculate_consistency_score(closed_trades)

        # High win rate (80%) + low volatility = high consistency
        assert consistency > 0.6

    def test_low_consistency(self):
        """Test low win rate or high volatility."""
        closed_trades = [
            ClosedTrade(None, None, 100, 100, 200, 100, 100.0, timedelta(hours=24)),  # Big win
            ClosedTrade(None, None, 100, 100, 50, -50, -50.0, timedelta(hours=24)),   # Big loss
            ClosedTrade(None, None, 100, 100, 150, 50, 50.0, timedelta(hours=24)),    # Win
        ]

        consistency = calculate_consistency_score(closed_trades)

        # High volatility = low consistency
        assert consistency < 0.5


class TestMetricsCalculation:
    """Test complete metrics calculation."""

    def test_calculate_metrics_success(self):
        """Test successful metrics calculation."""
        buy = Trade(datetime(2025, 1, 1), 'BUY', '0xT', 'T', 100, 1, 100, 1, '0x1')
        sell = Trade(datetime(2025, 1, 2), 'SELL', '0xT', 'T', 100, 2, 200, 2, '0x2')

        closed_trades = [
            ClosedTrade(buy, sell, 100, 101, 198, 97, 96.04, timedelta(hours=24))
            for _ in range(60)  # 60 trades
        ]

        metrics = calculate_metrics('0x123', 'ethereum', closed_trades)

        assert metrics is not None
        assert metrics.address == '0x123'
        assert metrics.chain == 'ethereum'
        assert metrics.total_closed_trades == 60
        assert metrics.winning_trades == 60
        assert metrics.win_rate == 100.0

    def test_calculate_metrics_empty_trades(self):
        """Test metrics with no closed trades."""
        metrics = calculate_metrics('0x123', 'ethereum', [])
        assert metrics is None


class TestFiltering:
    """Test wallet filtering logic."""

    def test_passes_all_filters(self):
        """Test wallet that passes all filters."""
        metrics = PerformanceMetrics(
            address='0x123',
            chain='ethereum',
            total_closed_trades=60,
            winning_trades=40,
            losing_trades=20,
            win_rate=66.7,  # > 55%
            sharpe_ratio=2.0,
            max_drawdown=0.20,  # < 30%
            profit_factor=2.5,
            avg_return_pct=10.0,
            consistency_score=0.65,
            total_pnl=5000.0,
            gross_profit=7500.0,
            gross_loss=2500.0,
            avg_trade_duration_hours=24.0,
            median_return_pct=8.0,
            total_gas_fees=100.0
        )

        assert metrics.passes_filters() is True

    def test_fails_win_rate(self):
        """Test wallet that fails win rate filter."""
        metrics = PerformanceMetrics(
            address='0x123', chain='ethereum',
            total_closed_trades=60, winning_trades=30, losing_trades=30,
            win_rate=50.0,  # ≤ 55%
            sharpe_ratio=2.0, max_drawdown=0.20, profit_factor=2.0,
            avg_return_pct=5.0, consistency_score=0.5,
            total_pnl=1000.0, gross_profit=2000.0, gross_loss=1000.0,
            avg_trade_duration_hours=24.0, median_return_pct=5.0, total_gas_fees=50.0
        )

        assert metrics.passes_filters() is False

    def test_fails_max_drawdown(self):
        """Test wallet that fails drawdown filter."""
        metrics = PerformanceMetrics(
            address='0x123', chain='ethereum',
            total_closed_trades=60, winning_trades=40, losing_trades=20,
            win_rate=66.7, sharpe_ratio=2.0,
            max_drawdown=0.35,  # ≥ 30%
            profit_factor=2.0, avg_return_pct=10.0, consistency_score=0.6,
            total_pnl=3000.0, gross_profit=5000.0, gross_loss=2000.0,
            avg_trade_duration_hours=24.0, median_return_pct=8.0, total_gas_fees=75.0
        )

        assert metrics.passes_filters() is False

    def test_fails_min_trades(self):
        """Test wallet that fails minimum trades filter."""
        metrics = PerformanceMetrics(
            address='0x123', chain='ethereum',
            total_closed_trades=30,  # < 50
            winning_trades=25, losing_trades=5,
            win_rate=83.3, sharpe_ratio=2.5, max_drawdown=0.10, profit_factor=3.0,
            avg_return_pct=15.0, consistency_score=0.8,
            total_pnl=2000.0, gross_profit=2500.0, gross_loss=500.0,
            avg_trade_duration_hours=24.0, median_return_pct=12.0, total_gas_fees=40.0
        )

        assert metrics.passes_filters() is False


class TestRanking:
    """Test ranking and scoring logic."""

    def test_calculate_score(self):
        """Test rank score calculation."""
        metrics = PerformanceMetrics(
            address='0x123', chain='ethereum',
            total_closed_trades=60, winning_trades=40, losing_trades=20,
            win_rate=66.7, sharpe_ratio=2.0, max_drawdown=0.20, profit_factor=2.5,
            avg_return_pct=10.0, consistency_score=0.65,
            total_pnl=5000.0, gross_profit=7500.0, gross_loss=2500.0,
            avg_trade_duration_hours=24.0, median_return_pct=8.0, total_gas_fees=100.0
        )

        score = RankedWallet.calculate_score(metrics)

        # Score should be between 0-100
        assert 0 <= score <= 100

        # With these good metrics, should score fairly high
        assert score > 60

    def test_perfect_score(self):
        """Test score with perfect metrics."""
        metrics = PerformanceMetrics(
            address='0x123', chain='ethereum',
            total_closed_trades=100, winning_trades=100, losing_trades=0,
            win_rate=100.0, sharpe_ratio=3.0, max_drawdown=0.0, profit_factor=999.0,
            avg_return_pct=50.0, consistency_score=1.0,
            total_pnl=50000.0, gross_profit=50000.0, gross_loss=0.0,
            avg_trade_duration_hours=24.0, median_return_pct=50.0, total_gas_fees=100.0
        )

        score = RankedWallet.calculate_score(metrics)

        # Should be near perfect score
        assert score > 90


class TestCapitalAllocation:
    """Test capital allocation logic."""

    def test_allocation_top_5(self):
        """Test 10% allocation for top 5."""
        wallets = [
            RankedWallet('0x1', 'eth', None, 90.0),
            RankedWallet('0x2', 'eth', None, 85.0),
            RankedWallet('0x3', 'eth', None, 80.0),
            RankedWallet('0x4', 'eth', None, 75.0),
            RankedWallet('0x5', 'eth', None, 70.0),
        ]

        allocated = allocate_capital(wallets)

        for i in range(5):
            assert allocated[i].allocation_pct == 10.0
            assert allocated[i].rank_position == i + 1

    def test_allocation_ranks_6_10(self):
        """Test 5% allocation for ranks 6-10."""
        wallets = [RankedWallet(f'0x{i}', 'eth', None, 90.0 - i) for i in range(15)]

        allocated = allocate_capital(wallets)

        for i in range(5, 10):
            assert allocated[i].allocation_pct == 5.0

    def test_allocation_ranks_11_20(self):
        """Test 2.5% allocation for ranks 11-20."""
        wallets = [RankedWallet(f'0x{i}', 'eth', None, 90.0 - i) for i in range(25)]

        allocated = allocate_capital(wallets)

        for i in range(10, 20):
            assert allocated[i].allocation_pct == 2.5

    def test_allocation_below_20(self):
        """Test 0% allocation below rank 20."""
        wallets = [RankedWallet(f'0x{i}', 'eth', None, 90.0 - i) for i in range(25)]

        allocated = allocate_capital(wallets)

        for i in range(20, 25):
            assert allocated[i].allocation_pct == 0.0

    def test_total_allocation(self):
        """Test that total allocation equals 100% for 20+ wallets."""
        wallets = [RankedWallet(f'0x{i}', 'eth', None, 90.0 - i) for i in range(20)]

        allocated = allocate_capital(wallets)

        total = sum(w.allocation_pct for w in allocated)
        assert abs(total - 100.0) < 0.01  # Should equal 100%


class TestTokenFiltering:
    """Test token tradability filtering."""

    def test_tradeable_major_tokens(self):
        """Test that major tokens are recognized as tradeable."""
        major_tokens = ['ETH', 'BTC', 'USDT', 'BNB', 'PEPE', 'SHIB']

        for token in major_tokens:
            assert is_token_tradeable(token) is True

    def test_nontradeable_tokens(self):
        """Test that obscure tokens are not tradeable."""
        obscure_tokens = ['SCAM123', 'RANDOM', 'UNKNOWN']

        for token in obscure_tokens:
            assert is_token_tradeable(token) is False

    def test_filter_trades_by_tradeable(self):
        """Test filtering trades by token tradability."""
        trades = [
            Trade(datetime(2025, 1, 1), 'BUY', '0xETH', 'ETH',
                  100, 2000, 200000, 5, '0x1'),  # Tradeable
            Trade(datetime(2025, 1, 1), 'BUY', '0xSCAM', 'SCAM',
                  1000, 0.01, 10, 1, '0x2'),  # Not tradeable
            Trade(datetime(2025, 1, 2), 'SELL', '0xETH', 'ETH',
                  50, 2100, 105000, 5, '0x3'),  # Tradeable
        ]

        filtered = filter_tradeable_tokens(trades)

        assert len(filtered) == 2  # Only ETH trades
        assert all(t.token_symbol == 'ETH' for t in filtered)


class TestGasFeeHandling:
    """Test that gas fees are properly included in P&L."""

    def test_gas_fees_reduce_profit(self):
        """Test that gas fees reduce profitability."""
        # Without gas fees: 100% profit
        # With gas fees: profit reduced

        buy_no_gas = Trade(datetime(2025, 1, 1), 'BUY', '0xT', 'T',
                           1000, 1.0, 1000, 0.0, '0x1')
        sell_no_gas = Trade(datetime(2025, 1, 2), 'SELL', '0xT', 'T',
                            1000, 2.0, 2000, 0.0, '0x2')

        buy_with_gas = Trade(datetime(2025, 1, 1), 'BUY', '0xT', 'T',
                             1000, 1.0, 1000, 50.0, '0x1')
        sell_with_gas = Trade(datetime(2025, 1, 2), 'SELL', '0xT', 'T',
                              1000, 2.0, 2000, 50.0, '0x2')

        # Calculate P&L without gas
        trades_no_gas = [buy_no_gas, sell_no_gas]
        closed_no_gas = match_trades_fifo(trades_no_gas)
        pnl_no_gas = closed_no_gas[0].pnl

        # Calculate P&L with gas
        trades_with_gas = [buy_with_gas, sell_with_gas]
        closed_with_gas = match_trades_fifo(trades_with_gas)
        pnl_with_gas = closed_with_gas[0].pnl

        # P&L with gas should be lower (fees = 100)
        assert pnl_with_gas == pnl_no_gas - 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
