"""
Test Suite for Wallet Discovery Module

Tests all major functions with mocked API responses. Does not hit real APIs.

Test Coverage:
    - Configuration loading (file, env vars, errors)
    - Rate limiting (token bucket algorithm)
    - Exponential backoff on failures
    - Transaction parsing and filtering
    - Contract address detection
    - Wallet metrics calculation
    - Filter logic
    - CSV export

Usage:
    pytest test_wallet_discovery.py -v
"""

import pytest
import json
import time
import os
import tempfile
import csv
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

from wallet_discovery import (
    load_config,
    TokenBucket,
    BlockchainAPIClient,
    EtherscanClient,
    BSCScanClient,
    WalletMetrics,
    apply_filters,
    export_to_csv,
    fetch_wallet_metrics,
    APIError,
    RateLimitError
)


class TestConfigLoading:
    """Test configuration loading from file and environment variables."""

    def test_load_config_from_file(self, tmp_path):
        """Test loading config from JSON file."""
        config_file = tmp_path / "api_keys.json"
        config_data = {
            "etherscan_api_key": "test_eth_key_123",
            "bscscan_api_key": "test_bsc_key_456"
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        config = load_config(str(config_file))

        assert config['etherscan_api_key'] == "test_eth_key_123"
        assert config['bscscan_api_key'] == "test_bsc_key_456"
        assert config['rate_limit_per_second'] == 5.0  # Default
        assert config['max_retries'] == 5  # Default

    def test_load_config_from_env_vars(self, tmp_path, monkeypatch):
        """Test fallback to environment variables."""
        nonexistent_file = tmp_path / "nonexistent.json"

        monkeypatch.setenv("ETHERSCAN_API_KEY", "env_eth_key")
        monkeypatch.setenv("BSCSCAN_API_KEY", "env_bsc_key")

        config = load_config(str(nonexistent_file))

        assert config['etherscan_api_key'] == "env_eth_key"
        assert config['bscscan_api_key'] == "env_bsc_key"

    def test_load_config_missing_keys(self, tmp_path):
        """Test error when required keys are missing."""
        config_file = tmp_path / "incomplete.json"

        with open(config_file, 'w') as f:
            json.dump({"etherscan_api_key": "test"}, f)

        with pytest.raises(ValueError, match="Missing required API keys"):
            load_config(str(config_file))

    def test_load_config_invalid_json(self, tmp_path):
        """Test error handling for invalid JSON."""
        config_file = tmp_path / "invalid.json"

        with open(config_file, 'w') as f:
            f.write("{invalid json content")

        with pytest.raises(ValueError, match="Invalid config file"):
            load_config(str(config_file))


class TestRateLimiting:
    """Test token bucket rate limiting algorithm."""

    def test_token_bucket_allows_burst(self):
        """Test that token bucket allows burst up to capacity."""
        bucket = TokenBucket(rate=5.0, capacity=5)

        start_time = time.time()

        # Should allow 5 immediate requests (burst)
        for _ in range(5):
            bucket.consume(1)

        elapsed = time.time() - start_time

        # All 5 requests should complete in < 0.1 seconds (burst)
        assert elapsed < 0.1

    def test_token_bucket_enforces_rate_limit(self):
        """Test that rate limiting works after burst exhausted."""
        bucket = TokenBucket(rate=5.0, capacity=5)

        start_time = time.time()

        # Consume 10 tokens (5 burst + 5 rate-limited)
        for _ in range(10):
            bucket.consume(1)

        elapsed = time.time() - start_time

        # Should take ~1 second for 10 requests at 5 req/sec
        # (5 burst immediate + 5 at rate limit)
        assert 0.9 < elapsed < 1.5

    def test_token_bucket_refills_over_time(self):
        """Test token refill mechanism."""
        bucket = TokenBucket(rate=5.0, capacity=5)

        # Exhaust bucket
        for _ in range(5):
            bucket.consume(1)

        # Wait for refill
        time.sleep(0.5)  # Should refill 2.5 tokens

        start_time = time.time()
        bucket.consume(2)  # Should not block
        elapsed = time.time() - start_time

        assert elapsed < 0.1


class TestAPIClient:
    """Test blockchain API client functionality."""

    @patch('wallet_discovery.requests.get')
    def test_make_request_success(self, mock_get):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',
            'message': 'OK',
            'result': [{'test': 'data'}]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")
        result = client._make_request({'module': 'test'})

        assert result['status'] == '1'
        assert result['result'] == [{'test': 'data'}]

    @patch('wallet_discovery.requests.get')
    def test_make_request_retry_on_timeout(self, mock_get):
        """Test retry logic on timeout."""
        # First call times out, second succeeds
        mock_get.side_effect = [
            Exception("Timeout"),
            Mock(json=lambda: {'status': '1', 'result': []}, raise_for_status=Mock())
        ]

        client = EtherscanClient(api_key="test_key")

        # Should succeed after retry
        result = client._make_request({'module': 'test'}, max_retries=2)
        assert result['status'] == '1'

    @patch('wallet_discovery.requests.get')
    def test_make_request_exponential_backoff(self, mock_get):
        """Test exponential backoff on failures."""
        mock_get.side_effect = Exception("Network error")

        client = EtherscanClient(api_key="test_key")

        start_time = time.time()

        with pytest.raises(APIError, match="Max retries exceeded"):
            client._make_request({'module': 'test'}, max_retries=3)

        elapsed = time.time() - start_time

        # Should wait: 2s + 4s = 6s total (for 3 attempts with 2 waits)
        assert elapsed >= 6.0

    @patch('wallet_discovery.requests.get')
    def test_make_request_rate_limit_error(self, mock_get):
        """Test handling of API rate limit errors."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '0',
            'message': 'NOTOK',
            'result': 'Max rate limit reached'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        # Should wait 60s on rate limit (we'll mock time.sleep)
        with patch('wallet_discovery.time.sleep') as mock_sleep:
            with pytest.raises(APIError):
                client._make_request({'module': 'test'}, max_retries=1)

            # Should have called sleep with 60s
            mock_sleep.assert_called_with(60)


class TestTransactionParsing:
    """Test transaction fetching and parsing."""

    @patch('wallet_discovery.requests.get')
    def test_get_transactions_success(self, mock_get):
        """Test successful transaction fetching."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',
            'result': [
                {
                    'hash': '0xabc123',
                    'timeStamp': '1700000000',
                    'from': '0x123',
                    'to': '0x456',
                    'value': '1000000000000000000'  # 1 ETH in wei
                },
                {
                    'hash': '0xdef456',
                    'timeStamp': '1700086400',
                    'from': '0x123',
                    'to': '0x789',
                    'value': '2000000000000000000'  # 2 ETH in wei
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        start_ts = 1699900000
        end_ts = 1700100000

        transactions = client.get_transactions('0x123', start_ts, end_ts)

        assert len(transactions) == 2
        assert transactions[0]['hash'] == '0xabc123'
        assert transactions[1]['value'] == '2000000000000000000'

    @patch('wallet_discovery.requests.get')
    def test_get_transactions_filters_by_timestamp(self, mock_get):
        """Test timestamp filtering of transactions."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',
            'result': [
                {'hash': '0x1', 'timeStamp': '1000000'},  # Too old
                {'hash': '0x2', 'timeStamp': '1700000000'},  # In range
                {'hash': '0x3', 'timeStamp': '2000000000'}  # Too new
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        transactions = client.get_transactions('0x123', 1699000000, 1701000000)

        assert len(transactions) == 1
        assert transactions[0]['hash'] == '0x2'


class TestContractDetection:
    """Test contract address detection."""

    @patch('wallet_discovery.requests.get')
    def test_is_contract_returns_true_for_contract(self, mock_get):
        """Test detecting contract addresses."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',  # Status '1' means contract with ABI
            'result': '[{"abi": "data"}]'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        assert client.is_contract('0xcontract123') is True

    @patch('wallet_discovery.requests.get')
    def test_is_contract_returns_false_for_eoa(self, mock_get):
        """Test detecting EOA (externally owned account)."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '0',  # Status '0' means no contract
            'message': 'NOTOK'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        assert client.is_contract('0xeoa123') is False

    @patch('wallet_discovery.requests.get')
    def test_is_contract_caches_results(self, mock_get):
        """Test that contract check results are cached."""
        mock_response = Mock()
        mock_response.json.return_value = {'status': '1', 'result': 'abi'}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        # First call
        result1 = client.is_contract('0xcontract123')

        # Second call (should use cache)
        result2 = client.is_contract('0xcontract123')

        assert result1 is True
        assert result2 is True

        # Should only call API once due to caching
        assert mock_get.call_count == 1


class TestPriceFetching:
    """Test USD price fetching."""

    @patch('wallet_discovery.requests.get')
    def test_get_eth_price(self, mock_get):
        """Test fetching ETH price."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',
            'result': {'ethusd': '2500.50'}
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")
        price = client.get_current_price()

        assert price == 2500.50

    @patch('wallet_discovery.requests.get')
    def test_get_bnb_price(self, mock_get):
        """Test fetching BNB price."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',
            'result': {'ethusd': '350.75'}  # BSCScan uses 'ethusd' key for BNB
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = BSCScanClient(api_key="test_key")
        price = client.get_current_price()

        assert price == 350.75

    @patch('wallet_discovery.requests.get')
    def test_price_caching(self, mock_get):
        """Test that prices are cached for 1 hour."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': '1',
            'result': {'ethusd': '2500'}
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = EtherscanClient(api_key="test_key")

        # First call
        price1 = client.get_current_price()

        # Second call (should use cache)
        price2 = client.get_current_price()

        assert price1 == 2500
        assert price2 == 2500

        # Should only call API once due to caching
        assert mock_get.call_count == 1


class TestFilterLogic:
    """Test wallet filtering criteria."""

    def test_apply_filters_passes_valid_wallet(self):
        """Test that valid wallet passes all filters."""
        metrics = WalletMetrics(
            address='0x123',
            chain='ethereum',
            total_trades=100,
            total_volume_usd=100000.0,
            last_activity=datetime.now(),
            unique_tokens=10,
            days_since_last_activity=3,
            is_contract=False
        )

        assert apply_filters(metrics) is True

    def test_apply_filters_rejects_contract(self):
        """Test that contracts are rejected."""
        metrics = WalletMetrics(
            address='0x123',
            chain='ethereum',
            total_trades=100,
            total_volume_usd=100000.0,
            last_activity=datetime.now(),
            unique_tokens=10,
            days_since_last_activity=3,
            is_contract=True  # Contract
        )

        assert apply_filters(metrics) is False

    def test_apply_filters_rejects_low_trades(self):
        """Test that wallets with < 50 trades are rejected."""
        metrics = WalletMetrics(
            address='0x123',
            chain='ethereum',
            total_trades=30,  # Below threshold
            total_volume_usd=100000.0,
            last_activity=datetime.now(),
            unique_tokens=10,
            days_since_last_activity=3,
            is_contract=False
        )

        assert apply_filters(metrics) is False

    def test_apply_filters_rejects_low_volume(self):
        """Test that wallets with < $50k volume are rejected."""
        metrics = WalletMetrics(
            address='0x123',
            chain='ethereum',
            total_trades=100,
            total_volume_usd=30000.0,  # Below threshold
            last_activity=datetime.now(),
            unique_tokens=10,
            days_since_last_activity=3,
            is_contract=False
        )

        assert apply_filters(metrics) is False

    def test_apply_filters_rejects_inactive_wallet(self):
        """Test that wallets inactive > 7 days are rejected."""
        metrics = WalletMetrics(
            address='0x123',
            chain='ethereum',
            total_trades=100,
            total_volume_usd=100000.0,
            last_activity=datetime.now() - timedelta(days=10),
            unique_tokens=10,
            days_since_last_activity=10,  # Too old
            is_contract=False
        )

        assert apply_filters(metrics) is False

    def test_apply_filters_edge_cases(self):
        """Test filter edge cases (exactly at thresholds)."""
        # Exactly 50 trades - should pass
        metrics = WalletMetrics(
            address='0x123',
            chain='ethereum',
            total_trades=50,
            total_volume_usd=50000.0,
            last_activity=datetime.now(),
            unique_tokens=10,
            days_since_last_activity=7,
            is_contract=False
        )

        assert apply_filters(metrics) is True


class TestWalletMetrics:
    """Test wallet metrics calculation."""

    @patch.object(EtherscanClient, 'get_transactions')
    @patch.object(EtherscanClient, 'is_contract')
    @patch.object(EtherscanClient, 'get_current_price')
    def test_fetch_wallet_metrics_success(
        self,
        mock_price,
        mock_is_contract,
        mock_get_txns
    ):
        """Test successful wallet metrics calculation."""
        mock_is_contract.return_value = False
        mock_price.return_value = 2500.0

        # Mock transactions
        now = int(datetime.now().timestamp())
        mock_get_txns.return_value = [
            {
                'timeStamp': str(now - 86400),  # 1 day ago
                'value': '1000000000000000000',  # 1 ETH
                'to': '0xtoken1'
            },
            {
                'timeStamp': str(now - 172800),  # 2 days ago
                'value': '2000000000000000000',  # 2 ETH
                'to': '0xtoken2'
            }
        ]

        client = EtherscanClient(api_key="test_key")
        metrics = fetch_wallet_metrics(client, '0x123', days_back=90)

        assert metrics is not None
        assert metrics.address == '0x123'
        assert metrics.chain == 'ethereum'
        assert metrics.total_trades == 2
        assert metrics.unique_tokens == 2
        assert metrics.total_volume_usd == 3.0 * 2500.0  # 3 ETH * $2500
        assert metrics.days_since_last_activity <= 1
        assert metrics.is_contract is False

    @patch.object(EtherscanClient, 'is_contract')
    def test_fetch_wallet_metrics_skips_contracts(self, mock_is_contract):
        """Test that contract addresses are skipped."""
        mock_is_contract.return_value = True

        client = EtherscanClient(api_key="test_key")
        metrics = fetch_wallet_metrics(client, '0xcontract', days_back=90)

        assert metrics is None

    @patch.object(EtherscanClient, 'get_transactions')
    @patch.object(EtherscanClient, 'is_contract')
    def test_fetch_wallet_metrics_no_transactions(
        self,
        mock_is_contract,
        mock_get_txns
    ):
        """Test handling of wallets with no transactions."""
        mock_is_contract.return_value = False
        mock_get_txns.return_value = []

        client = EtherscanClient(api_key="test_key")
        metrics = fetch_wallet_metrics(client, '0x123', days_back=90)

        assert metrics is None


class TestCSVExport:
    """Test CSV export functionality."""

    def test_export_to_csv_creates_file(self, tmp_path):
        """Test CSV file creation."""
        wallets = [
            WalletMetrics(
                address='0x123',
                chain='ethereum',
                total_trades=100,
                total_volume_usd=100000.0,
                last_activity=datetime(2025, 11, 1, 12, 0, 0),
                unique_tokens=10,
                days_since_last_activity=3,
                is_contract=False
            ),
            WalletMetrics(
                address='0x456',
                chain='bsc',
                total_trades=75,
                total_volume_usd=80000.0,
                last_activity=datetime(2025, 11, 2, 14, 30, 0),
                unique_tokens=8,
                days_since_last_activity=2,
                is_contract=False
            )
        ]

        output_file = tmp_path / "test_output.csv"
        export_to_csv(wallets, str(output_file))

        assert output_file.exists()

        # Read and verify CSV
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2

        # Should be sorted by volume (descending)
        assert rows[0]['address'] == '0x123'
        assert rows[0]['total_volume_usd'] == '100000.00'
        assert rows[1]['address'] == '0x456'

    def test_export_to_csv_correct_format(self, tmp_path):
        """Test CSV format and columns."""
        wallets = [
            WalletMetrics(
                address='0xabc',
                chain='ethereum',
                total_trades=50,
                total_volume_usd=55000.50,
                last_activity=datetime(2025, 11, 5, 10, 15, 30),
                unique_tokens=5,
                days_since_last_activity=1,
                is_contract=False
            )
        ]

        output_file = tmp_path / "format_test.csv"
        export_to_csv(wallets, str(output_file))

        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            row = next(reader)

        # Verify all columns present
        expected_columns = [
            'address', 'chain', 'total_trades', 'total_volume_usd',
            'last_activity', 'unique_tokens', 'days_since_last_activity'
        ]

        for col in expected_columns:
            assert col in row

        # Verify formatting
        assert row['address'] == '0xabc'
        assert row['total_volume_usd'] == '55000.50'
        assert row['last_activity'] == '2025-11-05 10:15:30'
        assert row['days_since_last_activity'] == '1'

    def test_export_to_csv_sorts_by_volume(self, tmp_path):
        """Test that CSV is sorted by volume descending."""
        wallets = [
            WalletMetrics('0x1', 'eth', 50, 50000.0, datetime.now(), 5, 1, False),
            WalletMetrics('0x2', 'eth', 50, 90000.0, datetime.now(), 5, 1, False),
            WalletMetrics('0x3', 'eth', 50, 70000.0, datetime.now(), 5, 1, False),
        ]

        output_file = tmp_path / "sorted_test.csv"
        export_to_csv(wallets, str(output_file))

        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Should be sorted: 90000, 70000, 50000
        assert rows[0]['address'] == '0x2'
        assert rows[1]['address'] == '0x3'
        assert rows[2]['address'] == '0x1'


class TestIntegration:
    """Integration tests for full workflow."""

    @patch.object(EtherscanClient, '_make_request')
    def test_full_workflow_integration(self, mock_request, tmp_path):
        """Test complete workflow from discovery to export."""
        # Mock API responses for different calls
        def request_side_effect(params, max_retries=None):
            action = params.get('action')

            if action == 'eth_blockNumber':
                return {'result': '0x1000000'}  # Current block

            elif action == 'eth_getBlockByNumber':
                return {
                    'result': {
                        'transactions': [
                            {'from': '0xwallet1'},
                            {'from': '0xwallet2'}
                        ]
                    }
                }

            elif action == 'txlist':
                now = int(datetime.now().timestamp())
                return {
                    'status': '1',
                    'result': [
                        {
                            'timeStamp': str(now - 86400),
                            'value': '50000000000000000000',  # 50 ETH
                            'to': '0xtoken1'
                        }
                    ] * 60  # 60 transactions
                }

            elif action == 'getabi':
                return {'status': '0'}  # Not a contract

            elif action == 'ethprice':
                return {'status': '1', 'result': {'ethusd': '2000'}}

            return {'status': '1', 'result': []}

        mock_request.side_effect = request_side_effect

        client = EtherscanClient(api_key="test_key")

        # Fetch metrics for wallet
        metrics = fetch_wallet_metrics(client, '0xwallet1', days_back=90)

        assert metrics is not None
        assert metrics.total_trades == 60
        assert metrics.total_volume_usd > 50000  # 60 txns * 50 ETH * $2000

        # Apply filters
        passes = apply_filters(metrics)
        assert passes is True

        # Export to CSV
        output_file = tmp_path / "integration_test.csv"
        export_to_csv([metrics], str(output_file))

        assert output_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
