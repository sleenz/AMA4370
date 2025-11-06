"""
Wallet Discovery Module for Copy Trading System

This module discovers profitable wallets on Ethereum and BSC by analyzing
transaction history, volume, and activity patterns. Uses Etherscan and BSCScan
APIs to identify candidate wallets for copy trading.

Discovery Strategy (Option A - Recent Blocks Sampling):
    1. Query recent blocks from last 7 days
    2. Extract unique addresses from transactions
    3. Fetch full transaction history (90 days)
    4. Calculate metrics and apply filters
    5. Export qualifying wallets to CSV

Filter Criteria:
    - Minimum 50 trades in last 90 days
    - Total volume > $50,000 USD
    - Not a smart contract address
    - Active within last 7 days

Usage:
    python wallet_discovery.py

Configuration:
    Requires config/api_keys.json with API keys for Etherscan and BSCScan
"""

import json
import time
import logging
import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import requests
from threading import Lock


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class WalletMetrics:
    """Data class for wallet metrics."""
    address: str
    chain: str
    total_trades: int
    total_volume_usd: float
    last_activity: datetime
    unique_tokens: int
    days_since_last_activity: int
    is_contract: bool


class APIError(Exception):
    """Custom exception for API-related errors."""
    pass


class RateLimitError(APIError):
    """Exception for rate limit errors."""
    pass


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.

    Allows burst traffic up to bucket capacity while maintaining
    average rate limit over time.

    Args:
        rate: Tokens added per second (e.g., 5 = 5 requests/sec)
        capacity: Maximum tokens in bucket
    """

    def __init__(self, rate: float = 5.0, capacity: int = 5):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> None:
        """
        Consume tokens from bucket, blocking if insufficient tokens.

        Args:
            tokens: Number of tokens to consume (default: 1)
        """
        with self.lock:
            while True:
                now = time.time()
                elapsed = now - self.last_update

                # Refill tokens based on elapsed time
                self.tokens = min(
                    self.capacity,
                    self.tokens + elapsed * self.rate
                )
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    break
                else:
                    # Calculate sleep time needed
                    needed = tokens - self.tokens
                    sleep_time = needed / self.rate
                    logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)


class BlockchainAPIClient:
    """
    Base class for blockchain API clients with rate limiting and retry logic.

    Features:
        - Token bucket rate limiting (5 requests/sec)
        - Exponential backoff on failures (2s, 4s, 8s, 16s, 32s)
        - Request caching for contract checks
        - Comprehensive error handling

    Args:
        api_key: API key for authentication
        base_url: Base URL for API endpoints
        rate_limit: Requests per second (default: 5.0)
        max_retries: Maximum retry attempts (default: 5)
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        rate_limit: float = 5.0,
        max_retries: int = 5,
        timeout: int = 30
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout = timeout
        self.rate_limiter = TokenBucket(rate=rate_limit)
        self.contract_cache: Dict[str, bool] = {}
        self.price_cache: Dict[str, tuple[float, float]] = {}  # (price, timestamp)

    def _make_request(
        self,
        params: Dict[str, Any],
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Make rate-limited API request with exponential backoff.

        Args:
            params: Query parameters for API request
            max_retries: Override default max_retries

        Returns:
            dict: Parsed JSON response

        Raises:
            APIError: If all retries exhausted
            RateLimitError: If rate limited by API
        """
        max_retries = max_retries or self.max_retries
        params['apikey'] = self.api_key

        for attempt in range(max_retries):
            try:
                # Rate limiting
                self.rate_limiter.consume()

                # Make request
                response = requests.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()

                # Check API-level errors
                if data.get('status') == '0' and data.get('message') == 'NOTOK':
                    error_msg = data.get('result', 'Unknown error')

                    # Handle rate limiting
                    if 'rate limit' in error_msg.lower():
                        wait_time = 60  # Wait 60s for rate limit
                        logger.warning(f"Rate limited by API, waiting {wait_time}s")
                        time.sleep(wait_time)
                        continue

                    # Other API errors
                    logger.debug(f"API error: {error_msg}")
                    raise APIError(f"API error: {error_msg}")

                return data

            except requests.exceptions.Timeout:
                wait_time = min(2 ** attempt, 32)
                logger.warning(f"Timeout, retry {attempt+1}/{max_retries}, waiting {wait_time}s")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise APIError("Max retries exceeded due to timeout")

            except requests.exceptions.RequestException as e:
                wait_time = min(2 ** attempt, 32)
                logger.warning(f"Request failed: {e}, retry {attempt+1}/{max_retries}, waiting {wait_time}s")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise APIError(f"Max retries exceeded: {e}")

        raise APIError("Max retries exceeded")

    def get_current_price(self) -> float:
        """
        Get current native token price in USD.
        Must be implemented by subclasses.

        Returns:
            float: Current price in USD
        """
        raise NotImplementedError

    def get_transactions(
        self,
        address: str,
        start_timestamp: int,
        end_timestamp: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch all transactions for address in time range.

        Args:
            address: Wallet address
            start_timestamp: Unix timestamp start
            end_timestamp: Unix timestamp end

        Returns:
            list[dict]: Transaction records
        """
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'desc'
        }

        try:
            response = self._make_request(params)
            transactions = response.get('result', [])

            # Filter by timestamp
            if isinstance(transactions, list):
                filtered = [
                    tx for tx in transactions
                    if start_timestamp <= int(tx.get('timeStamp', 0)) <= end_timestamp
                ]
                return filtered

            return []

        except APIError as e:
            logger.error(f"Failed to fetch transactions for {address}: {e}")
            return []

    def is_contract(self, address: str) -> bool:
        """
        Check if address is a smart contract.

        Args:
            address: Wallet address

        Returns:
            bool: True if contract, False if EOA
        """
        # Check cache
        if address in self.contract_cache:
            return self.contract_cache[address]

        params = {
            'module': 'contract',
            'action': 'getabi',
            'address': address
        }

        try:
            response = self._make_request(params)
            # Status '1' means contract exists with ABI
            is_contract = response.get('status') == '1'
            self.contract_cache[address] = is_contract
            return is_contract

        except APIError:
            # If error, assume it's not a contract (safer default)
            self.contract_cache[address] = False
            return False

    def get_recent_blocks(self, days: int = 7) -> List[int]:
        """
        Get list of recent block numbers from last N days.

        Args:
            days: Number of days to look back

        Returns:
            list[int]: Block numbers
        """
        # Get current block number
        params = {
            'module': 'proxy',
            'action': 'eth_blockNumber'
        }

        try:
            response = self._make_request(params)
            current_block = int(response.get('result', '0x0'), 16)

            # Estimate blocks per day (Ethereum ~7200, BSC ~28800)
            blocks_per_day = self._get_blocks_per_day()
            blocks_to_fetch = days * blocks_per_day

            start_block = max(0, current_block - blocks_to_fetch)

            logger.info(f"Fetching blocks from {start_block} to {current_block}")
            return list(range(start_block, current_block + 1, 100))  # Sample every 100 blocks

        except APIError as e:
            logger.error(f"Failed to get recent blocks: {e}")
            return []

    def _get_blocks_per_day(self) -> int:
        """Get estimated blocks per day for this chain."""
        raise NotImplementedError


