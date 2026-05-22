## Main menu
welcome = 👋 Hello, { $name }!
menu-exchange = 💱 New exchange
menu-orders = 📋 My orders
menu-rate-header = 📊 Available pairs:
menu-rate-info =
    📊 Current rate:
    • 1 RUB = { $rub_rate } THB
    • 1 USDT = { $usdt_rate } THB
    🕐 Updated: { $updated_at }
home-title = 🏠 Main menu
bot-disabled = ⚠️ Bot is temporarily unavailable. Please try again later.
bot-turned-on = ✅ Bot enabled.
bot-turned-off = 🔴 Bot disabled.

## FSM — exchange flow
exchange-step = Step { $current } of { $total }
exchange-choose-currency = Choose the currency to exchange:
exchange-choose-buy-currency = Choose what to receive for { $currency }:
exchange-enter-amount = Enter the amount in { $currency }:
exchange-amount-invalid = ❌ Invalid amount. Enter a number greater than 0.
exchange-choose-method = How would you like to receive { $currency }?
exchange-rate-unavailable = ⚠️ Exchange rate is temporarily unavailable. Please try again later.
exchange-confirm-summary =
    📋 Confirm order — step { $current }/{ $total }

    You send:    { $amount } { $from_currency }
    You receive: { $result } { $to_currency }
    Method:      { $method }

## Buttons
btn-confirm = ✅ Confirm
btn-cancel = ❌ Cancel
btn-back = ◀ Back
btn-home = 🏠 Main menu
btn-qr = 📱 QR code
btn-transfer = 🏦 Transfer
btn-cash = 💵 Cash
btn-wallet = 👛 Wallet
btn-card = 💳 Card
btn-cancel-order = ❌ Cancel
btn-confirm-cancel-order = ❌ Confirm cancel
btn-keep-order = ✅ Keep order
btn-take-order = ✅ Take order
btn-open-chat = 💬 Open chat
btn-write-manager = 💬 Write manager
btn-close-order = ✅ Close order
btn-leave-review = ⭐ Leave a review
btn-rub-thb = 🇷🇺 RUB → THB
btn-usdt-thb = 💎 USDT → THB
menu-open-site = 🚀 Open site

## Orders
orders-header = 📋 Your orders:
orders-empty = 📭 You have no orders yet.
orders-item = #{ $id }: { $amount_sell } { $currency_sell } → { $amount_buy } { $currency_buy }

## Order statuses
order-created = ✅ Order #{ $id } created. Please wait for confirmation.
order-confirmed = ✅ Order #{ $id } is now being processed by the manager.
order-cancelled = ❌ Order #{ $id } cancelled.
order-completed = 🎉 Order #{ $id } completed. Thank you! You can leave a review if you want.
