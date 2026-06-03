from __future__ import annotations

import json
import os

import sentry_sdk
from google.cloud import pubsub_v1

from backend.gdal_cog_processor.process import process_event

PROJECT_ID = os.getenv("GCP_PROJECT", "")
SUBSCRIPTION_ID = os.getenv("IMAGERY_SUBSCRIPTION", "imagery-uploads-sub")

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("APP_ENV", "production"),
    traces_sample_rate=0.1,
)


def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        event_data = json.loads(message.data.decode("utf-8"))
        process_event(event_data)
        message.ack()
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        message.nack()


def main() -> None:
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    print(f"Listening on {subscription_path}")
    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()


if __name__ == "__main__":
    main()
