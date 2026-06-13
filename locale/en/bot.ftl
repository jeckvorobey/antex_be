## Main menu
welcome =
    👋 Hello, { $name }!

    I will help you create an exchange order in a few simple steps.
    Tap "New exchange" to start.

exchange-start-welcome =
    👋 Hello, { $name }!

    <b>AntEx</b> is a service that helps you <u>quickly exchange money</u> and pay for the services you need without extra effort.

    📝 To create a request, open the app or choose a country from the list below.

    ☝️ We’ll guide you at every step.
exchange-choose-country = Choose a country
exchange-choose-service =
    <b>💠 Choose the service you need</b>

    🚕 <i>Cash delivery</i> — we’ll deliver cash to a place convenient for you.
    🏧 <i>Cash by QR</i> — withdraw cash from an ATM using a QR code.
    💳 <i>Transfer</i> — we’ll send funds to a local bank account.
    🧰 <i>Service payments</i> — we’ll help pay for the services you need.
exchange-choose-city = Choose a city
menu-orders = 📋 My orders
menu-new-site-leads = 🆕 New requests
menu-rate-header = 💱 Current rate from:
home-title =
    🏠 Main menu

    Choose what you want to do:
bot-disabled = ⚠️ Bot is temporarily unavailable. Please try again later.
bot-turned-on = ✅ Bot enabled.
bot-turned-off = 🔴 Bot disabled.

## FSM — exchange flow
exchange-step = Step { $current }/{ $total }
exchange-choose-currency = What do you send?
exchange-choose-buy-currency = Choose what you want to receive for { $currency }:
exchange-enter-amount = Enter the amount you want to exchange in { $currency }:
exchange-amount-invalid = Enter an amount greater than zero.
exchange-choose-method = How would you like to receive { $currency }?
exchange-rate-unavailable = ⚠️ Exchange rate is temporarily unavailable. Please try again later.
exchange-confirm-summary =
    📋 Review your order — step { $current }/{ $total }

    You send: { $amount } { $from_currency }
    You receive: { $result } { $to_currency }
    Receive method: { $method }

    If everything looks correct, tap "Confirm".

## Buttons
btn-confirm = ✅ Confirm
btn-cancel = ❌ Cancel
btn-back = ◀ Back
btn-service-cash-delivery = 🚕 Cash delivery
btn-service-cash-atm = 🏧 Cash by QR
btn-service-bank-account = 💳 Transfer
btn-service-pay-services = 🧰 Service payments
btn-edit = ✏️ Edit
btn-home-red = 🔴 Back to start
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
menu-open-site = 🚀 Open app

## Orders
orders-header = 📋 Your orders:
orders-empty = 📭 You have no orders yet.
orders-item = #{ $id }: { $amount_sell } { $currency_sell } → { $amount_buy } { $currency_buy }

## Manager
manager-new-orders-header = 🆕 New exchange requests:
manager-new-orders-empty = 📭 No new exchange requests.
manager-access-denied = Access denied.

## Order statuses
order-created = ✅ Order #{ $id } created. Please wait for confirmation.
order-creation-failed = Could not create the order right now. Please try again in a minute.
order-creation-limit-reached = You already have too many active orders. Please wait for the current ones to be processed.
order-confirmed = ✅ Order #{ $id } is now being processed by the manager.
order-cancelled = ❌ Order #{ $id } cancelled.
order-completed = 🎉 Order #{ $id } completed. Thank you! You can leave a review if you want.
