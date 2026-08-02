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
    durable=True,  # переживает рестарт RabbitMQ -- задачи капчи/автоудаления не теряются при деплое
)


async def schedule_autodelete(chat_id: int, message_id: int, autodelete_settings: dict | None, msg_type: str) -> None:
    """Publish a delayed message-deletion task if autodelete is configured for msg_type."""
    if not autodelete_settings:
        return
    config = autodelete_settings.get(msg_type)
    if not config or not config.get("enabled"):
        return
    delay = config.get("delay", 30)
    await broker.publish(
        message={"chat_id": chat_id, "message_id": message_id},
        exchange=delayed_exchange,
        routing_key="q.messages.delete",
        headers={"x-delay": delay * 1000},
        persist=True,
    )
