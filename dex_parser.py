"""
DEX Parser - Multi-Protocol Swap Transaction Decoder

Supports parsing swap transactions from:
- Uniswap V2 (Ethereum)
- Uniswap V3 (Ethereum)
- PancakeSwap V2 (BSC/Ethereum)
- PancakeSwap V3 (BSC/Ethereum)

Features:
    - Event log parsing for Swap events
    - Multi-hop swap path extraction
    - Token symbol/decimals lookup with caching
    - USD price conversion via CoinGecko API
    - BUY/SELL action classification

Usage:
    >>> from web3 import Web3
    >>> w3 = Web3(Web3.HTTPProvider('https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY'))
    >>> parser = DexParser(w3, etherscan_api_key='YOUR_KEY')
    >>> swap_info = parser.parse_transaction(tx_hash='0x...', wallet_address='0x...')
"""

import logging
import time
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from web3 import Web3
from web3.types import TxData, TxReceipt, LogReceipt
from web3.exceptions import TransactionNotFound
from eth_abi import decode as abi_decode

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class SwapInfo:
    """Complete information about a DEX swap transaction."""
    tx_hash: str
    block_number: int
    timestamp: datetime

    # DEX info
    dex_protocol: str  # 'uniswap_v2', 'uniswap_v3', 'pancakeswap_v2', etc.
    router_address: str

    # Swap details
    token_in: str  # Address
    token_out: str  # Address
    token_in_symbol: str
    token_out_symbol: str

    amount_in: float  # Human-readable (after decimals conversion)
    amount_out: float
    amount_in_usd: float
    amount_out_usd: float

    # Action classification
    action: str  # 'BUY' or 'SELL'

    # Wallet info
    wallet_address: str
    recipient_address: str  # May differ from sender

    # Multi-hop info
    is_multihop: bool
    path: List[str] = field(default_factory=list)  # Full token path


@dataclass
class TokenInfo:
    """Cached token information."""
    address: str
    symbol: str
    decimals: int
    price_usd: float
    last_updated: datetime


# ============================================================================
# DEX PARSER
# ============================================================================

