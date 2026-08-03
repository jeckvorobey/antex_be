## Main menu
welcome =
    👋 Hello, { $name }!

    I will help you create an exchange order in a few simple steps.
    Tap "New exchange" to start.

exchange-start-greeting = Hello, { $name }!
exchange-start-category = Currency exchange and service payments
exchange-start-title = AntEx
exchange-start-description = Exchange currency and pay for the services you need with fewer steps.
exchange-start-instruction-title = How to get started
exchange-start-instruction = Open the app or choose a country below — we’ll guide you through each step.
manager-working-hours-title = Working hours
manager-requests-anytime = Orders are accepted around the clock.
manager-label = Managers
exchange-start-off-hours-title = We’ll process it in the morning, during working hours
exchange-start-off-hours-text = You can create an order now.
exchange-choose-country = Choose a country
exchange-choose-service-category = Service selection
exchange-choose-service-title = How would you like to receive the money?
exchange-choose-service-description = Choose the option that works best for you — we’ll guide you through the details next.
exchange-choose-service-options-title = Available options
exchange-service-cash-delivery-title = Cash delivery
exchange-service-cash-delivery-description = We’ll bring cash to a convenient location.
exchange-service-cash-atm-title = Cash by QR
exchange-service-cash-atm-description = Withdraw cash from an ATM using a QR code.
exchange-service-bank-account-title = Transfer
exchange-service-bank-account-description = We’ll send the money to a local bank account.
exchange-service-pay-services-title = Service payments
exchange-service-pay-services-description = We’ll help pay for the services you need.
exchange-choose-city-category = Cash delivery
exchange-choose-city-title = Choose a city
exchange-choose-city-description = Choose the city where you would like the cash delivered.
exchange-choose-city-options-title = Available cities
exchange-choose-city-options-hint = Select a city using the buttons below.
exchange-choose-currency-category = Currency selection
exchange-choose-currency-title = Which currency would you like to exchange?
exchange-choose-currency-description = Choose the currency you would like to send.
exchange-choose-currency-rates-title = Current rates
exchange-choose-currency-currency-column = Currency
exchange-choose-currency-rate-column = Rate
exchange-choose-currency-rate-from = from
exchange-choose-currency-options-hint = Select a currency using the buttons below.
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
exchange-off-hours-alert = A manager will process the order in the morning after the working day begins.
exchange-off-hours-confirmation =
    ⚠️ Managers are not working right now.

    The order will be processed in the morning after the working day begins. You can create it now — working hours do not affect order creation.

    Working hours: { $hours }.

    If everything is correct, press “Yes”.
exchange-summary-country = Country
exchange-summary-city = City
exchange-summary-rate = Rate
exchange-summary-sell = You send
exchange-summary-buy = You receive
exchange-summary-method = Receive method
manager-summary-user = User

## Buttons
btn-confirm = ✅ Confirm
btn-yes = ✅ Yes
btn-cancel = ❌ Cancel
btn-cancel-short = ❌ Cancel
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
btn-cancel-order = ❌ Cancel order
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
order-created-offline =
    ✅ Order #{ $id } created. Your request has been accepted.

    <blockquote>A manager will process the order in the morning after the working day begins.</blockquote>
order-creation-failed = Could not create the order right now. Please try again in a minute.
order-created-notification-failed = Order #{ $id } was created, but the confirmation could not be sent. Open “My orders” to check its status.
order-creation-limit-reached = You already have too many active orders. Please wait for the current ones to be processed.
order-confirmed = ✅ Order #{ $id } is now being processed by the manager.
customer-manager-draft = Hello! I’m contacting you about order #{ $id }. I’m ready to continue the exchange.
order-details-caption = Order details
order-country-thailand = Thailand
order-country-vietnam = Vietnam
order-country-georgia = Georgia
order-country-internal = Internal exchange
order-handoff-rich =
    <footer>Order status</footer>
    <h2>✅ Order #{ $id } is being processed</h2>
    <p>The manager is ready to continue the exchange.</p>
    <hr/>
    { $summary }
    <h3>Open the conversation</h3>
    <p>Message the manager first. Once you send a message, the manager can reply and confirm the exchange details.</p>
order-handoff-html =
    <b>✅ Order #{ $id } is being processed</b>

    The manager is ready to continue the exchange.

    { $summary }

    <b>Open the conversation</b>
    Message the manager first. Once you send a message, the manager can reply and confirm the exchange details.
order-reminder-rich =
    <footer>Order reminder</footer>
    <h2>🔔 The manager is waiting for your message about order #{ $id }</h2>
    <p>{ $direction }</p>
    <p>Message the manager first to open the conversation. The manager can then reply and continue the exchange.</p>
order-reminder-html =
    <b>🔔 The manager is waiting for your message about order #{ $id }</b>

    { $direction }

    Message the manager first to open the conversation. The manager can then reply and continue the exchange.
manager-order-card-footer = Order status
manager-order-created-title = 🆕 New order #{ $id }
manager-order-created-lead = Waiting for a manager decision.
manager-order-processing-title = ✅ Order #{ $id } is being processed
manager-order-processing-lead = The customer was asked to open the conversation. Wait for their message.
manager-order-processing-failed-lead = The order is being processed, but the message was not delivered to the customer. Check the contact settings, then send a reminder.
manager-order-completed-title = ✅ Order #{ $id } completed
manager-order-completed-lead = The exchange has been completed successfully.
manager-order-cancelled-title = ❌ Order #{ $id } cancelled
manager-order-cancelled-lead = Work on the order has stopped.
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
btn-write-manager = 💬 Message the manager
btn-open-client-chat = 💬 Open chat with client
btn-remind-client = 🔔 Remind client
referral-bonus-credited =
    🎁 Referral program reward: +{ $amount } ATXG
    For completed order #{ $order_id }.
referral-bonus-reversed =
    💸 Referral program reward reversed: -{ $amount } ATXG
    Order #{ $order_id } was cancelled.
miniapp-aex-referral-reward = Referral reward
miniapp-aex-referral-reward-with-order = Referral reward for order { $order_number }
miniapp-aex-withdraw-hold = Reserved
miniapp-aex-withdraw-hold-with-order = Reserved for order { $order_number }
miniapp-aex-withdraw-debit = Debited
miniapp-aex-withdraw-debit-with-order = Debited for order { $order_number }
miniapp-aex-withdraw-release = Refund
miniapp-aex-withdraw-release-with-order = Refund for order { $order_number }