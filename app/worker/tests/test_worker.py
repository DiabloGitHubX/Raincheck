
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pika
import pytest
import redis
import requests

os.environ.setdefault("RABBITMQ_USERNAME", "test-user")
os.environ.setdefault("RABBITMQ_PASSWORD", "test-password")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as worker


@pytest.fixture
def setup_worker(monkeypatch):
    channel = MagicMock()
    channel.basic_publish.return_value = True

    method = SimpleNamespace(delivery_tag=1)
    properties = pika.BasicProperties(headers={})

    client = MagicMock()
    monkeypatch.setattr(worker, "get_redis_client", lambda: client)

    return channel, method, properties, client


def make_message(request_id="test-123", city="London"):
    return json.dumps({
        "request_id": request_id,
        "city": city,
    }).encode()


def test_successful_request(setup_worker, monkeypatch):
    channel, method, properties, client = setup_worker

    monkeypatch.setattr(
        worker,
        "get_weather",
        lambda city: {"city": city, "current_weather": {}},
    )

    worker.process_message(
        channel, method, properties, make_message()
    )

    channel.basic_ack.assert_called_once_with(delivery_tag=1)
    channel.basic_publish.assert_not_called()
    assert client.setex.call_count == 2
    client.close.assert_called_once()


def test_unknown_city_goes_to_dlq(setup_worker, monkeypatch):
    channel, method, properties, client = setup_worker

    def unknown_city(city):
        raise worker.PermanentRequestError("City not found")

    monkeypatch.setattr(worker, "get_weather", unknown_city)

    worker.process_message(
        channel, method, properties, make_message()
    )

    assert channel.basic_publish.call_args.kwargs["routing_key"] == (
        worker.DEAD_LETTER_QUEUE
    )
    channel.basic_ack.assert_called_once()
    client.close.assert_called_once()


def test_temporary_failure_schedules_retry(setup_worker, monkeypatch):
    channel, method, properties, client = setup_worker

    def temporary_failure(city):
        raise requests.Timeout("Open-Meteo timeout")

    monkeypatch.setattr(worker, "get_weather", temporary_failure)

    worker.process_message(
        channel, method, properties, make_message()
    )

    publish_args = channel.basic_publish.call_args.kwargs

    assert publish_args["routing_key"] == worker.RETRY_QUEUE
    assert publish_args["properties"].headers["x-retry-count"] == 1
    assert publish_args["mandatory"] is True

    channel.basic_ack.assert_called_once()
    client.close.assert_called_once()


def test_retries_exhausted_goes_to_dlq(setup_worker, monkeypatch):
    channel, method, properties, client = setup_worker

    properties.headers = {"x-retry-count": worker.MAX_RETRIES}

    def temporary_failure(city):
        raise requests.Timeout("Open-Meteo timeout")

    monkeypatch.setattr(worker, "get_weather", temporary_failure)

    worker.process_message(
        channel, method, properties, make_message()
    )

    publish_args = channel.basic_publish.call_args.kwargs

    assert publish_args["routing_key"] == worker.DEAD_LETTER_QUEUE
    assert publish_args["properties"].headers["x-retry-count"] == (
        worker.MAX_RETRIES
    )
    channel.basic_ack.assert_called_once()
    client.close.assert_called_once()


def test_publish_failure_does_not_ack(setup_worker, monkeypatch):
    channel, method, properties, client = setup_worker

    channel.basic_publish.return_value = False

    def temporary_failure(city):
        raise requests.Timeout("Open-Meteo timeout")

    monkeypatch.setattr(worker, "get_weather", temporary_failure)

    with pytest.raises(RuntimeError):
        worker.process_message(
            channel, method, properties, make_message()
        )

    channel.basic_ack.assert_not_called()
    client.close.assert_called_once()


def test_redis_failure_schedules_retry(setup_worker):
    channel, method, properties, client = setup_worker

    client.setex.side_effect = redis.RedisError("Redis unavailable")

    worker.process_message(
        channel, method, properties, make_message()
    )

    publish_args = channel.basic_publish.call_args.kwargs

    assert publish_args["routing_key"] == worker.RETRY_QUEUE
    channel.basic_ack.assert_called_once()
    client.close.assert_called_once()


def test_invalid_json_goes_to_dlq(setup_worker):
    channel, method, properties, _client = setup_worker

    worker.process_message(
        channel, method, properties, b"not valid JSON"
    )

    assert channel.basic_publish.call_args.kwargs["routing_key"] == (
        worker.DEAD_LETTER_QUEUE
    )
    channel.basic_ack.assert_called_once()
