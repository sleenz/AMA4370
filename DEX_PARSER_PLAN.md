# DEX Parser Implementation Plan

Detailed step-by-step plan for implementing dex_parser.py

## Architecture Overview

```
DexParser
├── Initialization
│   ├── Web3 connection
│   ├── Token cache (address → symbol/decimals)
│   └── Price cache (address → USD price)
│
├── Main Entry Point
│   └── parse_transaction(tx_hash) → SwapInfo | None
│
├── V2 Parsing Pipeline
│   ├── detect_v2_swap(receipt)
│   ├── decode_v2_swap_event(log)
│   ├── get_v2_token_addresses(pair_address)
│   └── determine_v2_direction(amounts, tokens)
│
├── V3 Parsing Pipeline
│   ├── detect_v3_swap(receipt)
│   ├── decode_v3_swap_event(log)
│   ├── extract_v3_tokens_from_input(input_data)
│   └── determine_v3_direction(amount0, amount1)
│
├── Helper Functions
│   ├── get_token_symbol(address)
│   ├── get_token_decimals(address)
│   ├── calculate_usd_value(token, amount)
│   └── parse_transfer_events(logs)
│
└── Utilities
    ├── decode_path_v3(path_bytes)
    ├── is_router_transaction(to_address)
    └── classify_action(token_in, token_out)
```

---

## Data Structures

### SwapInfo (Output)
```python
@dataclass
class SwapInfo:
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
    action: str  # 'BUY' or 'SELL' (relative to token_out)

    # Multi-hop info
    is_multihop: bool
    path: List[str]  # Full token path

    # Wallet info
    wallet_address: str
    recipient_address: str  # May differ from sender
```

### TokenInfo (Cache)
```python
@dataclass
class TokenInfo:
    address: str
    symbol: str
    decimals: int
    price_usd: float
    last_updated: datetime
```

---

## Implementation Steps

### Step 1: Setup and Initialization

```python
class DexParser:
    def __init__(self, w3: Web3, etherscan_api_key: str):
        self.w3 = w3
        self.api_key = etherscan_api_key

        # Caches
        self.token_cache: Dict[str, TokenInfo] = {}
        self.pair_cache: Dict[str, Tuple[str, str]] = {}  # pair → (token0, token1)

        # Constants
        self.KNOWN_ROUTERS = {...}
        self.V2_SWAP_TOPIC = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
        self.V3_SWAP_TOPIC = '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67'
        self.TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        # ABIs (minimal for event decoding)
        self.v2_swap_abi = [...]
        self.v3_swap_abi = [...]
        self.erc20_abi = [...]
```

**Rationale**:
- Web3 connection for on-chain queries (token decimals, pair info)
- Caching to minimize API calls
- Constants for event signature matching

---

### Step 2: Main Entry Point

```python
def parse_transaction(
    self,
    tx_hash: str,
    wallet_address: str
) -> Optional[SwapInfo]:
    """
    Main entry point for parsing a transaction.

    Returns:
        SwapInfo if valid swap detected, None otherwise
    """
    try:
        # Fetch transaction and receipt
        tx = self.w3.eth.get_transaction(tx_hash)
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)

        # Check if successful
        if receipt.status != 1:
            return None

        # Check if router transaction
        router_type = self.is_router_transaction(tx.to)
        if not router_type:
            return None

        # Route to appropriate parser
        if 'v2' in router_type:
            return self.parse_v2_swap(tx, receipt, wallet_address)
        elif 'v3' in router_type:
            return self.parse_v3_swap(tx, receipt, wallet_address)
        else:
            return None

    except Exception as e:
        logger.error(f"Error parsing tx {tx_hash}: {e}")
        return None
```

**Flow**:
1. Fetch transaction + receipt from blockchain
2. Validate success status
3. Check if interacting with known router
4. Route to V2 or V3 parser

---

### Step 3: Uniswap V2 Parser

