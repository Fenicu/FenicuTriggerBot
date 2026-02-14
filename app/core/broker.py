from enum import StrEnum

from faststream.rabbit import RabbitBroker, RabbitExchange

from app.core.config import settings


class ExchangeTypeCustom(StrEnum):
    X_DELAYED_MESSAGE = "x-delayed-message"


broker = RabbitBroker(settings.RABBITMQ_URL)

delayed_exchange = RabbitExchange(
    name="delayed_exchange",
    type=ExchangeTypeCustom.X_DELAYED_MESSAGE,
    arguments={"x-delayed-type": "direct"},
)