class DexParser:
    """
    Multi-protocol DEX transaction parser.

    Decodes swap transactions from Uniswap V2/V3 and PancakeSwap V2/V3.

    Features:
        - Multiple RPC provider fallback
        - Automatic retry with exponential backoff
        - Provider rotation on failures
    """

    # Event signatures (topic[0] for logs)
    V2_SWAP_TOPIC = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
    V3_SWAP_TOPIC = '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67'
    TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

    # Default RPC providers with fallback order
    DEFAULT_RPC_PROVIDERS = [
        'https://eth.drpc.org',
        'https://rpc.ankr.com/eth',
        'https://ethereum.publicnode.com',
        'https://1rpc.io/eth',
        'https://eth.llamarpc.com',
        'https://cloudflare-eth.com',
    ]

    # Function selectors
    V2_SWAP_EXACT_TOKENS = '0x38ed1739'  # swapExactTokensForTokens
    V2_SWAP_TOKENS_EXACT = '0x8803dbee'  # swapTokensForExactTokens
    V2_SWAP_EXACT_ETH = '0x7ff36ab5'     # swapExactETHForTokens
    V2_SWAP_TOKENS_ETH = '0x18cbafe5'    # swapExactTokensForETH

    V3_EXACT_INPUT_SINGLE = '0x414bf389'  # exactInputSingle
    V3_EXACT_INPUT = '0xc04b8d59'         # exactInput
    V3_EXACT_OUTPUT_SINGLE = '0xdb3e2198' # exactOutputSingle
    V3_EXACT_OUTPUT = '0xf28c0498'        # exactOutput

    # Known router addresses
    KNOWN_ROUTERS = {
        # Uniswap V2
        '0x7a250d5630b4cf539739df2c5dacb4c659f2488d': 'uniswap_v2',

        # Uniswap V3
        '0xe592427a0aece92de3edee1f18e0157c05861564': 'uniswap_v3',
        '0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45': 'uniswap_v3',

        # Uniswap Universal Router (MOST COMMONLY USED)
        '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad': 'uniswap_v3',  # Universal Router
        '0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b': 'uniswap_v3',  # Universal Router (old)
        '0x4c60051384bd2d3c01bfc845cf5f4b44bcbe9de5': 'uniswap_v3',  # Permit2

        # PancakeSwap V2
        '0x10ed43c718714eb63d5aa57b78b54704e256024e': 'pancakeswap_v2',  # BSC
        '0xeff92a263d31888d860bd50809a8d171709b7b1c': 'pancakeswap_v2',  # ETH

        # PancakeSwap V3
        '0x13f4ea83d0bd40e75c8222255bc855a974568dd4': 'pancakeswap_v3',

        # SushiSwap
        '0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f': 'sushiswap_v2',  # Ethereum
        '0x1b02da8cb0d097eb8d57a175b88c7d8b47997506': 'sushiswap_v2',  # BSC

        # 1inch Routers
        '0x1111111254eeb25477b68fb85ed929f73a960582': '1inch_v5',  # V5 Router
        '0x1111111254fb6c44bac0bed2854e76f90643097d': '1inch_v4',  # V4 Router
        '0x11111112542d85b3ef69ae05771c2dccff4faa26': '1inch_v3',  # V3 Router
        '0x111111125421ca6dc452d289314280a0f8842a65': '1inch_v5',  # V6 Router

        # 0x Exchange
        '0xdef1c0ded9bec7f1a1670819833240f027b25eff': '0x_v4',  # V4 Exchange Proxy
        '0x61935cbdd02287b511119ddb11aeb42f1593b7ef': '0x_v3',  # V3 Exchange Proxy

        # Curve Finance
        '0x8e764bc2e8b16f2c028c2e115a0363d91ae37f2f': 'curve',  # Old Router
        '0xf0d4c12a5768d806021f80a262b4d39d26c58b8d': 'curve',  # New Router
        '0x99a58482bd75cbab83b27ec03ca68ff489b5788f': 'curve',  # Router NG

        # Balancer V2
        '0xba12222222228d8ba445958a75a0704d566bf2c8': 'balancer_v2',  # Vault

        # Kyber Network
        '0x6131b5fae19ea4f9d964eac0408e4408b66337b5': 'kyber',  # Classic Router
        '0x1c87257f5e8609940bc751a07bb085bb7f8cdbe6': 'kyber',  # Aggregation Router
        '0x617dee16b86534a5d792a4d7a62fb491b544111e': 'kyber',  # Meta Aggregation Router

        # Matcha (0x API)
        '0xdef1c0ded9bec7f1a1670819833240f027b25eff': 'matcha',  # Same as 0x V4

        # ParaSwap
        '0xdef171fe48cf0115b1d80b88dc8eab59176fee57': 'paraswap_v5',  # Augustus V5
        '0x216b4b4ba9f3e719726886d34a177484278bfcae': 'paraswap_v5',  # Augustus V6

        # OpenOcean
        '0x6352a56caadc4f1e25cd6c75970fa768a3304e64': 'openocean',  # Ethereum Router

        # DODO
        '0xa356867fdcea8e71aeaf87805808803806231fdc': 'dodo_v2',  # V2 Proxy
        '0x8f8dd7db1bda5ed3da8c9daf3bfa471c12d58486': 'dodo_v1',  # V1 Proxy

        # CoW Protocol (MEV Protection)
        '0x9008d19f58aabd9ed0d60971565aa8510560ab41': 'cow_protocol',

        # MetaMask Swap Router
        '0x881d40237659c251811cec9c364ef91dc08d300c': 'metamask_swap',

        # Banana Gun (Popular trading bot)
        '0x3328f7f4a1d1c57c35df56bbf0c9dcafca309c49': 'banana_gun',

        # Maestro (Trading bot)
        '0x80a64c6d7f12c47b7c66c5b4e20e72bc1fcd5d9e': 'maestro',
    }

    # Non-swap function selectors (to filter out)
    NON_SWAP_SELECTORS = {
        '0x095ea7b3',  # approve
        '0xe8e33700',  # addLiquidity
        '0xbaa2abde',  # removeLiquidity
        '0x4515cef3',  # addLiquidityETH
        '0x02751cec',  # removeLiquidityETH
    }

    # Stablecoin addresses (for action classification)
    STABLECOINS = {
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
        '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
        '0x4fabb145d64652a948d72533023f6e7a623c7c53',  # BUSD
    }

    WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

    # Minimal ABIs for event decoding
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "from", "type": "address"},
                {"indexed": True, "name": "to", "type": "address"},
                {"indexed": False, "name": "value", "type": "uint256"}
            ],
            "name": "Transfer",
            "type": "event"
        }
    ]

    V2_SWAP_EVENT_ABI = [{
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "sender", "type": "address"},
            {"indexed": False, "name": "amount0In", "type": "uint256"},
            {"indexed": False, "name": "amount1In", "type": "uint256"},
            {"indexed": False, "name": "amount0Out", "type": "uint256"},
            {"indexed": False, "name": "amount1Out", "type": "uint256"},
            {"indexed": True, "name": "to", "type": "address"}
        ],
        "name": "Swap",
        "type": "event"
    }]

    V3_SWAP_EVENT_ABI = [{
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "sender", "type": "address"},
            {"indexed": True, "name": "recipient", "type": "address"},
            {"indexed": False, "name": "amount0", "type": "int256"},
            {"indexed": False, "name": "amount1", "type": "int256"},
            {"indexed": False, "name": "sqrtPriceX96", "type": "uint160"},
            {"indexed": False, "name": "liquidity", "type": "uint128"},
            {"indexed": False, "name": "tick", "type": "int24"}
        ],
        "name": "Swap",
        "type": "event"
    }]

    PAIR_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        }
    ]

    def __init__(
        self,
        w3: Optional[Web3] = None,
        etherscan_api_key: Optional[str] = None,
        coingecko_api_key: Optional[str] = None,
        rpc_providers: Optional[List[str]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize DEX parser with RPC fallback support.

        Args:
            w3: Web3 instance connected to Ethereum/BSC node (optional if rpc_providers given)
            etherscan_api_key: Optional Etherscan API key for contract verification
            coingecko_api_key: Optional CoinGecko API key for price data
            rpc_providers: List of RPC provider URLs for fallback
            max_retries: Maximum retries per provider before rotating
            retry_delay: Base delay between retries (exponential backoff)
        """
        # RPC provider management
        self.rpc_providers = rpc_providers or self.DEFAULT_RPC_PROVIDERS.copy()
        self.current_provider_index = 0
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.provider_failures: Dict[str, int] = {}  # Track failures per provider

        # Initialize Web3 with first provider or use provided instance
        if w3 is not None:
            self.w3 = w3
            # Add the provided w3 provider to our list if not already there
            if hasattr(w3.provider, 'endpoint_uri'):
                provider_uri = w3.provider.endpoint_uri
                if provider_uri and provider_uri not in self.rpc_providers:
                    self.rpc_providers.insert(0, provider_uri)
        else:
            self._connect_to_provider(0)

        self.etherscan_api_key = etherscan_api_key
        self.coingecko_api_key = coingecko_api_key

        # Caches
        self.token_cache: Dict[str, TokenInfo] = {}
        self.pair_cache: Dict[str, Tuple[str, str]] = {}  # pair → (token0, token1)
        self.price_cache: Dict[str, Tuple[float, datetime]] = {}  # token → (price, timestamp)

        # Rate limiting
        self.last_coingecko_call = 0
        self.coingecko_rate_limit = 1.2  # 50 calls/min = 1 call per 1.2s

        logger.info(f"DexParser initialized with {len(self.rpc_providers)} RPC providers")
        logger.debug(f"Primary RPC: {self.rpc_providers[0]}")

    def _connect_to_provider(self, index: int) -> bool:
        """
        Connect to RPC provider at given index.

        Args:
            index: Index in rpc_providers list

        Returns:
            bool: True if connection successful
        """
        if index >= len(self.rpc_providers):
            logger.error("No more RPC providers available")
            return False

        provider_url = self.rpc_providers[index]
        try:
            self.w3 = Web3(Web3.HTTPProvider(
                provider_url,
                request_kwargs={'timeout': 30}
            ))
            self.current_provider_index = index

            # Test connection
            if self.w3.is_connected():
                logger.info(f"Connected to RPC provider: {provider_url}")
                return True
            else:
                logger.warning(f"Failed to connect to {provider_url}")
                return False

        except Exception as e:
            logger.warning(f"Error connecting to {provider_url}: {e}")
            return False

    def _rotate_provider(self) -> bool:
        """
        Rotate to next RPC provider.

        Returns:
            bool: True if successfully rotated to new provider
        """
        # Mark current provider as failed
        current_url = self.rpc_providers[self.current_provider_index]
        self.provider_failures[current_url] = self.provider_failures.get(current_url, 0) + 1

        # Try next providers
        for i in range(len(self.rpc_providers)):
            next_index = (self.current_provider_index + 1 + i) % len(self.rpc_providers)
            if self._connect_to_provider(next_index):
                return True

        logger.error("All RPC providers failed")
        return False

    def _execute_with_retry(self, func, *args, **kwargs):
        """
        Execute a Web3 function with retry and provider rotation.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of function call

        Raises:
            Exception: If all retries and providers exhausted
        """
        last_error = None
        providers_tried = 0

        while providers_tried < len(self.rpc_providers):
            for attempt in range(self.max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()

                    # Check if it's a retryable error
                    is_retryable = any(err in error_msg for err in [
                        '500', '502', '503', '504',  # Server errors
                        'timeout', 'timed out',
                        'connection', 'network',
                        'rate limit', 'too many requests',
                        'internal server error'
                    ])

                    if is_retryable and attempt < self.max_retries - 1:
                        # Exponential backoff
                        delay = self.retry_delay * (2 ** attempt)
                        logger.debug(f"Retry {attempt + 1}/{self.max_retries} after {delay:.1f}s: {e}")
                        time.sleep(delay)
                        continue
                    elif is_retryable:
                        # Max retries reached, try next provider
                        break
                    else:
                        # Non-retryable error (e.g., transaction not found)
                        raise e

            # Rotate to next provider
            providers_tried += 1
            if providers_tried < len(self.rpc_providers):
                logger.warning(f"Rotating RPC provider after failures")
                if not self._rotate_provider():
                    break

        # All providers failed
        raise last_error if last_error else Exception("All RPC providers exhausted")

    # ========================================================================
    # MAIN ENTRY POINT
    # ========================================================================

    def parse_transaction(
        self,
        tx_hash: str,
        wallet_address: str
    ) -> Optional[SwapInfo]:
        """
        Parse a transaction and extract swap information.

        Args:
            tx_hash: Transaction hash
            wallet_address: Address of wallet being monitored

        Returns:
            SwapInfo if valid swap detected, None otherwise
        """
        try:
            # Fetch transaction and receipt with retry
            tx = self._execute_with_retry(self.w3.eth.get_transaction, tx_hash)
            receipt = self._execute_with_retry(self.w3.eth.get_transaction_receipt, tx_hash)

            # Check if successful
            if receipt.status != 1:
                logger.debug(f"Transaction {tx_hash[:10]}... failed (status=0)")
                return None

            # Check if router transaction
            router_type = self._get_router_type(tx.to)
            if not router_type:
                logger.debug(f"Transaction {tx_hash[:10]}... not to known router")
                return None

            # Check if actually a swap (not approval/liquidity)
            if not self._is_swap_transaction(tx, receipt):
                logger.debug(f"Transaction {tx_hash[:10]}... not a swap")
                return None

            # Route to appropriate parser
            # Aggregators (1inch, 0x, MetaMask, etc.) route through V2/V3 pools
            # so we try both parsers
            if 'v2' in router_type:
                return self._parse_v2_swap(tx, receipt, wallet_address, router_type)
            elif 'v3' in router_type:
                return self._parse_v3_swap(tx, receipt, wallet_address, router_type)
            else:
                # For aggregators and other protocols, try V3 first then V2
                # They emit standard Uniswap Swap events from the pools they route through
                result = self._parse_v3_swap(tx, receipt, wallet_address, router_type)
                if result:
                    return result
                result = self._parse_v2_swap(tx, receipt, wallet_address, router_type)
                if result:
                    return result
                logger.debug(f"No swap events found for {router_type} transaction")
                return None

        except TransactionNotFound:
            # Expected: old transactions not available in RPC provider
            logger.debug(f"Transaction {tx_hash[:10]}... not found in RPC (old tx)")
            return None
        except (ValueError, AttributeError) as e:
            # Expected errors: receipt not available, null values for old txs
            error_msg = str(e).lower()
            if 'not found' in error_msg or 'none' in error_msg:
                logger.debug(f"Transaction {tx_hash[:10]}... not available in RPC (likely old)")
                return None
            else:
                logger.error(f"Error parsing transaction {tx_hash}: {e}")
                return None
        except Exception as e:
            # Unexpected errors
            logger.warning(f"Unexpected error parsing {tx_hash[:10]}...: {e}")
            return None

    # ========================================================================
    # UNISWAP V2 PARSER
    # ========================================================================

    def _parse_v2_swap(
        self,
        tx: TxData,
        receipt: TxReceipt,
        wallet_address: str,
        router_type: str
    ) -> Optional[SwapInfo]:
        """
        Parse Uniswap V2 style swap.

        Returns:
            SwapInfo if valid swap, None otherwise
        """
        # Find Swap event in logs
        swap_log = self._find_event_in_logs(receipt.logs, self.V2_SWAP_TOPIC)
        if not swap_log:
            logger.debug("No V2 Swap event found in logs")
            return None

        try:
            # Decode event
            event_contract = self.w3.eth.contract(abi=self.V2_SWAP_EVENT_ABI)
            decoded = event_contract.events.Swap().processLog(swap_log)

            amount0In = decoded['args']['amount0In']
            amount1In = decoded['args']['amount1In']
            amount0Out = decoded['args']['amount0Out']
            amount1Out = decoded['args']['amount1Out']
            to_address = decoded['args']['to']

            # Get token addresses from pair
            pair_address = swap_log.address
            token0, token1 = self._get_pair_tokens(pair_address)

            # Determine swap direction
            if amount0In > 0 and amount1Out > 0:
                # Swapping token0 → token1
                token_in = token0
                token_out = token1
                amount_in_raw = amount0In
                amount_out_raw = amount1Out
            elif amount1In > 0 and amount0Out > 0:
                # Swapping token1 → token0
                token_in = token1
                token_out = token0
                amount_in_raw = amount1In
                amount_out_raw = amount0Out
            else:
                logger.warning(f"Unexpected V2 swap amounts: {amount0In}/{amount1In} → {amount0Out}/{amount1Out}")
                return None

            # Get token info
            token_in_info = self.get_token_info(token_in)
            token_out_info = self.get_token_info(token_out)

            # Convert to human-readable
            amount_in = amount_in_raw / (10 ** token_in_info.decimals)
            amount_out = amount_out_raw / (10 ** token_out_info.decimals)

            # Calculate USD values
            amount_in_usd = amount_in * token_in_info.price_usd
            amount_out_usd = amount_out * token_out_info.price_usd

            # Parse path from input (for multi-hop detection)
            path = self._extract_path_from_input_v2(tx.input)
            if not path:
                path = [token_in, token_out]

            # Classify action
            action = self._classify_action(token_in, token_out)

            # Get timestamp with retry
            block = self._execute_with_retry(self.w3.eth.get_block, receipt.blockNumber)
            timestamp = datetime.fromtimestamp(block.timestamp)

            return SwapInfo(
                tx_hash=tx.hash.hex(),
                block_number=receipt.blockNumber,
                timestamp=timestamp,
                dex_protocol=router_type,
                router_address=tx.to,
                token_in=token_in,
                token_out=token_out,
                token_in_symbol=token_in_info.symbol,
                token_out_symbol=token_out_info.symbol,
                amount_in=amount_in,
                amount_out=amount_out,
                amount_in_usd=amount_in_usd,
                amount_out_usd=amount_out_usd,
                action=action,
                is_multihop=len(path) > 2,
                path=path,
                wallet_address=wallet_address.lower(),
                recipient_address=to_address.lower()
            )

        except Exception as e:
            logger.error(f"Error decoding V2 swap: {e}")
            return None

    # ========================================================================
    # UNISWAP V3 PARSER
    # ========================================================================

    def _parse_v3_swap(
        self,
        tx: TxData,
        receipt: TxReceipt,
        wallet_address: str,
        router_type: str
    ) -> Optional[SwapInfo]:
        """
        Parse Uniswap V3 style swap.

        Returns:
            SwapInfo if valid swap, None otherwise
        """
        # Find Swap event in logs
        swap_log = self._find_event_in_logs(receipt.logs, self.V3_SWAP_TOPIC)
        if not swap_log:
            logger.debug("No V3 Swap event found in logs")
            return None

        try:
            # Decode event
            event_contract = self.w3.eth.contract(abi=self.V3_SWAP_EVENT_ABI)
            decoded = event_contract.events.Swap().processLog(swap_log)

            amount0 = decoded['args']['amount0']  # int256
            amount1 = decoded['args']['amount1']  # int256
            recipient = decoded['args']['recipient']

            # Extract tokens from function input
            token_in, token_out, path = self._extract_tokens_from_input_v3(tx.input)

            if not token_in or not token_out:
                logger.warning("Could not extract tokens from V3 input")
                return None

            # Get pool tokens to map amounts
            pool_address = swap_log.address
            pool_token0, pool_token1 = self._get_pair_tokens(pool_address)

            # Determine which amount corresponds to which token
            # Positive amount = tokens IN (from user to pool)
            # Negative amount = tokens OUT (from pool to user)
            if token_in.lower() == pool_token0.lower():
                amount_in_raw = abs(amount0) if amount0 > 0 else 0
                amount_out_raw = abs(amount1) if amount1 < 0 else 0
            else:
                amount_in_raw = abs(amount1) if amount1 > 0 else 0
                amount_out_raw = abs(amount0) if amount0 < 0 else 0

            if amount_in_raw == 0 or amount_out_raw == 0:
                logger.warning(f"Unexpected V3 swap amounts: {amount0}/{amount1}")
                return None

            # Get token info
            token_in_info = self.get_token_info(token_in)
            token_out_info = self.get_token_info(token_out)

            # Convert to human-readable
            amount_in = amount_in_raw / (10 ** token_in_info.decimals)
            amount_out = amount_out_raw / (10 ** token_out_info.decimals)

            # Calculate USD values
            amount_in_usd = amount_in * token_in_info.price_usd
            amount_out_usd = amount_out * token_out_info.price_usd

            # Classify action
            action = self._classify_action(token_in, token_out)

            # Get timestamp with retry
            block = self._execute_with_retry(self.w3.eth.get_block, receipt.blockNumber)
            timestamp = datetime.fromtimestamp(block.timestamp)

            return SwapInfo(
                tx_hash=tx.hash.hex(),
                block_number=receipt.blockNumber,
                timestamp=timestamp,
                dex_protocol=router_type,
                router_address=tx.to,
                token_in=token_in,
                token_out=token_out,
                token_in_symbol=token_in_info.symbol,
                token_out_symbol=token_out_info.symbol,
                amount_in=amount_in,
                amount_out=amount_out,
                amount_in_usd=amount_in_usd,
                amount_out_usd=amount_out_usd,
                action=action,
                is_multihop=len(path) > 2,
                path=path,
                wallet_address=wallet_address.lower(),
                recipient_address=recipient.lower()
            )

        except Exception as e:
            logger.error(f"Error decoding V3 swap: {e}")
            return None

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def _get_router_type(self, address: Optional[str]) -> Optional[str]:
        """Check if address is a known DEX router."""
        if not address:
            return None
        return self.KNOWN_ROUTERS.get(address.lower())

    def _is_swap_transaction(self, tx: TxData, receipt: TxReceipt) -> bool:
        """
        Verify this is actually a swap, not approval/liquidity.

        Returns:
            bool: True if swap transaction
        """
        # Check function selector
        if len(tx.input) < 10:
            return False

        selector = tx.input[:10]

        # Filter out non-swap functions
        if selector in self.NON_SWAP_SELECTORS:
            return False

        # Check for Swap event in logs
        has_swap = any(
            log.topics[0].hex() == self.V2_SWAP_TOPIC or
            log.topics[0].hex() == self.V3_SWAP_TOPIC
            for log in receipt.logs
        )

        return has_swap

    def _find_event_in_logs(
        self,
        logs: List[LogReceipt],
        topic0: str
    ) -> Optional[LogReceipt]:
        """Find first log with matching topic[0]."""
        for log in logs:
            if log.topics[0].hex() == topic0:
                return log
        return None

    def _get_pair_tokens(self, pair_address: str) -> Tuple[str, str]:
        """
        Get token0 and token1 from pair/pool contract.

        Returns:
            (token0_address, token1_address)
        """
        pair_address_lower = pair_address.lower()

        # Check cache
        if pair_address_lower in self.pair_cache:
            return self.pair_cache[pair_address_lower]

        try:
            # Query on-chain with retry
            pair_contract = self.w3.eth.contract(
                address=Web3.toChecksumAddress(pair_address),
                abi=self.PAIR_ABI
            )

            token0 = self._execute_with_retry(pair_contract.functions.token0().call).lower()
            token1 = self._execute_with_retry(pair_contract.functions.token1().call).lower()

            # Cache result
            self.pair_cache[pair_address_lower] = (token0, token1)

            return (token0, token1)

        except Exception as e:
            logger.error(f"Failed to get pair tokens for {pair_address}: {e}")
            raise

    def get_token_info(self, address: str) -> TokenInfo:
        """
        Get token symbol, decimals, and price with caching.

        Returns:
            TokenInfo
        """
        address_lower = address.lower()

        # Check cache
        if address_lower in self.token_cache:
            info = self.token_cache[address_lower]
            # Refresh price if older than 5 minutes
            if (datetime.now() - info.last_updated).total_seconds() < 300:
                return info

        # Fetch from blockchain with retry
        try:
            contract = self.w3.eth.contract(
                address=Web3.toChecksumAddress(address),
                abi=self.ERC20_ABI
            )

            symbol = self._execute_with_retry(contract.functions.symbol().call)
            decimals = self._execute_with_retry(contract.functions.decimals().call)

        except Exception as e:
            logger.warning(f"Failed to get token info for {address}: {e}")
            symbol = 'UNKNOWN'
            decimals = 18

        # Get price
        price_usd = self._get_token_price(address_lower, symbol)

        # Create and cache info
        info = TokenInfo(
            address=address_lower,
            symbol=symbol,
            decimals=decimals,
            price_usd=price_usd,
            last_updated=datetime.now()
        )

        self.token_cache[address_lower] = info
        return info

    def _get_token_price(self, address: str, symbol: str) -> float:
        """
        Get USD price for token.

        Strategy:
            1. Check hardcoded prices (WETH, USDC, etc.)
            2. Query CoinGecko API
            3. Fallback: Return 0.0
        """
        # Hardcoded for stablecoins only (WETH removed - fetched from CoinGecko)
        KNOWN_PRICES = {
            '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 1.0,     # USDC
            '0xdac17f958d2ee523a2206206994597c13d831ec7': 1.0,     # USDT
            '0x6b175474e89094c44da98b954eedeac495271d0f': 1.0,     # DAI
            '0x4fabb145d64652a948d72533023f6e7a623c7c53': 1.0,     # BUSD
        }

        address_lower = address.lower()
        if address_lower in KNOWN_PRICES:
            return KNOWN_PRICES[address_lower]

        # Check price cache
        if address_lower in self.price_cache:
            price, cached_at = self.price_cache[address_lower]
            if (datetime.now() - cached_at).total_seconds() < 300:  # 5 min cache
                return price

        # Try CoinGecko
        try:
            price = self._fetch_coingecko_price(address_lower)
            if price > 0:
                self.price_cache[address_lower] = (price, datetime.now())
                return price
        except Exception as e:
            logger.debug(f"CoinGecko price fetch failed for {symbol}: {e}")

        # Fallback
        logger.warning(f"Could not fetch price for {symbol} ({address}), using 0.0")
        return 0.0

    def _fetch_coingecko_price(self, address: str) -> float:
        """Fetch token price from CoinGecko API."""
        # Rate limiting
        time_since_last = time.time() - self.last_coingecko_call
        if time_since_last < self.coingecko_rate_limit:
            time.sleep(self.coingecko_rate_limit - time_since_last)

        url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum"
        params = {
            'contract_addresses': address,
            'vs_currencies': 'usd'
        }

        if self.coingecko_api_key:
            params['x_cg_pro_api_key'] = self.coingecko_api_key

        response = requests.get(url, params=params, timeout=10)
        self.last_coingecko_call = time.time()

        if response.status_code == 200:
            data = response.json()
            if address in data and 'usd' in data[address]:
                return float(data[address]['usd'])

        return 0.0

    def _classify_action(self, token_in: str, token_out: str) -> str:
        """
        Classify swap as BUY or SELL.

        Logic:
            - Selling stablecoin/WETH for token → BUY
            - Selling token for stablecoin/WETH → SELL
            - Otherwise → BUY (acquiring token_out)
        """
        token_in_lower = token_in.lower()
        token_out_lower = token_out.lower()

        # Selling stablecoin/ETH for token = BUY
        if token_in_lower in self.STABLECOINS or token_in_lower == self.WETH:
            return 'BUY'

        # Selling token for stablecoin/ETH = SELL
        if token_out_lower in self.STABLECOINS or token_out_lower == self.WETH:
            return 'SELL'

        # Both tokens: classify as BUY (acquiring token_out)
        return 'BUY'

    def _extract_path_from_input_v2(self, input_data: str) -> List[str]:
        """
        Extract path array from V2 router function input.

        Returns:
            List of token addresses in path
        """
        if len(input_data) < 10:
            return []

        selector = input_data[:10]

        try:
            if selector in {self.V2_SWAP_EXACT_TOKENS, self.V2_SWAP_TOKENS_EXACT}:
                # Decode: (uint256, uint256, address[], address, uint256)
                params = abi_decode(
                    ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                    bytes.fromhex(input_data[10:])
                )
                path = params[2]  # Third parameter is path
                return [addr.lower() for addr in path]

            elif selector == self.V2_SWAP_EXACT_ETH:
                # Decode: (uint256, address[], address, uint256)
                params = abi_decode(
                    ['uint256', 'address[]', 'address', 'uint256'],
                    bytes.fromhex(input_data[10:])
                )
                path = params[1]
                return [addr.lower() for addr in path]

            elif selector == self.V2_SWAP_TOKENS_ETH:
                # Decode: (uint256, uint256, address[], address, uint256)
                params = abi_decode(
                    ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                    bytes.fromhex(input_data[10:])
                )
                path = params[2]
                return [addr.lower() for addr in path]

        except Exception as e:
            logger.debug(f"Could not decode V2 path from input: {e}")

        return []

    def _extract_tokens_from_input_v3(
        self,
        input_data: str
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        Extract token addresses from V3 router function input.

        Returns:
            (token_in, token_out, full_path)
        """
        if len(input_data) < 10:
            return (None, None, [])

        selector = input_data[:10]

        try:
            if selector == self.V3_EXACT_INPUT_SINGLE:
                # Decode struct: (address tokenIn, address tokenOut, uint24 fee, address recipient, uint256 deadline, uint256 amountIn, uint256 amountOutMinimum, uint160 sqrtPriceLimitX96)
                params = abi_decode(
                    ['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint256', 'uint160'],
                    bytes.fromhex(input_data[10:])
                )
                token_in = params[0].lower()
                token_out = params[1].lower()
                return (token_in, token_out, [token_in, token_out])

            elif selector == self.V3_EXACT_INPUT:
                # Decode struct: (bytes path, address recipient, uint256 deadline, uint256 amountIn, uint256 amountOutMinimum)
                params = abi_decode(
                    ['bytes', 'address', 'uint256', 'uint256', 'uint256'],
                    bytes.fromhex(input_data[10:])
                )
                path_bytes = params[0]
                path = self._decode_path_v3(path_bytes)
                if len(path) >= 2:
                    return (path[0], path[-1], path)

            elif selector == self.V3_EXACT_OUTPUT_SINGLE:
                # Similar to exactInputSingle
                params = abi_decode(
                    ['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint256', 'uint160'],
                    bytes.fromhex(input_data[10:])
                )
                token_in = params[0].lower()
                token_out = params[1].lower()
                return (token_in, token_out, [token_in, token_out])

            elif selector == self.V3_EXACT_OUTPUT:
                # Similar to exactInput
                params = abi_decode(
                    ['bytes', 'address', 'uint256', 'uint256', 'uint256'],
                    bytes.fromhex(input_data[10:])
                )
                path_bytes = params[0]
                path = self._decode_path_v3(path_bytes)
                if len(path) >= 2:
                    # For exactOutput, path is reversed
                    return (path[-1], path[0], list(reversed(path)))

        except Exception as e:
            logger.debug(f"Could not decode V3 tokens from input: {e}")

        return (None, None, [])

    def _decode_path_v3(self, path_bytes: bytes) -> List[str]:
        """
        Decode Uniswap V3 path.

        Format: abi.encodePacked(tokenA, fee, tokenB, fee, tokenC)
        - Token address: 20 bytes
        - Fee: 3 bytes (uint24)

        Returns:
            List of token addresses
        """
        tokens = []
        offset = 0

        while offset < len(path_bytes):
            # Extract token address (20 bytes)
            if offset + 20 > len(path_bytes):
                break

            token = '0x' + path_bytes[offset:offset+20].hex()
            tokens.append(token.lower())
            offset += 20

            # Skip fee (3 bytes) if not at end
            if offset < len(path_bytes):
                offset += 3

        return tokens
