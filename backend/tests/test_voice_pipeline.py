import asyncio

from app.voice.pipeline import speak_sentences, take_sentences


def test_take_sentences_keeps_the_unfinished_tail():
    sentences, rest = take_sentences("Hello there. How are you? Still talking")
    assert sentences == ["Hello there.", "How are you?"]
    assert rest == "Still talking"


def test_decimals_do_not_split_a_sentence():
    sentences, rest = take_sentences("The expedited shipping cost is $18.")
    assert sentences == ["The expedited shipping cost is $18."]
    assert rest == ""


def test_barge_in_stops_before_the_next_sentence():
    cancel = asyncio.Event()
    sent = []

    class ScriptedTTS:
        def __init__(self):
            self.calls = 0

        async def synthesize(self, text: str) -> bytes:
            self.calls += 1
            return f"audio-{self.calls}".encode()

    tts = ScriptedTTS()

    async def send(audio: bytes) -> None:
        sent.append(audio)
        cancel.set()

    status = asyncio.run(speak_sentences(["One complete sentence.", "Two."], tts, cancel, send))
    assert status == "interrupted"
    assert sent == [b"audio-1"]
    assert tts.calls == 1
