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
exchange-choose-currency-title = Which currency are you sending?
exchange-choose-currency-description = Choose a currency — you’ll enter the amount next.
exchange-choose-currency-selection-title = Order details
exchange-choose-currency-summary-country = Country
exchange-choose-currency-summary-service = Service
exchange-choose-currency-summary-city = City
exchange-choose-currency-rates-title = Available rates
exchange-choose-currency-currency-column = Currency
exchange-choose-currency-rate-column = Rate
exchange-choose-currency-rate-from = from
exchange-choose-currency-options-hint = Select a currency using the buttons below 👇
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
exchange-enter-amount-title = Enter the exchange amount
exchange-enter-amount-prompt = Send the amount in { $currency } you want to exchange in one message.
exchange-enter-amount-minimum-label = Minimum amount
exchange-amount-invalid = Enter an amount greater than zero.
exchange-amount-below-minimum = The amount must be at least { $minAmount }. Enter a valid amount for this receive method.
exchange-choose-method = How would you like to receive { $currency }?
exchange-rate-unavailable = ⚠️ Exchange rate is temporarily unavailable. Please try again later.
exchange-confirm-summary-top = 📋 Review your order — step { $current }/{ $total }
exchange-confirm-title = Review your order
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
btn-write-manager = 💬 Write in this chat
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
    <h2>What to do</h2>
    <ol>
      <li>💬 Tap “Write in this chat”.</li>
      <li>📝 Send your message in the official bot chat.</li>
    </ol>
    <aside>The manager will reply here through the official bot and confirm the exchange details.</aside>
order-handoff-html =
    <b>✅ Order #{ $id } is being processed</b>

    The manager is ready to continue the exchange.

    { $summary }

    <b>What to do</b>
    1. 💬 Tap “Write in this chat”.
    2. 📝 Send your message in the official bot chat.

    The manager will reply here through the official bot and confirm the exchange details.
order-reminder-rich =
    <footer>Order reminder</footer>
    <h2>🔔 The manager is waiting for your message about order #{ $id }</h2>
    <p>The manager is ready to continue the exchange.</p>
    <hr/>
    { $summary }
    <h2>What to do</h2>
    <ol>
      <li>💬 Tap “Write in this chat”.</li>
      <li>📝 Send your message in the official bot chat.</li>
    </ol>
    <aside>The manager will reply here through the official bot and confirm the exchange details.</aside>
order-reminder-html =
    <b>🔔 The manager is waiting for your message about order #{ $id }</b>

    The manager is ready to continue the exchange.

    { $summary }

    <b>What to do</b>
    1. 💬 Tap “Write in this chat”.
    2. 📝 Send your message in the official bot chat.

    The manager will reply here through the official bot and confirm the exchange details.
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
order-completed-footer = Order completed
order-completed-bottom =
    💚 <b>Thanks for using our service!</b>

    We value your feedback.

    ⭐ <b>We’d be glad to receive your review!</b>

    It helps us improve.
order-completed-bottom-rich =
    <p>💚 <b>Thanks for using our service!</b><br/>We value your feedback.</p>
    <aside>💰 Send a video review (a video note) and receive a <b>$5 bonus for your next exchange 💰</b></aside>
    <p>⭐ <b>We’d be glad to receive your review!</b><br/>It helps us improve.</p>
order-cancelled = ❌ Order #{ $id } cancelled.
btn-write-manager = 💬 Write in this chat
btn-open-client-chat = 💬 Open chat in Mini App
btn-remind-client = 🔔 Remind client
customer-chat-reply-prompt = Send your message in this bot chat. The manager will reply here.
manager-chat-fallback-title = New customer message
manager-chat-fallback-anonymous = Customer #{ $user_id }
manager-chat-fallback-media = Attachment: { $media_type }
manager-chat-fallback-open = Open chat in Mini App
operator-order-not-found = Order not found
operator-order-status-changed = The order status has already changed
operator-card-update-failed = Could not update the order card
operator-handoff-delivery-failed = The order was accepted, but the instruction could not be delivered. Check the official bot chat and send the reminder again.
operator-reminder-processing-only = Reminders are available only while the order is in progress
operator-reminder-failed = Could not send the reminder. Please try again.
operator-reminder-sent = 🔔 Reminder sent to the customer
operator-order-cancelled = Order cancelled
operator-chat-button-obsolete = Open the chat in Manager Mini App
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
