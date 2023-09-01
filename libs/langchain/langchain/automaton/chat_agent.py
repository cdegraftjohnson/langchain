"""Module contains code for a general chat agent."""
from __future__ import annotations

import ast
import re
from typing import Sequence, Union, Optional, List

from langchain.automaton.prompt_generators import MessageLogPromptValue
from langchain.automaton.runnables import create_llm_program
from langchain.automaton.typedefs import (
    MessageLog,
    AgentFinish,
    MessageLike,
    FunctionCall,
    FunctionResult,
)
from langchain.schema.language_model import BaseLanguageModel
from langchain.schema.messages import SystemMessage, BaseMessage
from langchain.tools import BaseTool


class ActionEncoder:
    def __init__(self) -> None:
        """Initialize the ActionParser."""
        self.pattern = re.compile(r"<action>(?P<action_blob>.*?)<\/action>", re.DOTALL)

    def decode(self, text: Union[BaseMessage, str]) -> Optional[MessageLike]:
        """Decode the action."""
        if isinstance(text, BaseMessage):
            text = text.content
        match = self.pattern.search(text)
        if match:
            action_blob = match.group("action_blob")
            data = ast.literal_eval(action_blob)
            name = data["action"]
            if name == "Final Answer":  # Special cased "tool" for final answer
                return AgentFinish(result=data["action_input"])
            return FunctionCall(
                name=data["action"], arguments=data["action_input"] or {}
            )
        else:
            return None

    def encode_as_str(self, function_call: FunctionCall) -> str:
        """Encode the action."""
        if function_call.name == "Final Answer":
            return f"<action>{{'action': 'Final Answer', 'action_input': '{function_call.arguments}'}}</action>"
        return f"<action>{{'action': '{function_call.name}', 'action_input': {function_call.arguments}}}</action>"


def prompt_generator(log: MessageLog) -> List[BaseMessage]:
    """Generate a prompt from a log of message like objects."""
    messages = []
    for message in log.messages:
        if isinstance(message, BaseMessage):
            messages.append(message)
        elif isinstance(message, FunctionResult):
            messages.append(
                SystemMessage(
                    content=f"Observation: {message.result}",
                )
            )
        else:
            pass
    return messages


class ChatAgent:
    """An agent for chat models."""

    def __init__(
        self,
        llm: BaseLanguageModel,
        tools: Sequence[BaseTool],
        *,
        max_iterations: int = 10,
    ) -> None:
        """Initialize the chat automaton."""
        action_encoder = ActionEncoder()
        self.llm_program = create_llm_program(
            llm,
            prompt_generator=MessageLogPromptValue.from_message_log,
            tools=tools,
            parser=action_encoder.decode,
        )
        self.max_iterations = max_iterations

    def run(self, message_log: MessageLog) -> None:
        """Run the agent."""
        if not message_log:
            raise AssertionError(f"Expected at least one message in message_log")

        for _ in range(self.max_iterations):
            last_message = message_log[-1]

            if isinstance(last_message, AgentFinish):
                break

            messages = self.llm_program.invoke(message_log)
            message_log.add_messages(messages)
