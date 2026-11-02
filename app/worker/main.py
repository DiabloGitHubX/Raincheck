
import json
import logging
import os
import time

import pika
import redis
import requests
from rabbitmq_topology import (
    DEAD_LETTER_EXCHANGE,
    DEAD_LETTER_QUEUE,
    MAIN_QUEUE,
    MAX_RETRIES,
    RETRY_EXCHANGE,
    RETRY_QUEUE,
    declare_topology,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "raincheck-rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.environ["RABBITMQ_USERNAME"]
RABBITMQ_PASSWORD = os.environ["RABBITMQ_PASSWORD"]

REDIS_HOST = os.getenv("REDIS_HOST", "raincheck-redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "3600"))


class PermanentRequestError(Exception):
    """A request that cannot succeed by retrying."""


def get_redis_client():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def get_weather(city):
    geocoding_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city,
            "count": 1,
            "language": "en",
            "format": "json",
        },
        timeout=15,
    )
    geocoding_response.raise_for_status()

    locations = geocoding_response.json().get("results", [])

    if not locations:
        raise PermanentRequestError(f"City not found: {city}")

    location = locations[0]

    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "apparent_temperature,precipitation,"
                "weather_code,wind_speed_10m"
            ),
        },
        timeout=15,
    )
    weather_response.raise_for_status()

    return {
        "city": location["name"],
        "country": location.get("country"),
        "current_weather": weather_response.json().get("current", {}),
    }


def save_status(client, request_id, city, status, **extra):
    client.setex(
        f"weather:{request_id}",
        REDIS_TTL,
        json.dumps({
            "request_id": request_id,
            "city": city,
            "status": status,
            **extra,
        }),
    )


def publish_and_ack(
    channel,
    method,
    properties,
    body,
    exchange,
    routing_key,
    retry_count,
):
    """ACK the original only after confirmed, routed publication."""

    headers = dict(properties.headers or {})
    headers["x-retry-count"] = retry_count

    outgoing_properties = pika.BasicProperties(
        content_type=properties.content_type or "application/json",
        delivery_mode=2,
        headers=headers,
        correlation_id=properties.correlation_id,
        message_id=properties.message_id,
    )

    # With Pika BlockingChannel publisher confirms enabled,
    # basic_publish returns None on success and raises on failure.
    channel.basic_publish(
        exchange=exchange,
        routing_key=routing_key,
        body=body,
        properties=outgoing_properties,
        mandatory=True,
    )

    channel.basic_ack(delivery_tag=method.delivery_tag)


def process_message(channel, method, properties, body):
    client = None
    request_id = None
    city = None

    try:
        headers = properties.headers or {}
        retry_count = int(headers.get("x-retry-count", 0))

        if retry_count < 0:
            raise PermanentRequestError("Invalid retry count")

        try:
            message = json.loads(body)

            if not isinstance(message, dict):
                raise PermanentRequestError("Message must be a JSON object")

            request_id = message.get("request_id")
            city = message.get("city")

            if not isinstance(request_id, str) or not request_id:
                raise PermanentRequestError("Invalid request_id")

            if not isinstance(city, str) or not city.strip():
                raise PermanentRequestError("Invalid city")

        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise PermanentRequestError("Invalid JSON message") from error

        client = get_redis_client()

        save_status(client, request_id, city, "processing")

        logger.info(
            "Processing request %s for %s (retry %s/%s)",
            request_id,
            city,
            retry_count,
            MAX_RETRIES,
        )

        weather = get_weather(city)

        save_status(
            client,
            request_id,
            city,
            "completed",
            weather=weather,
        )

        channel.basic_ack(delivery_tag=method.delivery_tag)

        logger.info("Request %s completed", request_id)
        return

    except (PermanentRequestError, ValueError, TypeError) as error:
        logger.warning("Permanent request failure: %s", error)

        target_exchange = DEAD_LETTER_EXCHANGE
        target_queue = DEAD_LETTER_QUEUE
        next_retry_count = MAX_RETRIES

        if request_id and city:
            try:
                if client is None:
                    client = get_redis_client()

                save_status(
                    client,
                    request_id,
                    city,
                    "failed",
                    error=str(error),
                )
            except redis.RedisError:
                logger.exception("Unable to save permanent failure status")

    except Exception as error:
        logger.exception("Worker processing failed")

        if retry_count < MAX_RETRIES:
            target_exchange = RETRY_EXCHANGE
            target_queue = RETRY_QUEUE
            next_retry_count = retry_count + 1

            logger.warning(
                "Scheduling retry %s/%s for request %s",
                next_retry_count,
                MAX_RETRIES,
                request_id,
            )

        else:
            target_exchange = DEAD_LETTER_EXCHANGE
            target_queue = DEAD_LETTER_QUEUE
            next_retry_count = retry_count

            logger.error(
                "Retries exhausted for request %s: %s",
                request_id,
                error,
            )

            if request_id and city:
                try:
                    if client is None:
                        client = get_redis_client()

                    save_status(
                        client,
                        request_id,
                        city,
                        "failed",
                        error=f"Retries exhausted: {error}",
                    )
                except redis.RedisError:
                    logger.exception("Unable to save final failure status")

    finally:
        if client is not None:
            client.close()

    try:
        publish_and_ack(
            channel=channel,
            method=method,
            properties=properties,
            body=body,
            exchange=target_exchange,
            routing_key=target_queue,
            retry_count=next_retry_count,
        )

        logger.info(
            "Request %s routed to %s",
            request_id,
            target_queue,
        )

    except Exception:
        logger.exception(
            "RabbitMQ publication failed; original message not acknowledged"
        )
        raise


def main():
    credentials = pika.PlainCredentials(
        RABBITMQ_USERNAME,
        RABBITMQ_PASSWORD,
    )

    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=30,
        connection_attempts=10,
        retry_delay=5,
    )

    while True:
        connection = None

        try:
            logger.info("Connecting to RabbitMQ at %s", RABBITMQ_HOST)

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            declare_topology(channel)

            # Required for publish_and_ack reliability.
            channel.confirm_delivery()

            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=MAIN_QUEUE,
                on_message_callback=process_message,
            )

            logger.info("Waiting for messages on queue: %s", MAIN_QUEUE)

            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Worker shutdown requested")
            break

        except Exception:
            logger.exception(
                "Worker connection or processing failed; retrying in 5 seconds"
            )
            time.sleep(5)

        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