class EtherscanClient(BlockchainAPIClient):
    """
    Etherscan API client for Ethereum blockchain.

    API Documentation: https://docs.etherscan.io/

    Args:
        api_key: Etherscan API key
        rate_limit: Requests per second (default: 5.0)
    """

    def __init__(self, api_key: str, rate_limit: float = 5.0):
        super().__init__(
            api_key=api_key,
            base_url='https://api.etherscan.io/api',
            rate_limit=rate_limit
        )
        self.chain_name = 'ethereum'

    def _get_blocks_per_day(self) -> int:
        """Ethereum: ~7200 blocks per day (12s block time)."""
        return 7200

    def get_current_price(self) -> float:
        """
        Get current ETH price in USD.

        Returns:
            float: ETH price in USD
        """
        # Check cache (1 hour TTL)
        if 'ETH' in self.price_cache:
            price, timestamp = self.price_cache['ETH']
            if time.time() - timestamp < 3600:  # 1 hour
                return price

        params = {
            'module': 'stats',
            'action': 'ethprice'
        }

        try:
            response = self._make_request(params)
            price = float(response.get('result', {}).get('ethusd', 0))
            self.price_cache['ETH'] = (price, time.time())
            logger.info(f"Current ETH price: ${price:.2f}")
            return price

        except (APIError, ValueError, KeyError) as e:
            logger.error(f"Failed to fetch ETH price: {e}")
            return 0.0


