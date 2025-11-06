# DEX Event Signatures and Function Selectors

Comprehensive reference for parsing DEX transactions across multiple protocols.

## Table of Contents
1. [Uniswap V2](#uniswap-v2)
2. [Uniswap V3](#uniswap-v3)
3. [PancakeSwap V2](#pancakeswap-v2)
4. [PancakeSwap V3](#pancakeswap-v3)
5. [Common Events](#common-events)

---

## Uniswap V2

### Event Signatures

#### Swap Event
```solidity
event Swap(
    address indexed sender,
    uint amount0In,
    uint amount1In,
    uint amount0Out,
    uint amount1Out,
    address indexed to
)
```

**Topic0 (keccak256)**: `0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822`

**Indexed Parameters** (in topics):
- `topic[0]`: Event signature hash
- `topic[1]`: sender (address)
- `topic[2]`: to (address)

**Non-indexed Parameters** (in data):
- amount0In (uint256)
- amount1In (uint256)
- amount0Out (uint256)
- amount1Out (uint256)

**Interpretation**:
- If `amount0In > 0`, user is swapping token0 → token1
- If `amount1In > 0`, user is swapping token1 → token0
- Token0 and Token1 are sorted alphabetically by address
- Only one of `amountXIn` will be non-zero (except for multi-hop)

### Function Signatures (Router)

#### swapExactTokensForTokens
```solidity
function swapExactTokensForTokens(
    uint amountIn,
    uint amountOutMin,
    address[] calldata path,
    address to,
    uint deadline
) external returns (uint[] memory amounts)
```
**Function Selector**: `0x38ed1739`

#### swapTokensForExactTokens
```solidity
function swapTokensForExactTokens(
    uint amountOut,
    uint amountInMax,
    address[] calldata path,
    address to,
    uint deadline
) external returns (uint[] memory amounts)
```
**Function Selector**: `0x8803dbee`

#### swapExactETHForTokens
**Function Selector**: `0x7ff36ab5`

#### swapTokensForExactETH
**Function Selector**: `0x4a25d94a`

#### swapExactTokensForETH
**Function Selector**: `0x18cbafe5`

#### swapETHForExactTokens
**Function Selector**: `0xfb3bdb41`

### Router Addresses
- **Ethereum Mainnet**: `0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D`

---

## Uniswap V3

### Event Signatures

#### Swap Event
```solidity
event Swap(
    address indexed sender,
    address indexed recipient,
    int256 amount0,
    int256 amount1,
    uint160 sqrtPriceX96,
    uint128 liquidity,
    int24 tick
)
```

**Topic0 (keccak256)**: `0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67`

**Indexed Parameters** (in topics):
- `topic[0]`: Event signature hash
- `topic[1]`: sender (address)
- `topic[2]`: recipient (address)

**Non-indexed Parameters** (in data):
- amount0 (int256) - can be negative or positive
- amount1 (int256) - can be negative or positive
- sqrtPriceX96 (uint160)
- liquidity (uint128)
- tick (int24)

**Interpretation**:
- Negative amount = tokens leaving the pool (going to user)
- Positive amount = tokens entering the pool (coming from user)
- If `amount0 < 0`, user received token0 (sold token1)
- If `amount1 < 0`, user received token1 (sold token0)

### Function Signatures (SwapRouter)

#### exactInputSingle
```solidity
struct ExactInputSingleParams {
    address tokenIn;
    address tokenOut;
    uint24 fee;
    address recipient;
    uint256 deadline;
    uint256 amountIn;
    uint256 amountOutMinimum;
    uint160 sqrtPriceLimitX96;
}

function exactInputSingle(ExactInputSingleParams calldata params)
    external payable returns (uint256 amountOut)
```
**Function Selector**: `0x414bf389`

#### exactInput (multi-hop)
```solidity
struct ExactInputParams {
    bytes path;
    address recipient;
    uint256 deadline;
    uint256 amountIn;
    uint256 amountOutMinimum;
}

function exactInput(ExactInputParams calldata params)
    external payable returns (uint256 amountOut)
```
**Function Selector**: `0xc04b8d59`

**Path Encoding**: `abi.encodePacked(tokenA, fee, tokenB, fee, tokenC)`

#### exactOutputSingle
```solidity
struct ExactOutputSingleParams {
    address tokenIn;
    address tokenOut;
    uint24 fee;
    address recipient;
    uint256 deadline;
    uint256 amountOut;
    uint256 amountInMaximum;
    uint160 sqrtPriceLimitX96;
}

function exactOutputSingle(ExactOutputSingleParams calldata params)
    external payable returns (uint256 amountIn)
```
**Function Selector**: `0xdb3e2198`

#### exactOutput (multi-hop)
```solidity
struct ExactOutputParams {
    bytes path;
    address recipient;
    uint256 deadline;
    uint256 amountOut;
    uint256 amountInMaximum;
}

function exactOutput(ExactOutputParams calldata params)
    external payable returns (uint256 amountIn)
```
**Function Selector**: `0xf28c0498`

### Router Addresses
- **Ethereum Mainnet (SwapRouter)**: `0xE592427A0AEce92De3Edee1F18E0157C05861564`
- **Ethereum Mainnet (SwapRouter02)**: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`

---

## PancakeSwap V2

PancakeSwap V2 uses **identical signatures to Uniswap V2**.

### Router Addresses
- **BSC Mainnet**: `0x10ED43C718714eb63d5aA57B78B54704E256024E`
- **Ethereum**: `0xEfF92A263d31888d860bD50809A8D171709b7b1c`

### Event Signatures
Same as Uniswap V2 (see above)

### Function Selectors
Same as Uniswap V2 (see above)

---

## PancakeSwap V3

PancakeSwap V3 uses **identical signatures to Uniswap V3**.

### Router Addresses
- **BSC Mainnet (SmartRouter)**: `0x13f4EA83D0bd40E75C8222255bc855a974568Dd4`
- **Ethereum (SmartRouter)**: `0x13f4EA83D0bd40E75C8222255bc855a974568Dd4`

### Event Signatures
Same as Uniswap V3 (see above)

### Function Selectors
Same as Uniswap V3 (see above)

---

## Common Events

### ERC20 Transfer Event
```solidity
event Transfer(
    address indexed from,
    address indexed to,
    uint256 value
)
```

**Topic0 (keccak256)**: `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`

**Usage in DEX Parsing**:
- Track token movements in/out of user wallet
- Identify which tokens were swapped
- Calculate exact amounts transferred

**Indexed Parameters**:
- `topic[0]`: Event signature hash
- `topic[1]`: from (address)
- `topic[2]`: to (address)

**Non-indexed Parameters**:
- value (uint256)

---

## Parsing Strategy

### Step 1: Identify Transaction Type
1. Check input data function selector (first 4 bytes)
2. Match against known router function selectors
3. Determine if V2 or V3 swap

### Step 2: Parse Event Logs
1. Filter logs by Swap event signature (topic[0])
2. Decode indexed parameters from topics
3. Decode non-indexed parameters from data field

### Step 3: Extract Token Addresses
**For Uniswap V2:**
- Call pair contract to get token0 and token1 addresses
- Or parse Transfer events to identify tokens

**For Uniswap V3:**
- Parse function input to extract tokenIn/tokenOut
- Or parse Transfer events

### Step 4: Determine Trade Direction
**For Uniswap V2:**
- If amount0In > 0: Selling token0, buying token1
- If amount1In > 0: Selling token1, buying token0

**For Uniswap V3:**
- If amount0 > 0: User sent token0 (buying token1)
- If amount0 < 0: User received token0 (selling token1)
- Same logic for amount1

### Step 5: Handle Multi-hop Swaps
**Uniswap V2:**
- Parse `path` array from function input
- First element = tokenIn, last element = tokenOut

**Uniswap V3:**
- Decode path bytes: `abi.encodePacked(token0, fee, token1, fee, token2)`
- Extract token addresses at positions: 0, 23, 46, 69, etc.

### Step 6: Calculate USD Value
1. Get token decimals (typically 18, but check)
2. Convert raw amount to human-readable (amount / 10^decimals)
3. Fetch USD price from oracle/cache
4. Calculate: `usd_value = amount * price`

---

## Edge Cases

### Not a Swap
- **Approval**: Function selector `0x095ea7b3` (approve)
- **AddLiquidity**: Function selector `0xe8e33700` (addLiquidity)
- **RemoveLiquidity**: Function selector `0xbaa2abde` (removeLiquidity)
- **Action**: Return None, do not parse

### Failed Transaction
- Check `receipt.status == 1` (success)
- If status == 0, return None

### Zero-value Swaps
- Some protocols emit events for failed swaps
- Check if `amountOut > 0` before processing

### Exotic Tokens
- Fee-on-transfer tokens (e.g., SAFEMOON)
- Actual received amount differs from event amount
- Solution: Parse Transfer events for exact amounts

### Missing Token Data
- Token not in CoinGecko/cache
- Solution: Skip trade or use default price

---

## Router Detection Map

```python
KNOWN_ROUTERS = {
    # Uniswap V2
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d': 'uniswap_v2',

    # Uniswap V3
    '0xe592427a0aece92de3edee1f18e0157c05861564': 'uniswap_v3',
    '0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45': 'uniswap_v3',

    # PancakeSwap V2 (BSC)
    '0x10ed43c718714eb63d5aa57b78b54704e256024e': 'pancakeswap_v2',

    # PancakeSwap V2 (Ethereum)
    '0xeff92a263d31888d860bd50809a8d171709b7b1c': 'pancakeswap_v2',

    # PancakeSwap V3
    '0x13f4ea83d0bd40e75c8222255bc855a974568dd4': 'pancakeswap_v3',
}
```

---

## Testing Transactions

### Uniswap V2 Swap (Ethereum)
- **TX**: `0x...` (TODO: Add real example)
- **Type**: swapExactTokensForTokens
- **Path**: USDC → WETH

### Uniswap V3 Swap (Ethereum)
- **TX**: `0x...` (TODO: Add real example)
- **Type**: exactInputSingle
- **Swap**: USDC → WETH

### Multi-hop Swap (Uniswap V3)
- **TX**: `0x...` (TODO: Add real example)
- **Type**: exactInput
- **Path**: USDC → WETH → DAI

---

## References

- [Uniswap V2 Documentation](https://docs.uniswap.org/contracts/v2)
- [Uniswap V3 Documentation](https://docs.uniswap.org/contracts/v3)
- [PancakeSwap Documentation](https://docs.pancakeswap.finance/)
- [4byte.directory](https://www.4byte.directory/) - Function selector database
- [Ethereum Event Logs](https://github.com/otterscan/topic0) - Event signature database
