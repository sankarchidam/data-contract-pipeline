#!/usr/bin/env python3
"""
Consumer for the OrderCreated data contract.

Deserializes with confluent_kafka's AvroDeserializer, which fetches the writer's
schema from the registry by the ID embedded in each message and resolves it against
whatever reader schema this process was built with. As long as the registry's
BACKWARD compatibility rule holds, every message this consumer ever sees is
guaranteed to be readable by the field access below without a KeyError.
"""
import logging
import os

from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s consumer %(levelname)s %(message)s")
log = logging.getLogger("consumer")

TOPIC = os.environ.get("TOPIC_NAME", "orders.order-created")
BOOTSTRAP_SERVERS = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
REGISTRY_URL = os.environ["SCHEMA_REGISTRY_URL"]
GROUP_ID = os.environ.get("GROUP_ID", "order-created-consumer")


def main() -> None:
    schema_registry_client = SchemaRegistryClient({"url": REGISTRY_URL})
    avro_deserializer = AvroDeserializer(schema_registry_client)

    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([TOPIC])

    log.info("group '%s' subscribed to '%s' (registry=%s)", GROUP_ID, TOPIC, REGISTRY_URL)
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
                "consumed order_id=%s customer=%s amount=%.2f %s | count=%d running_total=%.2f",
                order["order_id"],
                order["customer_id"],
                order["amount"],
                order["currency"],
                count,
                running_total,
            )
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
