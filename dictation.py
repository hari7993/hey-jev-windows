"""Dictation: say "Hey Jev, transcribe", talk as long as you like, then "stop transcribing", and the text lands
where your cursor is.

Nothing goes off the PC for this: the speech model that's already listening for the stop phrase writes the words.
"""
import json
import os
import re
import time
from pathlib import Path

from winplatform import log_path

LIMIT = 900  # seconds: a dictation whose stop phrase was never heard ends on its own after a quarter of an hour
FOLDER = os.path.dirname(os.path.abspath(__file__))
HISTORY = log_path("Hey Jev dictation.jsonl")  # one JSON line per finished dictation, for the Dictation history tab
USER_VOCAB = os.path.join(FOLDER, "vocabulary.json")  # the Dictionary tab's words, kept out of git
EXAMPLE_VOCAB = os.path.join(FOLDER, "vocabulary.example.json")

# What starts one: "transcribe", "start dictating", "can you take notes for me", "dictation mode now". Only the whole
# phrase, so "I was transcribing the call yesterday" doesn't start anything
_ASK = r"(?:please|can you|could you)"
_VERB = r"(?:transcrib|dictat)\w*|take notes"
_AFTER = r"this(?: meeting| call)?|notes|mode|now|please|for me"
START = re.compile(rf"^\W*(?:{_ASK}\s+)?(?:start\s+)?(?:{_VERB})(?:\s+(?:{_AFTER}))?\W*$", re.IGNORECASE)

VOCAB = []  # (pattern for a way it was heard, the word it should be)


def read_vocab():
    """{"Word": ["heard as", ...]}: yours once you've saved some, else the examples."""
    return json.loads(Path(USER_VOCAB if os.path.isfile(USER_VOCAB) else EXAMPLE_VOCAB).read_text(encoding="utf-8"))


def load_vocab():
    VOCAB[:] = [(re.compile(rf"\b{re.escape(spelling)}\b", re.IGNORECASE), word)
                for word, heard_as in read_vocab().items() for spelling in heard_as]


def save_vocab(words):
    """Writes the Dictionary tab's words and puts them to use at once."""
    Path(USER_VOCAB).write_text(json.dumps(words, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    load_vocab()


def fix_vocab(text):
    for pattern, word in VOCAB:
        text = pattern.sub(word, text)
    return text


load_vocab()


class Dictation:
    def __init__(self, names):
        # The stop phrase, with her name in front however speech-to-text spelled it: "Hey Jev" has come out as
        # "Hello" and as "Heijev", and either was then pasted at the end of the text
        greeting = r"(?:\b(?:hey|hi|hay|hello|hallo|hullo|okay|ok)\W+)?"
        name = rf"(?:\b(?:hey|hei|he|hi|ha|h|a)?(?:{names})\W+)?"
        self.stop_rx = re.compile(greeting + name + r"\b(?:stop|end|finish)\W+(?:the\W+)?(?:transcri|dictat)\w*\W*$",
                                  re.IGNORECASE)
        self.active, self.heard, self.started = False, [], 0.0

    def start(self):
        self.heard = []
        self.started = time.time()
        self.active = True

    def timed_out(self):
        return self.active and time.time() > self.started + LIMIT

    def add(self, heard):
        """One phrase of it. True once it's over: the stop phrase, or the time limit."""
        if heard:
            self.heard.append(heard)
        return self.stop_rx.search(heard) is not None or self.timed_out()

    def finish(self):
        """All of it as one text, without the stop phrase, and kept in the history."""
        self.active = False
        whole = self.stop_rx.sub("", " ".join(self.heard)).strip(" ,")
        if not whole:
            return ""
        whole = fix_vocab(whole)
        entry = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "text": whole})
        with Path(HISTORY).open("a", encoding="utf-8") as history:
            history.write(entry + "\n")
        return whole
