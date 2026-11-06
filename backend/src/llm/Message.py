Message = dict[str, str]
Messages = list[Message]


def add_system_prompt(messages: Messages, text: str) -> Messages:
    messages.insert(0, {"role": "system", "content": text})
    return messages


def add_user_message(messages: Messages, text: str) -> Messages:
    messages.append({"role": "user", "content": text})
    return messages


def add_assistant_message(messages: Messages, text: str) -> Messages:
    messages.append({"role": "assistant", "content": text})
    return messages
