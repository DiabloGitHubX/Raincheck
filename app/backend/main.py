
import json
import logging
import os
import uuid

import pika
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Raincheck Backend",
    description="Backend API for the Raincheck weather dashboard",
    version="2.0.0",
)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "raincheck-rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.environ["RABBITMQ_USERNAME"]
RABBITMQ_PASSWORD = os.environ["RABBITMQ_PASSWORD"]

REDIS_HOST = os.getenv("REDIS_HOST", "raincheck-redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "3600"))

QUEUE_NAME = "weather_tasks"


class WeatherRequest(BaseModel):
    city: str = Field(min_length=2, max_length=100)


def get_redis_client():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def publish_weather_request(request_id: str, city: str):
    credentials = pika.PlainCredentials(
        RABBITMQ_USERNAME,
        RABBITMQ_PASSWORD,
    )

    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
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
            queue=QUEUE_NAME,
            durable=True,
        )

        channel.confirm_delivery()

        message = json.dumps({
            "request_id": request_id,
            "city": city,
        })

        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
            mandatory=True,
        )

        logger.info(
            "Published weather request %s for %s",
            request_id,
            city,
        )

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
    return {"status": "healthy"}


@app.post("/weather/request", status_code=202)
def request_weather(request: WeatherRequest):
    city = request.city.strip()

    if len(city) < 2:
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid city name",
        )

    request_id = str(uuid.uuid4())
    redis_client = get_redis_client()

    try:
        redis_client.setex(
            f"weather:{request_id}",
            REDIS_TTL,
            json.dumps({
                "request_id": request_id,
                "city": city,
                "status": "queued",
            }),
        )

        publish_weather_request(request_id, city)

        return {
            "request_id": request_id,
            "city": city,
            "status": "queued",
        }

    except Exception:
        logger.exception("Failed to submit weather request")

        try:
            redis_client.delete(f"weather:{request_id}")
        except redis.RedisError:
            logger.exception("Failed to clean up Redis request")

        raise HTTPException(
            status_code=503,
            detail="Could not submit weather request. Please try again.",
        )

    finally:
        redis_client.close()


@app.get("/weather/result/{request_id}")
def get_weather_result(request_id: str):
    try:
        redis_client = get_redis_client()

        try:
            result = redis_client.get(f"weather:{request_id}")
        finally:
            redis_client.close()

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Weather request not found or expired",
            )

        return json.loads(result)

    except redis.RedisError:
        logger.exception("Redis unavailable while retrieving weather result")

        raise HTTPException(
            status_code=503,
            detail="Weather results are temporarily unavailable",
        )
