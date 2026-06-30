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

    🚕 <u><i>Cash delivery</i></u> — we’ll deliver cash to a place convenient for you.
    🏧 <u><i>Cash by QR</i></u> — withdraw cash from an ATM using a QR code.
    💳 <u><i>Transfer</i></u> — we’ll send funds to a local bank account.
    🧰 <u><i>Service payments</i></u> — we’ll help pay for the services you need.
exchange-choose-city = Choose a cash-delivery city
menu-orders = 📋 My orders
menu-new-site-leads = 🆕 New requests
menu-rate-header = 🏦 Current rate:
home-title =
    🏠 Main menu

    Choose what you want to do:
bot-disabled = ⚠️ Bot is temporarily unavailable. Please try again later.
bot-turned-on = ✅ Bot enabled.
bot-turned-off = 🔴 Bot disabled.

## FSM — exchange flow
exchange-step = Step { $current }/{ $total }
exchange-choose-currency = Choose the currency you want to exchange.
exchange-choose-buy-currency = Choose what you want to receive for { $currency }:
exchange-enter-amount = <b>Enter the amount you want to exchange in { $currency }:</b>
exchange-enter-amount-with-min = <b>Enter the amount you want to exchange in { $currency }:</b>
    ⚠️ Minimum amount: <b>{ $minAmount } { $minCurrency }</b>
exchange-amount-invalid = Enter an amount greater than zero.
exchange-amount-below-minimum = The amount must be at least { $minAmount }. Enter a valid amount for this receive method.
exchange-choose-method = How would you like to receive { $currency }?
exchange-rate-unavailable = ⚠️ Exchange rate is temporarily unavailable. Please try again later.
exchange-confirm-summary-top = 📋 Review your order — step { $current }/{ $total }
exchange-confirm-summary-bottom = If everything is correct, press “Confirm”.
exchange-summary-country = Country
exchange-summary-city = City
exchange-summary-rate = Rate
exchange-summary-sell = You send
exchange-summary-buy = You receive
exchange-summary-method = Receive method
manager-summary-user = User

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
orders-item-rate-label = Rate
orders-item-method-label = Payout method
orders-item-status-created = New
orders-item-status-processing = In progress
orders-item-status-completed = Completed
orders-item-status-cancelled = Cancelled
orders-item-method-cash = Cash delivery
orders-item-method-qrcode = Cash by QR
orders-item-method-bank-account = Transfer to a local bank account
orders-item-method-pay-services = Service payment

## Manager
manager-new-orders-header = 🆕 New exchange requests:
manager-new-orders-empty = 📭 No new exchange requests.
manager-access-denied = Access denied.

## Order statuses
order-created = ✅ Order #{ $id } created. Please wait for confirmation.
order-creation-failed = Could not create the order right now. Please try again in a minute.
order-creation-limit-reached = You already have too many active orders. Please wait for the current ones to be processed.
order-confirmed = ✅ Order #{ $id } is now being processed by the manager.
order-completed = ✅ Order #{ $id } completed.

    Direction: { $direction }
    Amount: { $amount } { $currency }

    { $city }

    The exchange has been completed successfully.
order-completed-top = 🎉 Order #{ $id } completed successfully.
order-completed-bottom = Thanks for using our service! If you have a minute, we’d love your review.
order-cancelled = ❌ Order #{ $id } cancelled.
manager-chat-open-text = Hello! You had left order #{ $id } for exchanging { $amount } { $currency }. Are you ready to continue?
user-chat-open-text = Hello! For order #{ $id } in the amount of { $amount } { $currency }, I confirm I’m ready to exchange.
referral-bonus-credited = 🎁 { $amount } AEX credited for order #{ $order_id }.
referral-bonus-reversed = 💸 { $amount } AEX deducted for cancelled order #{ $order_id }.
