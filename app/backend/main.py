
import json
import logging
import os

import pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Raincheck Backend",
    description="Backend API for the Raincheck weather dashboard",
    version="1.0.0",
)


class WeatherRequest(BaseModel):
    city: str


def publish_weather_request(city: str):
    credentials = pika.PlainCredentials(
        os.environ["RABBITMQ_USERNAME"],
        os.environ["RABBITMQ_PASSWORD"],
    )

    parameters = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "raincheck-rabbitmq"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        credentials=credentials,
        heartbeat=30,
        socket_timeout=5,
        connection_attempts=3,
        retry_delay=2,
    )

    connection = pika.BlockingConnection(parameters)

    try:
        channel = connection.channel()

        channel.queue_declare(
            queue="weather_tasks",
            durable=True,
        )

        channel.confirm_delivery()

        message = json.dumps({"city": city})

        channel.basic_publish(
            exchange="",
            routing_key="weather_tasks",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
            mandatory=True,
        )

        logger.info("Published weather request for %s", city)

    finally:
        connection.close()


@app.get("/")
def root():
    return {
        "application": "Raincheck",
        "service": "backend",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


@app.post("/weather/request")
def request_weather(request: WeatherRequest):
    try:
        publish_weather_request(request.city)
        return {
            "status": "queued",
            "city": request.city,
            "queue": "weather_tasks",
        }

    except Exception:
        logger.exception("Failed to publish weather request")
        raise HTTPException(
            status_code=503,
            detail="Could not publish weather request to RabbitMQ",
        )
