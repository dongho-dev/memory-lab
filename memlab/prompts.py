"""Prompts shared by every memory system, plus the LongMemEval grading templates.

The answer prompt is identical across systems on purpose: differences in score should come
from what each system puts into <memory>, not from prompt wording.

The judge templates are copied from LongMemEval's src/evaluation/evaluate_qa.py
(MIT License, Copyright (c) 2024 Di Wu; see licenses/LongMemEval-LICENSE.txt) so that our
numbers stay comparable with published LongMemEval results.
"""
from __future__ import annotations

NO_MEMORY = "(no memory available)"

ANSWER_SYSTEM = (
    "You are a helpful assistant with long-term memory of your past conversations with this "
    "user. Answer the user's question using the memory you are given."
)

ANSWER_TEMPLATE = """Below is what you remember from past conversations with the user. Each excerpt is tagged with the date of its session.

<memory>
{context}
</memory>

Current date: {question_date}
Question: {question}

Answer based on the memory above. If it does not contain the information needed, say that you don't know. Keep the answer concise."""


def build_answer_prompt(context: str, question: str, question_date: str) -> str:
    return ANSWER_TEMPLATE.format(
        context=context.strip() or NO_MEMORY,
        question=question,
        question_date=question_date or "unknown",
    )



_JUDGE_DEFAULT = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."

_JUDGE_TEMPORAL = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."

_JUDGE_KNOWLEDGE_UPDATE = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."

_JUDGE_PREFERENCE = "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."

_JUDGE_ABSTENTION = "I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the model correctly identifies the question as unanswerable. The model could say that the information is incomplete, or some other information is given but the asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\nModel Response: {}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only."


def judge_prompt(question_type: str, question: str, answer: str, response: str,
                 abstention: bool = False) -> str:
    if abstention:
        template = _JUDGE_ABSTENTION
    elif question_type in ("single-session-user", "single-session-assistant", "multi-session"):
        template = _JUDGE_DEFAULT
    elif question_type == "temporal-reasoning":
        template = _JUDGE_TEMPORAL
    elif question_type == "knowledge-update":
        template = _JUDGE_KNOWLEDGE_UPDATE
    elif question_type == "single-session-preference":
        template = _JUDGE_PREFERENCE
    else:
        raise ValueError(f"unknown question type: {question_type}")
    return template.format(question, answer, response)



AGENT_SYSTEM = ANSWER_SYSTEM + """

Your memory is not shown to you up front. Look things up in it with these actions, one per reply:

search: <query>       keyword search (BM25) over your past conversations. Returns the {k} best-matching excerpts with their session id and date.
read: <session id>    returns that whole past session.
answer: <text>        your final answer to the user. Ends the conversation.

Reply in exactly this format:
REASON: <one or two sentences: what you know so far and why you take this step>
ACTION: <search: ... | read: ... | answer: ...>

You have at most {max_steps} search/read steps. Keyword search matches words, not meaning: if a search misses, try other words (specific items, names, synonyms). If your memory does not contain the information, answer that you don't know. Keep the final answer concise."""

AGENT_FIRST = """Current date: {question_date}
Question: {question}"""

FILES_SYSTEM = ANSWER_SYSTEM + """

Your memory of past conversations with this user is in the current directory: one file per past session under sessions/, named <date>_<session id>.md, with the session date in its first line. Look up whatever you need, in whatever way you like.

Before each tool call, write one short sentence saying why you are making it. When you are done, give your final answer to the question, concisely. If your memory does not contain the information, say that you don't know."""

FILES_BASH_RULE = """

You may also use the shell. The shell already starts in the memory folder, so begin with `ls sessions/` and use relative paths such as `sessions/<file>`. Do not `cd` anywhere else, do not use `$0`, `~` or absolute paths, and if a command fails, retry it inside this folder instead of looking elsewhere. Use only the files in the current directory: do not access anything outside it, and do not use the network."""

NOTES_SYSTEM = """Use progress.md in the current directory as your state document."""

NOTES_SEED = """Because of the context limit, you read these conversations in parts and continue the work from part to part. Write your progress here.
"""

NOTES_TEMPLATE = """Your past conversations with the user, part {part} of {parts}:

{sessions}"""

FILES_NOTES = """

progress.md in the current directory is the state document you kept while reading these conversations."""

SEARCH_LOG_SYSTEM = """

Use progress.md in the current directory as your state document."""

SEARCH_LOG_SEED = """Your memory is larger than your context, so you cannot see it all at once. Keep searching, and build up here what you tried and what came of it (where you looked, and what was and was not there). Decide for yourself when to stop.
"""

