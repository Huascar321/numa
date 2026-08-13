# Design

BUY_USDT = BOB paid / USDT received; SELL_USDT = BOB received / USDT sold.
Store side, offer context, limits/liquidity, payment method, fees, source, and
observed_at. Manual quotes are mandatory; provider abstraction SHOULD exist.
Binance P2P adapter is **UNVERIFIED** and **OPTIONAL**, never sole provider.
