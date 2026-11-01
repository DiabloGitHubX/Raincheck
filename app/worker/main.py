
import json
import logging
import os
import time

import pika
import redis
import requests

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

QUEUE_NAME = "weather_tasks"


def get_redis_client():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def get_weather(city):
    """Retrieve current weather for a city using Open-Meteo."""

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
        raise ValueError(f"City not found: {city}")

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


def process_message(channel, method, properties, body):
    redis_client = None
    message = {}

    try:
        message = json.loads(body)

        request_id = message["request_id"]
        city = message["city"]

        redis_client = get_redis_client()

        request_key = f"weather:{request_id}"

        redis_client.setex(
            request_key,
            REDIS_TTL,
            json.dumps({
                "request_id": request_id,
                "city": city,
                "status": "processing",
            }),
        )

        logger.info(
            "Processing weather request %s for %s",
            request_id,
            city,
        )

        weather = get_weather(city)

        result = {
            "request_id": request_id,
            "city": city,
            "status": "completed",
            "weather": weather,
        }

        redis_client.setex(
            request_key,
            REDIS_TTL,
            json.dumps(result),
        )

        logger.info(
            "Weather request %s completed successfully",
            request_id,
        )

        channel.basic_ack(delivery_tag=method.delivery_tag)

    except (requests.RequestException, ValueError, KeyError) as error:
        logger.exception("Weather request failed")

        if redis_client:
            try:
                request_id = message.get("request_id", "unknown")
                city = message.get("city", "unknown")

                redis_client.setex(
                    f"weather:{request_id}",
                    REDIS_TTL,
                    json.dumps({
                        "request_id": request_id,
                        "city": city,
                        "status": "failed",
                        "error": str(error),
                    }),
                )

                channel.basic_ack(delivery_tag=method.delivery_tag)

            except redis.RedisError:
                logger.exception("Could not save failed result to Redis")
                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True,
                )
        else:
            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=True,
            )

    except redis.RedisError:
        logger.exception("Redis operation failed")

        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=True,
        )

    except Exception:
        logger.exception("Unexpected worker error")

        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )

    finally:
        if redis_client:
            redis_client.close()


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
        try:
            logger.info("Connecting to RabbitMQ at %s", RABBITMQ_HOST)

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True,
            )

            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=process_message,
            )

            logger.info("Waiting for messages on queue: %s", QUEUE_NAME)

            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Worker shutdown requested")
            break

        except Exception:
            logger.exception("Worker connection failed; retrying in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()
