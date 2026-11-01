import json
import logging
import os
import time

import pika
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
QUEUE_NAME = "weather_tasks"


def get_weather(city):
    """Retrieve current weather for a city using Open-Meteo."""
    geocoding_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "en", "format": "json"},
        timeout=15,
    )
    geocoding_response.raise_for_status()

    locations = geocoding_response.json().get("results", [])
    if not locations:
        raise ValueError(f"City not found: {city}")

    location = locations[0]
    latitude = location["latitude"]
    longitude = location["longitude"]

    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
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
    try:
        message = json.loads(body)
        city = message["city"]

        logger.info("Processing weather request for %s", city)

        weather = get_weather(city)

        logger.info(
            "Weather retrieved successfully: %s",
            json.dumps(weather),
        )

        channel.basic_ack(delivery_tag=method.delivery_tag)

    except Exception:
        logger.exception("Failed to process weather request")
        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )


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

            channel.queue_declare(queue=QUEUE_NAME, durable=True)
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