```python
def parse_v2_swap(
    self,
    tx: TxData,
    receipt: TxReceipt,
    wallet_address: str
) -> Optional[SwapInfo]:
    """
    Parse Uniswap V2 style swap.

    Strategy:
        1. Find Swap event in logs
        2. Decode amounts (amount0In, amount1In, amount0Out, amount1Out)
        3. Get token addresses from pair contract
        4. Determine which token was IN and which was OUT
        5. Calculate USD values
    """
    # Find Swap event
    swap_log = self._find_event_in_logs(receipt.logs, self.V2_SWAP_TOPIC)
    if not swap_log:
        return None

    # Decode event
    decoded = self.w3.eth.contract(abi=self.v2_swap_abi).events.Swap().processLog(swap_log)

    amount0In = decoded['args']['amount0In']
    amount1In = decoded['args']['amount1In']
    amount0Out = decoded['args']['amount0Out']
    amount1Out = decoded['args']['amount1Out']

    # Get token addresses
    pair_address = swap_log.address
    token0, token1 = self.get_pair_tokens(pair_address)

    # Determine direction
    if amount0In > 0:
        # Swapping token0 → token1
        token_in = token0
        token_out = token1
        amount_in_raw = amount0In
        amount_out_raw = amount1Out
    else:
        # Swapping token1 → token0
        token_in = token1
        token_out = token0
        amount_in_raw = amount1In
        amount_out_raw = amount0Out

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

    # Classify action
    action = self._classify_action(token_in, token_out)

    return SwapInfo(
        tx_hash=tx.hash,
        block_number=receipt.blockNumber,
        timestamp=datetime.fromtimestamp(self.w3.eth.get_block(receipt.blockNumber).timestamp),
        dex_protocol=self.KNOWN_ROUTERS.get(tx.to.lower(), 'uniswap_v2'),
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
        wallet_address=wallet_address,
        recipient_address=decoded['args']['to']
    )
```

**Key Points**:
- V2 uses uint256 amounts (always positive)
- Exactly one of (amount0In, amount1In) is non-zero
- Exactly one of (amount0Out, amount1Out) is non-zero
- Token0 < Token1 (alphabetically sorted addresses)

---

### Step 4: Uniswap V3 Parser

```python
def parse_v3_swap(
    self,
    tx: TxData,
    receipt: TxReceipt,
    wallet_address: str
) -> Optional[SwapInfo]:
    """
    Parse Uniswap V3 style swap.

    Strategy:
        1. Find Swap event in logs
        2. Decode amounts (int256, can be negative)
        3. Extract tokens from function input (easier than querying pool)
        4. Determine direction from sign of amounts
        5. Calculate USD values
    """
    # Find Swap event
    swap_log = self._find_event_in_logs(receipt.logs, self.V3_SWAP_TOPIC)
    if not swap_log:
        return None

    # Decode event
    decoded = self.w3.eth.contract(abi=self.v3_swap_abi).events.Swap().processLog(swap_log)

    amount0 = decoded['args']['amount0']  # int256
    amount1 = decoded['args']['amount1']  # int256

    # Extract tokens from function input
    token_in, token_out, path = self._extract_tokens_from_input_v3(tx.input)

    # Determine which amount corresponds to which token
    # Note: token0 and token1 in pool are sorted alphabetically
    pool_address = swap_log.address
    pool_token0, pool_token1 = self.get_pair_tokens(pool_address)

    # Map amounts to tokens
    if token_in.lower() == pool_token0.lower():
        amount_in_raw = abs(amount0) if amount0 > 0 else 0
        amount_out_raw = abs(amount1) if amount1 < 0 else 0
    else:
        amount_in_raw = abs(amount1) if amount1 > 0 else 0
        amount_out_raw = abs(amount0) if amount0 < 0 else 0

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

    return SwapInfo(
        tx_hash=tx.hash,
        block_number=receipt.blockNumber,
        timestamp=datetime.fromtimestamp(self.w3.eth.get_block(receipt.blockNumber).timestamp),
        dex_protocol=self.KNOWN_ROUTERS.get(tx.to.lower(), 'uniswap_v3'),
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
        wallet_address=wallet_address,
        recipient_address=decoded['args']['recipient']
    )
```

**Key Points**:
- V3 uses int256 amounts (can be negative)
- Negative = tokens leaving pool (user receiving)
- Positive = tokens entering pool (user sending)
- Must decode function input to get token addresses

---

### Step 5: Helper Functions