class BSCScanClient(BlockchainAPIClient):
    """
    BSCScan API client for Binance Smart Chain.

    API Documentation: https://docs.bscscan.com/

    Args:
        api_key: BSCScan API key
        rate_limit: Requests per second (default: 5.0)
    """

    def __init__(self, api_key: str, rate_limit: float = 5.0):
        super().__init__(
            api_key=api_key,
            base_url='https://api.bscscan.com/api',
            rate_limit=rate_limit
        )
        self.chain_name = 'bsc'

    def _get_blocks_per_day(self) -> int:
        """BSC: ~28800 blocks per day (3s block time)."""
        return 28800

    def get_current_price(self) -> float:
        """
        Get current BNB price in USD.

        Returns:
            float: BNB price in USD
        """
        # Check cache (1 hour TTL)
        if 'BNB' in self.price_cache:
            price, timestamp = self.price_cache['BNB']
            if time.time() - timestamp < 3600:  # 1 hour
                return price

        params = {
            'module': 'stats',
            'action': 'bnbprice'
        }

        try:
            response = self._make_request(params)
            price = float(response.get('result', {}).get('ethusd', 0))  # BSCScan uses 'ethusd' key
            self.price_cache['BNB'] = (price, time.time())
            logger.info(f"Current BNB price: ${price:.2f}")
            return price

        except (APIError, ValueError, KeyError) as e:
            logger.error(f"Failed to fetch BNB price: {e}")
            return 0.0


