import asyncio
import base64
import json
import re
from pathlib import Path

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import sarvam
from customer import CUSTOMER, OPENING_INSTRUCTION, SUMMARY_PROMPT, SYSTEM_PROMPT

app = FastAPI()
# the page may be hosted on a different origin (e.g. Vercel) than this API
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
STATIC = Path(__file__).parent / "static"

# sentence boundary: Hindi danda, ! ? or ". " (not decimals like 4.5)
SENT_END = re.compile(r"(?<=[।!?])\s+|(?<=[.])\s+")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/customer")
def customer():
    return CUSTOMER


def split_sentences(buf: str, first: bool):
    """Return (ready_sentences, remainder). The first chunk is flushed early at a comma to cut latency."""
    parts = SENT_END.split(buf)
    ready, rest = parts[:-1], parts[-1]
    if first and not ready and len(rest) > 45 and "," in rest:
        i = rest.rfind(",")
        ready, rest = [rest[: i + 1]], rest[i + 1 :]
    return [s.strip() for s in ready if s.strip()], rest


class CallSession:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.history: list[dict] = []
        self.bot_task: asyncio.Task | None = None
        self.allow_barge_in = True

    # ---- bot speaking -------------------------------------------------
    async def bot_turn(self, first: bool = False):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history
        if first:
            msgs.append({"role": "user", "content": OPENING_INSTRUCTION})
        spoken: list[str] = []
        queue: asyncio.Queue = asyncio.Queue()

        async def producer():
            gen = sarvam.chat_stream(msgs)
            buf, is_first = "", True
            try:
                while True:
                    delta = await asyncio.to_thread(next, gen, None)
                    if delta is None:
                        break
                    buf += delta
                    ready, buf = split_sentences(buf, is_first)
                    for s in ready:
                        is_first = False
                        # start synthesis immediately; consumer awaits in order
                        await queue.put((s, asyncio.create_task(asyncio.to_thread(sarvam.speak, s))))
                if buf.strip():
                    s = buf.strip()
                    await queue.put((s, asyncio.create_task(asyncio.to_thread(sarvam.speak, s))))
            finally:
                await queue.put(None)

        prod = asyncio.create_task(producer())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                sentence, audio_task = item
                audio = await audio_task
                await self.ws.send_json({"type": "bot", "text": sentence})
                await self.ws.send_bytes(audio)
                spoken.append(sentence)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            await self.ws.send_json({"type": "error", "text": f"Bot error: {e}"})
        finally:
            prod.cancel()
            if spoken:
                self.history.append({"role": "assistant", "content": " ".join(spoken)})
            try:
                await self.ws.send_json({"type": "bot_done"})
            except Exception:  # noqa: BLE001
                pass

    def start_bot(self, first: bool = False):
        self.bot_task = asyncio.create_task(self.bot_turn(first))

    async def stop_bot(self):
        t = self.bot_task
        if t and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # ---- customer speaking (STT events) -------------------------------
    async def on_stt_message(self, raw: str):
        msg = json.loads(raw)
        kind, data = msg.get("type"), msg.get("data", {})
        if kind == "events" and data.get("signal_type") == "START_SPEECH":
            await self.ws.send_json({"type": "customer_speaking"})
            if self.allow_barge_in:
                await self.stop_bot()
                await self.ws.send_json({"type": "barge_in"})
        elif kind == "data":
            text = (data.get("transcript") or "").strip()
            if not text:
                return
            await self.stop_bot()
            self.history.append({"role": "user", "content": text})
            await self.ws.send_json({"type": "customer", "text": text})
            self.start_bot()
        elif kind == "error":
            await self.ws.send_json({"type": "error", "text": f"STT error: {data}"})

    # ---- report --------------------------------------------------------
    async def report(self):
        transcript = "\n".join(
            f"{'Agent' if m['role'] == 'assistant' else 'Customer'}: {m['content']}"
            for m in self.history
        )
        raw = await asyncio.to_thread(
            sarvam.chat, [{"role": "user", "content": SUMMARY_PROMPT + transcript}], 0.1
        )
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return json.loads(m.group(0)) if m else {"summary": raw}
        except json.JSONDecodeError:
            return {"summary": raw}


@app.websocket("/ws")
async def call(ws: WebSocket):
    await ws.accept()
    s = CallSession(ws)
    try:
        async with websockets.connect(
            sarvam.STT_WS_URL, additional_headers=sarvam.ws_headers(), max_size=None
        ) as stt:

            async def stt_reader():
                async for raw in stt:
                    await s.on_stt_message(raw)

            reader = asyncio.create_task(stt_reader())
            await ws.send_json({"type": "ready"})
            s.start_bot(first=True)
            try:
                while True:
                    m = await ws.receive()
                    if m.get("bytes") is not None:
                        await stt.send(
                            json.dumps(
                                {
                                    "audio": {
                                        "data": base64.b64encode(m["bytes"]).decode(),
                                        "sample_rate": "16000",
                                        "encoding": "audio/wav",
                                    }
                                }
                            )
                        )
                    elif m.get("text") is not None:
                        ctl = json.loads(m["text"])
                        if ctl.get("type") == "config":
                            s.allow_barge_in = bool(ctl.get("barge_in", True))
                        elif ctl.get("type") == "end":
                            break
                    elif m.get("type") == "websocket.disconnect":
                        raise WebSocketDisconnect()
            finally:
                reader.cancel()
        await s.stop_bot()
        await ws.send_json({"type": "report", "data": await s.report()})
    except WebSocketDisconnect:
        await s.stop_bot()
    except Exception as e:  # noqa: BLE001
        try:
            await ws.send_json({"type": "error", "text": f"Server error: {e}"})
        except Exception:  # noqa: BLE001
            pass


# serve config.js etc. (registered last so /ws and /api routes win)
app.mount("/", StaticFiles(directory=STATIC), name="static")