#### Token Info Retrieval
```python
def get_token_info(self, address: str) -> TokenInfo:
    """Get token symbol, decimals, and price with caching."""
    address = address.lower()

    # Check cache
    if address in self.token_cache:
        info = self.token_cache[address]
        # Refresh price if older than 5 minutes
        if (datetime.now() - info.last_updated).seconds < 300:
            return info

    # Fetch from blockchain
    contract = self.w3.eth.contract(address=Web3.toChecksumAddress(address), abi=self.erc20_abi)

    try:
        symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
    except Exception as e:
        logger.warning(f"Failed to get token info for {address}: {e}")
        symbol = 'UNKNOWN'
        decimals = 18

    # Get price from CoinGecko or cache
    price_usd = self.get_token_price(address, symbol)

    info = TokenInfo(
        address=address,
        symbol=symbol,
        decimals=decimals,
        price_usd=price_usd,
        last_updated=datetime.now()
    )

    self.token_cache[address] = info
    return info
```

#### Price Oracle
```python
def get_token_price(self, address: str, symbol: str) -> float:
    """
    Get USD price for token.

    Strategy:
        1. Check hardcoded prices (WETH, USDC, etc.)
        2. Query CoinGecko API
        3. Fallback: Use Uniswap/Chainlink oracle
        4. Last resort: Return 0.0
    """
    # Hardcoded for common tokens
    KNOWN_PRICES = {
        '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': 3400.0,  # WETH
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 1.0,     # USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7': 1.0,     # USDT
        '0x6b175474e89094c44da98b954eedeac495271d0f': 1.0,     # DAI
    }

    address_lower = address.lower()
    if address_lower in KNOWN_PRICES:
        return KNOWN_PRICES[address_lower]

    # Try CoinGecko
    try:
        price = self._fetch_coingecko_price(address)
        if price > 0:
            return price
    except:
        pass

    # Fallback
    logger.warning(f"Could not fetch price for {symbol} ({address}), using 0.0")
    return 0.0
```

#### Action Classification
```python
def _classify_action(self, token_in: str, token_out: str) -> str:
    """
    Classify swap as BUY or SELL.

    Logic:
        - If selling stablecoin for token → BUY
        - If selling token for stablecoin → SELL
        - If both are tokens → BUY (relative to token_out)
    """
    STABLECOINS = {
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
        '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
        '0x4fabb145d64652a948d72533023f6e7a623c7c53',  # BUSD
    }

    WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

    token_in_lower = token_in.lower()
    token_out_lower = token_out.lower()

    # Selling stablecoin/ETH for token = BUY
    if token_in_lower in STABLECOINS or token_in_lower == WETH:
        return 'BUY'

    # Selling token for stablecoin/ETH = SELL
    if token_out_lower in STABLECOINS or token_out_lower == WETH:
        return 'SELL'

    # Both tokens: classify as BUY (acquiring token_out)
    return 'BUY'
```

---

### Step 6: Path Decoding (Multi-hop)

#### V2 Path Extraction
```python
def _extract_path_from_input_v2(self, input_data: str) -> List[str]:
    """
    Extract path array from V2 router function input.

    Example input for swapExactTokensForTokens:
        0x38ed1739  # function selector
        [amountIn]
        [amountOutMin]
        [path offset]
        [to]
        [deadline]
        [path length]
        [token1]
        [token2]
        [token3]
    """
    try:
        # Decode using web3
        # This requires knowing the function signature
        selector = input_data[:10]

        if selector == '0x38ed1739':  # swapExactTokensForTokens
            # Decode parameters
            decoded = self.w3.eth.codec.decode_abi(
                ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                bytes.fromhex(input_data[10:])
            )
            path = decoded[2]  # Third parameter is path
            return [addr.lower() for addr in path]

        # Add other function selectors as needed

    except Exception as e:
        logger.debug(f"Could not decode path from input: {e}")

    return []
```

#### V3 Path Extraction
```python
def _decode_path_v3(self, path_bytes: bytes) -> List[str]:
    """
    Decode Uniswap V3 path.

    Format: abi.encodePacked(tokenA, fee, tokenB, fee, tokenC)

    Structure:
        - Token address: 20 bytes
        - Fee: 3 bytes (uint24)
        - Total per hop: 23 bytes

    Example: tokenA (20) + fee (3) + tokenB (20) + fee (3) + tokenC (20) = 66 bytes
    """
    tokens = []
    offset = 0

    while offset < len(path_bytes):
        # Extract token address (20 bytes)
        token = '0x' + path_bytes[offset:offset+20].hex()
        tokens.append(token.lower())
        offset += 20

        # Skip fee (3 bytes) if not at end
        if offset < len(path_bytes):
            offset += 3

    return tokens
```