def load_config(config_path: str = "config/api_keys.json") -> Dict[str, Any]:
    """
    Load API keys and configuration from JSON file.

    Fallback order:
        1. Load from config file
        2. Load from environment variables
        3. Raise ValueError

    Args:
        config_path: Path to config file

    Returns:
        dict: Configuration with keys 'etherscan_api_key', 'bscscan_api_key'

    Raises:
        FileNotFoundError: If config file doesn't exist and env vars not set
        ValueError: If required keys are missing
    """
    config = {}

    # Try loading from file
    if Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded config from {config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise ValueError(f"Invalid config file: {e}")
    else:
        logger.warning(f"Config file not found: {config_path}")

    # Fallback to environment variables
    if 'etherscan_api_key' not in config:
        config['etherscan_api_key'] = os.environ.get('ETHERSCAN_API_KEY', '')

    if 'bscscan_api_key' not in config:
        config['bscscan_api_key'] = os.environ.get('BSCSCAN_API_KEY', '')

    # Validate required keys
    required_keys = ['etherscan_api_key', 'bscscan_api_key']
    missing_keys = [key for key in required_keys if not config.get(key)]

    if missing_keys:
        raise ValueError(
            f"Missing required API keys: {missing_keys}. "
            f"Add them to {config_path} or set environment variables."
        )

    # Set defaults
    config.setdefault('rate_limit_per_second', 5.0)
    config.setdefault('max_retries', 5)
    config.setdefault('request_timeout', 30)

    return config


def discover_top_traders(
    client: BlockchainAPIClient,
    limit: int = 1000
) -> List[str]:
    """
    Discover top trader addresses by sampling recent blocks.

    Strategy (Option A):
        1. Get recent blocks from last 7 days
        2. Fetch transactions for sample blocks
        3. Extract unique 'from' addresses
        4. Count transactions per address
        5. Return top N addresses by transaction count

    Args:
        client: API client instance (Etherscan or BSCScan)
        limit: Number of addresses to return

    Returns:
        list[str]: Wallet addresses sorted by activity
    """
    logger.info(f"Discovering top traders on {client.chain_name}...")

    # Get recent block numbers
    block_numbers = client.get_recent_blocks(days=7)

    if not block_numbers:
        logger.error("Failed to get recent blocks")
        return []

    # Sample blocks (take every Nth block to reduce API calls)
    sample_size = min(100, len(block_numbers))
    sample_blocks = block_numbers[::max(1, len(block_numbers) // sample_size)]

    logger.info(f"Sampling {len(sample_blocks)} blocks from {len(block_numbers)} total")

    # Collect addresses from block transactions
    address_tx_count: Dict[str, int] = {}

    for i, block_num in enumerate(sample_blocks):
        if i % 10 == 0:
            logger.debug(f"Processing block {i+1}/{len(sample_blocks)}")

        params = {
            'module': 'proxy',
            'action': 'eth_getBlockByNumber',
            'tag': hex(block_num),
            'boolean': 'true'
        }

        try:
            response = client._make_request(params)
            block_data = response.get('result', {})
            transactions = block_data.get('transactions', [])

            for tx in transactions:
                from_addr = tx.get('from', '').lower()
                if from_addr and from_addr != '0x0000000000000000000000000000000000000000':
                    address_tx_count[from_addr] = address_tx_count.get(from_addr, 0) + 1

        except APIError as e:
            logger.debug(f"Failed to fetch block {block_num}: {e}")
            continue

    # Sort by transaction count and return top N
    sorted_addresses = sorted(
        address_tx_count.items(),
        key=lambda x: x[1],
        reverse=True
    )

    top_addresses = [addr for addr, count in sorted_addresses[:limit]]

    logger.info(f"Discovered {len(top_addresses)} candidate addresses")
    return top_addresses


def fetch_wallet_metrics(
    client: BlockchainAPIClient,
    address: str,
    days_back: int = 90
) -> Optional[WalletMetrics]:
    """
    Fetch and calculate metrics for a single wallet.

    Args:
        client: API client instance
        address: Wallet address to analyze
        days_back: Number of days of history to fetch

    Returns:
        WalletMetrics: Wallet metrics, or None if error
    """
    logger.debug(f"Fetching metrics for {address[:10]}... on {client.chain_name}")

    # Calculate timestamp range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_back)
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())

    # Check if contract
    is_contract = client.is_contract(address)

    if is_contract:
        logger.debug(f"{address[:10]}... is a contract, skipping")
        return None

    # Fetch transactions
    transactions = client.get_transactions(address, start_timestamp, end_timestamp)

    if not transactions:
        logger.debug(f"No transactions found for {address[:10]}...")
        return None

    # Calculate metrics
    total_trades = len(transactions)
    unique_tokens = len(set(tx.get('to', '') for tx in transactions))

    # Get current price for USD conversion
    native_price = client.get_current_price()

    # Calculate total volume in USD
    total_volume_wei = sum(int(tx.get('value', 0)) for tx in transactions)
    total_volume_native = total_volume_wei / 10**18  # Convert wei to ETH/BNB
    total_volume_usd = total_volume_native * native_price

    # Find last activity
    timestamps = [int(tx.get('timeStamp', 0)) for tx in transactions]
    last_activity_timestamp = max(timestamps) if timestamps else 0
    last_activity = datetime.fromtimestamp(last_activity_timestamp)

    days_since_last = (datetime.now() - last_activity).days

    return WalletMetrics(
        address=address,
        chain=client.chain_name,
        total_trades=total_trades,
        total_volume_usd=total_volume_usd,
        last_activity=last_activity,
        unique_tokens=unique_tokens,
        days_since_last_activity=days_since_last,
        is_contract=is_contract
    )


def apply_filters(wallet_metrics: WalletMetrics) -> bool:
    """
    Apply filtering criteria to wallet metrics.

    Filter criteria:
        - total_trades >= 50
        - total_volume_usd >= 50000
        - is_contract == False
        - days_since_last_activity <= 7

    Args:
        wallet_metrics: Wallet metrics from fetch_wallet_metrics()

    Returns:
        bool: True if wallet passes all filters
    """
    if wallet_metrics.is_contract:
        logger.debug(f"Filter failed: {wallet_metrics.address[:10]}... is contract")
        return False

    if wallet_metrics.total_trades < 50:
        logger.debug(f"Filter failed: {wallet_metrics.address[:10]}... only {wallet_metrics.total_trades} trades")
        return False

    if wallet_metrics.total_volume_usd < 50000:
        logger.debug(f"Filter failed: {wallet_metrics.address[:10]}... only ${wallet_metrics.total_volume_usd:.2f} volume")
        return False

    if wallet_metrics.days_since_last_activity > 7:
        logger.debug(f"Filter failed: {wallet_metrics.address[:10]}... last active {wallet_metrics.days_since_last_activity} days ago")
        return False

    logger.debug(f"Filter passed: {wallet_metrics.address[:10]}... ✓")
    return True


def process_wallets_parallel(
    addresses: List[str],
    client: BlockchainAPIClient,
    max_workers: int = 5
) -> List[WalletMetrics]:
    """
    Process multiple wallets in parallel with progress logging.

    Args:
        addresses: List of wallet addresses to process
        client: API client instance
        max_workers: Number of parallel threads

    Returns:
        list[WalletMetrics]: Filtered wallet metrics that passed criteria
    """
    logger.info(f"Processing {len(addresses)} wallets on {client.chain_name} with {max_workers} workers")

    qualified_wallets = []
    processed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_address = {
            executor.submit(fetch_wallet_metrics, client, addr): addr
            for addr in addresses
        }

        # Process completed tasks
        for future in as_completed(future_to_address):
            processed_count += 1
            address = future_to_address[future]

            try:
                metrics = future.result()

                if metrics and apply_filters(metrics):
                    qualified_wallets.append(metrics)
                    logger.info(f"✓ Qualified: {address[:10]}... ({len(qualified_wallets)} total)")

                # Progress logging
                if processed_count % 10 == 0:
                    logger.info(
                        f"Progress: {processed_count}/{len(addresses)} processed, "
                        f"{len(qualified_wallets)} qualified"
                    )

            except Exception as e:
                logger.error(f"Error processing {address}: {e}")

    logger.info(f"Completed: {len(qualified_wallets)} qualified wallets from {len(addresses)} candidates")
    return qualified_wallets


def export_to_csv(
    wallets: List[WalletMetrics],
    filename: str = "discovered_wallets.csv"
) -> None:
    """
    Export discovered wallets to CSV file.

    Args:
        wallets: List of WalletMetrics
        filename: Output CSV filename

    CSV Columns:
        address, chain, total_trades, total_volume_usd,
        last_activity, unique_tokens, days_since_last_activity
    """
    # Sort by volume descending
    sorted_wallets = sorted(wallets, key=lambda w: w.total_volume_usd, reverse=True)

    # Write CSV
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'address',
            'chain',
            'total_trades',
            'total_volume_usd',
            'last_activity',
            'unique_tokens',
            'days_since_last_activity'
        ])

        # Data rows
        for wallet in sorted_wallets:
            writer.writerow([
                wallet.address,
                wallet.chain,
                wallet.total_trades,
                f"{wallet.total_volume_usd:.2f}",
                wallet.last_activity.strftime('%Y-%m-%d %H:%M:%S'),
                wallet.unique_tokens,
                wallet.days_since_last_activity
            ])

    logger.info(f"Exported {len(wallets)} wallets to {filename}")


