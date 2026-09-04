#!/usr/bin/env python3
"""
Producer for the OrderCreated data contract.

Serializes every message with confluent_kafka's AvroSerializer, which round-trips
through the schema registry: it registers (or resolves) the OrderCreated schema for
subject "orders.order-created-value" before it will let a single message go out.
If someone edits schemas/order-created/schema.avsc into a breaking change and this
service is rebuilt, the registry's BACKWARD compatibility rule rejects the
registration and this process fails at startup instead of quietly shipping bad data.
"""
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s producer %(levelname)s %(message)s")
log = logging.getLogger("producer")

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schemas", "order-created", "schema.avsc")
TOPIC = os.environ.get("TOPIC_NAME", "orders.order-created")
BOOTSTRAP_SERVERS = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
REGISTRY_URL = os.environ["SCHEMA_REGISTRY_URL"]

CURRENCIES = ["USD", "EUR", "GBP", "INR"]


def load_schema_str() -> str:
    with open(SCHEMA_PATH) as f:
        return f.read()


def make_order() -> dict:
    return {
        "order_id": str(uuid.uuid4()),
        "customer_id": f"cust-{random.randint(1, 500)}",
        "amount": round(random.uniform(5, 500), 2),
        "currency": random.choice(CURRENCIES),
        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
    }


def delivery_report(err, msg) -> None:
    if err is not None:
        log.error("delivery failed key=%s: %s", msg.key(), err)
    else:
        log.info("delivered order_id=%s -> %s[%d]@%d", msg.key(), msg.topic(), msg.partition(), msg.offset())


def build_serializer(retries: int = 30, delay_seconds: float = 2.0) -> AvroSerializer:
    """The registry container can still be starting up when this process launches;
    retry rather than crash-looping on the very first connection attempt."""
    schema_registry_client = SchemaRegistryClient({"url": REGISTRY_URL})
    schema_str = load_schema_str()
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return AvroSerializer(schema_registry_client, schema_str)
        except Exception as exc:  # noqa: BLE001 - broad: registry may be down, schema may be rejected
            last_error = exc
            log.warning("could not initialize Avro serializer (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay_seconds)
    raise RuntimeError(f"giving up initializing Avro serializer against {REGISTRY_URL}: {last_error}")


def main() -> None:
    avro_serializer = build_serializer()
    producer = Producer({"bootstrap.servers": BOOTSTRAP_SERVERS})

    log.info("publishing OrderCreated events to '%s' every 2s (registry=%s)", TOPIC, REGISTRY_URL)
    try:
        while True:
            order = make_order()
            producer.produce(
                topic=TOPIC,
                key=order["order_id"],
                value=avro_serializer(order, SerializationContext(TOPIC, MessageField.VALUE)),
                on_delivery=delivery_report,
            )
            producer.poll(0)
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush()


if __name__ == "__main__":
    main()
