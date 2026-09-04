#!/usr/bin/env python3
"""
Stand-in for a consumer team that built against the v1 contract and never
redeployed. Unlike consumer/consumer.py, this one passes an explicit reader
schema (frozen in reader-schema-v1.avsc, baked into this image at build time)
to AvroDeserializer -- so it always resolves incoming Avro payloads against v1,
no matter what schema version the producer actually wrote with.

That's what BACKWARD compatibility buys you: this code and this image never
have to change for the pipeline to keep working as the contract evolves. Any
field added after v1 is silently dropped during resolution -- this process
never even sees it, let alone errors on it.

Runs as its own consumer group, so it gets an independent full copy of the
topic rather than competing with consumer/consumer.py for partitions.
"""
import logging
import os

from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s consumer-legacy %(levelname)s %(message)s")
log = logging.getLogger("consumer-legacy")

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reader-schema-v1.avsc")
TOPIC = os.environ.get("TOPIC_NAME", "orders.order-created")
BOOTSTRAP_SERVERS = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
REGISTRY_URL = os.environ["SCHEMA_REGISTRY_URL"]
GROUP_ID = os.environ.get("GROUP_ID", "order-created-consumer-legacy-v1")


def load_schema_str() -> str:
    with open(SCHEMA_PATH) as f:
        return f.read()


def main() -> None:
    schema_registry_client = SchemaRegistryClient({"url": REGISTRY_URL})
    # Passing schema_str pins this as the READER schema for every message, regardless
    # of which schema version the writer used -- this is the line that makes this
    # consumer "frozen" rather than "dynamic" like consumer/consumer.py.
    avro_deserializer = AvroDeserializer(schema_registry_client, load_schema_str())

    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([TOPIC])

    log.info("group '%s' subscribed to '%s', pinned to frozen v1 reader schema", GROUP_ID, TOPIC)
    count = 0
    running_total = 0.0
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("consumer error: %s", msg.error())
                continue

            order = avro_deserializer(msg.value(), SerializationContext(TOPIC, MessageField.VALUE))
            count += 1
            running_total += order["amount"]
            log.info(
                "[v1 reader] order_id=%s customer=%s amount=%.2f %s | count=%d running_total=%.2f | fields=%s",
                order["order_id"],
                order["customer_id"],
                order["amount"],
                order["currency"],
                count,
                running_total,
                sorted(order.keys()),
            )
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