def print_summary(wallets: List[WalletMetrics], total_scanned: Dict[str, int]) -> None:
    """
    Print summary statistics to console.

    Args:
        wallets: List of qualified wallets
        total_scanned: Dict with chain -> count of addresses scanned
    """
    eth_wallets = [w for w in wallets if w.chain == 'ethereum']
    bsc_wallets = [w for w in wallets if w.chain == 'bsc']

    total_addresses = sum(total_scanned.values())
    pass_rate = (len(wallets) / total_addresses * 100) if total_addresses > 0 else 0

    print("\n" + "="*60)
    print("WALLET DISCOVERY COMPLETE")
    print("="*60)
    print(f"\nTotal addresses scanned: {total_addresses}")
    for chain, count in total_scanned.items():
        print(f"  - {chain}: {count} addresses")

    print(f"\nWallets passing filters: {len(wallets)}")
    print(f"  - Ethereum: {len(eth_wallets)} wallets")
    print(f"  - BSC: {len(bsc_wallets)} wallets")

    print(f"\nOverall pass rate: {pass_rate:.2f}%")

    print(f"\nOutput: discovered_wallets.csv")
    print("="*60 + "\n")


def main() -> None:
    """
    Main orchestration function for wallet discovery pipeline.

    Pipeline steps:
        1. Load configuration from config/api_keys.json
        2. Initialize Etherscan and BSCScan clients
        3. Discover top traders on each chain (sequential)
        4. Fetch transaction history (90 days) for each address
        5. Calculate metrics and apply filters
        6. Export qualifying wallets to CSV
        7. Print summary statistics
    """
    logger.info("="*60)
    logger.info("Starting Wallet Discovery System")
    logger.info("="*60)

    try:
        # Step 1: Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")

        # Step 2: Initialize API clients
        etherscan = EtherscanClient(
            api_key=config['etherscan_api_key'],
            rate_limit=config['rate_limit_per_second']
        )
        logger.info("Etherscan client initialized")

        bscscan = BSCScanClient(
            api_key=config['bscscan_api_key'],
            rate_limit=config['rate_limit_per_second']
        )
        logger.info("BSCScan client initialized")

        all_qualified_wallets = []
        total_scanned = {}

        # Step 3-5: Process Ethereum (sequential)
        logger.info("\n" + "="*60)
        logger.info("PHASE 1: ETHEREUM")
        logger.info("="*60)

        eth_addresses = discover_top_traders(etherscan, limit=1000)
        total_scanned['ethereum'] = len(eth_addresses)

        eth_wallets = process_wallets_parallel(
            eth_addresses,
            etherscan,
            max_workers=5
        )
        all_qualified_wallets.extend(eth_wallets)

        # Step 3-5: Process BSC (sequential)
        logger.info("\n" + "="*60)
        logger.info("PHASE 2: BINANCE SMART CHAIN")
        logger.info("="*60)

        bsc_addresses = discover_top_traders(bscscan, limit=1000)
        total_scanned['bsc'] = len(bsc_addresses)

        bsc_wallets = process_wallets_parallel(
            bsc_addresses,
            bscscan,
            max_workers=5
        )
        all_qualified_wallets.extend(bsc_wallets)

        # Step 6: Export to CSV
        logger.info("\n" + "="*60)
        logger.info("EXPORTING RESULTS")
        logger.info("="*60)

        export_to_csv(all_qualified_wallets, "discovered_wallets.csv")

        # Step 7: Print summary
        print_summary(all_qualified_wallets, total_scanned)

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return


if __name__ == "__main__":
    main()
