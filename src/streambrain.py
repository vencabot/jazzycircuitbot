import datetime
import threading
import time
import typing


class Event:
    def __init__(self, message: object) -> None:
        self.message = message
        self.created_at = datetime.datetime.now()


class Listener:
    def __init__(self, sleep_sec: int, listen: callable=None) -> None:
        self.sleep_sec = sleep_sec
        if listen is not None:
            self.listen = listen

    def listen(self) -> typing.List[Event]:
        return []


class ListenThread(threading.Thread):
    def __init__(self, listener: Listener, process_event: callable) -> None:
        self.listener = listener
        self.process_event = process_event
        self._is_listening = False
        super().__init__()

    def run(self) -> None:
        self._is_listening = True
        while self._is_listening:
            for event in self.listener.listen():
                self.process_event(event)
            time.sleep(self.listener.sleep_sec)

    def stop(self) -> None:
        self._is_listening = False


class Handler:
    def __init__(self, handles_type: typing.Type[Event]) -> None:
        self.handles_type = handles_type

    def handle(self, streambrain_event: Event) -> None:
        pass


class StreamBrain:
    def __init__(self) -> None:
        self._event_handler_map = {}
        self._event_queue = []
        self._is_processing_event_queue = False
        self._listen_threads = []

    def start_listening(self, listener: Listener) -> ListenThread:
        listen_thread = ListenThread(listener, self.queue_event)
        self._listen_threads.append(listen_thread)
        listen_thread.start()
        return listen_thread

    def stop(self) -> None:
        while self._listen_threads:
            self._listen_threads.pop().stop()

    def activate_handler(self, handler) -> None:
        if handler.handles_type not in self._event_handler_map:
            self._event_handler_map[handler.handles_type] = []
        self._event_handler_map[handler.handles_type].append(handler)

    def queue_event(
            self, streambrain_event: Event) -> None:
        self._event_queue.append(streambrain_event)
        if not self._is_processing_event_queue:
            self.process_event_queue()

    def process_event_queue(self) -> None:
        self._is_processing_event_queue = True
        while self._event_queue:
            queued_event = self._event_queue.pop(0)
            event_type = type(queued_event)
            try:
                handlers_snapshot = (
                        self._event_handler_map[event_type].copy())
            except KeyError:
                # No handlers for this type of event.
                continue
            for handler in handlers_snapshot:
                handler.handle(queued_event)
        self._is_processing_event_queue = False
