import asyncio
import unittest

from observatory.log_broker import LogBroker


class LogBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_is_bounded_and_live_entries_follow_in_order(self):
        broker = LogBroker(history_size=3, queue_size=5)
        for index in range(4):
            broker.publish(
                [f"history {index}"],
                timestamp="2026-08-05T00:00:00Z",
                level="INFO",
                logger_name="test",
            )

        subscription, snapshot = broker.subscribe()
        self.assertEqual([entry["text"] for entry in snapshot], [
            "history 1",
            "history 2",
            "history 3",
        ])

        broker.publish(
            ["live 1", "live 2"],
            timestamp="2026-08-05T00:00:01Z",
            level="ERROR",
            logger_name="test.live",
        )
        await asyncio.sleep(0)

        first = await broker.next_event(subscription)
        second = await broker.next_event(subscription)
        self.assertEqual(first["entry"]["text"], "live 1")
        self.assertEqual(second["entry"]["text"], "live 2")
        self.assertLess(first["entry"]["seq"], second["entry"]["seq"])
        self.assertEqual(
            first["entry"]["record_id"],
            second["entry"]["record_id"],
        )

        broker.unsubscribe(subscription)

    async def test_slow_client_drops_oldest_entries_without_blocking(self):
        broker = LogBroker(history_size=10, queue_size=2)
        subscription, _ = broker.subscribe()

        for index in range(3):
            broker.publish(
                [f"live {index}"],
                timestamp="2026-08-05T00:00:00Z",
                level="INFO",
                logger_name="test",
            )
        await asyncio.sleep(0)

        dropped = await broker.next_event(subscription)
        self.assertEqual(dropped, {"type": "dropped", "count": 1})
        first = await broker.next_event(subscription)
        second = await broker.next_event(subscription)
        self.assertEqual(first["entry"]["text"], "live 1")
        self.assertEqual(second["entry"]["text"], "live 2")

        broker.unsubscribe(subscription)

    async def test_publish_from_worker_thread_reaches_async_client(self):
        broker = LogBroker(history_size=10, queue_size=5)
        subscription, _ = broker.subscribe()

        await asyncio.to_thread(
            broker.publish,
            ["threaded entry"],
            timestamp="2026-08-05T00:00:00Z",
            level="INFO",
            logger_name="test.thread",
        )

        event = await asyncio.wait_for(
            broker.next_event(subscription),
            timeout=1,
        )
        self.assertEqual(event["entry"]["text"], "threaded entry")
        self.assertEqual(event["entry"]["logger"], "test.thread")

        broker.unsubscribe(subscription)


if __name__ == "__main__":
    unittest.main()
