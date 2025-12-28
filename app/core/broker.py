from faststream.rabbit import RabbitBroker

from app.core.config import settings

broker = RabbitBroker(settings.RABBITMQ_URL)
