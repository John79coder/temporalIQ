import queue
import threading
import atexit
from logging import Handler, LogRecord
from typing import Optional


class AsyncHandler(Handler):
    """
    Asynchronous logging handler for high-throughput scenarios
    """

    def __init__(self, target_handler: Handler, buffer_size: int = 1024):
        super().__init__()
        self.target_handler = target_handler
        self.queue = queue.Queue(buffer_size)
        self.sentinel = object()

        # Start worker thread
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

        # Register cleanup
        atexit.register(self.close)

    def _worker_loop(self):
        """Worker thread that processes log records"""
        while True:
            try:
                record = self.queue.get(timeout=1)

                if record is self.sentinel:
                    break

                if record:
                    self.target_handler.emit(record)

            except queue.Empty:
                continue
            except Exception:
                # Silently ignore to prevent logging loops
                pass

    def emit(self, record: LogRecord):
        """Add record to queue for async processing"""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # If queue is full, fall back to synchronous logging
            self.target_handler.emit(record)

    def close(self):
        """Flush queue and stop worker thread"""
        # Signal worker to stop
        try:
            self.queue.put_nowait(self.sentinel)
        except queue.Full:
            pass

        # Wait for worker to finish
        if self.worker.is_alive():
            self.worker.join(timeout=5)

        # Close target handler
        self.target_handler.close()

        super().close()