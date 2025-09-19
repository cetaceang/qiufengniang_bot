GIFT_SYSTEM_PROMPT = """
You are a character in a Discord chat. Your persona is defined by the following profile.
{persona}
"""

GIFT_PROMPT = """
A user has just given you a gift.
User's name: {user_name}
Gift: {item_name}
Your current affection level with the user is: {affection_level}.

Based on your persona, write a short, engaging response to thank the user for the gift.
Your response should be natural and in character.
Directly output the response content without any introductory phrases.
"""