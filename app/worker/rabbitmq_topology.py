"""RabbitMQ retry and dead-letter topology for Raincheck."""

MAIN_QUEUE = "weather_tasks"
RETRY_QUEUE = "weather_tasks.retry"
DEAD_LETTER_QUEUE = "weather_tasks.dlq"

RETRY_EXCHANGE = "weather_tasks.retry.exchange"
DEAD_LETTER_EXCHANGE = "weather_tasks.dlx"

RETRY_DELAY_MS = 10_000
MAX_RETRIES = 3


def declare_topology(channel):
    """Declare durable queues and exchanges without modifying the main queue."""

    channel.exchange_declare(
        exchange=RETRY_EXCHANGE,
        exchange_type="direct",
        durable=True,
    )

    channel.exchange_declare(
        exchange=DEAD_LETTER_EXCHANGE,
        exchange_type="direct",
        durable=True,
    )

    channel.queue_declare(
        queue=MAIN_QUEUE,
        durable=True,
    )

    channel.queue_declare(
        queue=RETRY_QUEUE,
        durable=True,
        arguments={
            "x-message-ttl": RETRY_DELAY_MS,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": MAIN_QUEUE,
        },
    )

    channel.queue_bind(
        queue=RETRY_QUEUE,
        exchange=RETRY_EXCHANGE,
        routing_key=RETRY_QUEUE,
    )

    channel.queue_declare(
        queue=DEAD_LETTER_QUEUE,
        durable=True,
    )

    channel.queue_bind(
        queue=DEAD_LETTER_QUEUE,
        exchange=DEAD_LETTER_EXCHANGE,
        routing_key=DEAD_LETTER_QUEUE,
    )