---

### Step 7: Edge Case Handling

```python
def _is_swap_transaction(self, tx: TxData, receipt: TxReceipt) -> bool:
    """
    Verify this is actually a swap, not approval/liquidity.

    Checks:
        1. Has Swap event in logs
        2. Function selector is swap-related
        3. Not an approval (0x095ea7b3)
        4. Not add/remove liquidity
    """
    # Check function selector
    selector = tx.input[:10]

    NON_SWAP_SELECTORS = {
        '0x095ea7b3',  # approve
        '0xe8e33700',  # addLiquidity
        '0xbaa2abde',  # removeLiquidity
        '0x4515cef3',  # addLiquidityETH
        '0x02751cec',  # removeLiquidityETH
    }

    if selector in NON_SWAP_SELECTORS:
        return False

    # Check for Swap event
    has_swap = any(
        log.topics[0].hex() in {self.V2_SWAP_TOPIC, self.V3_SWAP_TOPIC}
        for log in receipt.logs
    )

    return has_swap
```

---

## Testing Strategy

### Unit Tests
1. Test event decoding (V2 Swap event)
2. Test event decoding (V3 Swap event)
3. Test path decoding (V2 array)
4. Test path decoding (V3 packed bytes)
5. Test action classification
6. Test token info caching

### Integration Tests
Use real transaction hashes:

```python
REAL_TXS = {
    'uniswap_v2_simple': '0x...',  # TODO: Find real tx
    'uniswap_v2_multihop': '0x...',
    'uniswap_v3_single': '0x...',
    'uniswap_v3_multihop': '0x...',
    'pancakeswap_v2': '0x...',
}
```

### Expected Outputs
For each test transaction, verify:
- Correct DEX protocol detected
- Correct token addresses extracted
- Correct amounts (within 0.01% due to rounding)
- Correct action (BUY/SELL)
- Correct path for multi-hop

---

## Performance Considerations

### Caching Strategy
- **Token Info**: Cache indefinitely (symbol/decimals don't change)
- **Prices**: Cache for 5 minutes
- **Pair Info**: Cache indefinitely

### Rate Limiting
- CoinGecko API: 50 calls/minute (free tier)
- Implement exponential backoff

### Fallback Strategy
1. Try CoinGecko for price
2. Fallback to hardcoded prices for common tokens
3. Last resort: Use $0 and log warning

---

## Integration with trade_monitor.py

Replace the simplified DEXParser in trade_monitor.py:

```python
# OLD (simplified)
class DEXParser:
    def parse_transaction(self, tx: RawTransaction, wallet_address: str) -> Optional[ParsedTrade]:
        # Simple ETH transfer detection
        ...

# NEW (comprehensive)
from dex_parser import DexParser, SwapInfo

class TradeMonitor:
    def __init__(self, ...):
        self.parser = DexParser(w3=Web3(...), etherscan_api_key=config['etherscan_api_key'])

    def check_wallet(self, wallet: WalletState, current_block: int):
        # ... fetch transactions ...

        for tx in transactions:
            # Parse swap
            swap = self.parser.parse_transaction(tx.tx_hash, wallet.address)
            if not swap:
                continue

            # Convert to ParsedTrade
            trade = ParsedTrade(
                tx_hash=swap.tx_hash,
                block_number=swap.block_number,
                timestamp=swap.timestamp,
                wallet_address=swap.wallet_address,
                token_address=swap.token_out,  # Track acquired token
                token_symbol=swap.token_out_symbol,
                action=swap.action,
                amount_usd=swap.amount_out_usd,
                dex_protocol=swap.dex_protocol,
                leverage_multiplier=1  # Leverage detection handled separately
            )

            # ... continue with leverage detection, signal emission ...
```

---

## Next Steps

1. ✅ Document event signatures (DONE - see DEX_SIGNATURES.md)
2. ✅ Plan implementation (DONE - this document)
3. ⏳ Implement dex_parser.py
4. ⏳ Create test_dex_parser.py with real transaction fixtures
5. ⏳ Test with Ethereum mainnet transactions
6. ⏳ Integrate with trade_monitor.py
7. ⏳ End-to-end testing with monitored wallets
