from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from typing import Any

from backend.engine.domain.commands import Command
from backend.engine.domain.events import Event
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)

Message = Command | Event
Handler = Callable[..., Any]


class MessageBus:
    def __init__(
        self,
        uow: UnitOfWork,
        command_handlers: dict[type[Command], Handler],
        event_handlers: dict[type[Event], list[Handler]],
    ) -> None:
        self.uow = uow
        self.command_handlers = command_handlers
        self.event_handlers = event_handlers

    def handle(self, message: Message) -> list[Any]:
        results = []
        queue: deque[Message] = deque([message])
        while queue:
            msg = queue.popleft()
            if isinstance(msg, Command):
                new_events, cmd_result = self._handle_command(msg)
                results.append(cmd_result)
                queue.extend(new_events)
            elif isinstance(msg, Event):
                self._handle_event(msg)
        return results

    def _handle_command(self, command: Command) -> tuple[list[Event], Any]:
        logger.debug(f"Handling command: {command}")
        handler = self.command_handlers.get(type(command))
        if handler is None:
            raise ValueError(f"No handler registered for {type(command).__name__}")

        with self.uow:
            result = handler(command, self.uow)
            self.uow.commit()
            collected_events = list(self.uow.events)

        return collected_events, result

    def _handle_event(self, event: Event) -> None:
        logger.debug(f"Handling event: {event}")
        handlers = self.event_handlers.get(type(event), [])
        for handler in handlers:
            with self.uow:
                handler(event, self.uow)
