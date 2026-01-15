from faststream.rabbit import RabbitBroker, RabbitExchange

from app.core.config import settings

broker = RabbitBroker(settings.RABBITMQ_URL)

delayed_exchange = RabbitExchange(
    name="delayed_exchange",
    type="x-delayed-message",
    arguments={"x-delayed-type": "direct"},
)
