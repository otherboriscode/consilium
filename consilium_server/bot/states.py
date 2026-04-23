"""aiogram FSM state groups for multi-step bot dialogs."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class NewDebate(StatesGroup):
    waiting_template = State()
    waiting_topic = State()
    waiting_context_choice = State()
    waiting_files = State()
    waiting_confirm = State()


class NewPack(StatesGroup):
    waiting_name = State()
    waiting_files = State()
