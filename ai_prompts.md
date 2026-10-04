# AI Prompting & Constraint Strategy Documentation

## 1. Overview & AI Policy Compliance

This document outlines the constrained system prompts used to enforce strict adherence to Option B (length-prefixed framing mechanism), turn-handshake confirmations (`ACK_STATE`), 10-second retransmit timers, and state suspension/reconnection logic.

---

## 2. System Prompt & Constraint Directive

```text
SYSTEM DIRECTIVE:
You are a network protocol code generator building a Tic-Tac-Toe server over TCP.
You MUST strictly follow docs/protocol_blueprint.md and docs/fsm_specification.md.
1. All framing MUST use Option B: a 4-byte big-endian unsigned integer header (!I) representing length.
2. All messages MUST be UTF-8 encoded JSON containing "msg_type", "player_id", and "timestamp".
3. When Player X completes a turn, send STATE_UPDATE with a unique sequence_id. Do NOT transition to Player Y's turn until Player Y returns an ACK_STATE payload.
4. Implement a 10-second timer: if ACK_STATE is not received within 10 seconds, send a STATE_RETRANSMIT payload.
5. If a connection drops, transition state to STATE_SUSPENDED. When a client reconnects via CONNECT with an existing player_id, restore match state and re-issue the pending STATE_UPDATE.
```

---
## 3. Targeted Implementation Prompts

### 3.1 Prompt 1: Framing Reader/Writer with Header Processing

#### User Prompt
> Write Python functions `send_framed_message(sock, msg_dict)` and `recv_framed_message(sock)` conforming to `protocol_blueprint.md`.
> - Header: Option B length-prefix (4-byte unsigned big-endian integer using `struct.pack("!I", len(payload))`).
> - Receiver loop MUST handle partial chunks via an exact-read helper function (`recv_exact(sock, n)`).
> - Explicitly detect EOF (`b""`) and socket exceptions (`ConnectionResetError`, `BrokenPipeError`), returning `None` to indicate disconnection.

---

### 3.2 Prompt 2: Handshake Timer, Retransmit, and Reconnection Logic

#### User Prompt
> Implement a Python FSM server loop that manages turn handshakes, timers, and reconnections:
> 1. When a player submits a valid `MOVE`, store the un-ACKed state, dispatch `STATE_UPDATE(sequence_id)`, and record `last_sent_time = time.time()`.
> 2. In the non-blocking event/select loop, check if `time.time() - last_sent_time >= 10.0`. If true and `ACK_STATE` has not been received, send `STATE_RETRANSMIT`.
> 3. If a socket raises an exception or returns EOF, set state to `STATE_SUSPENDED` and store game state in `active_games[player_id]`.
> 4. On receiving `CONNECT` with an existing `player_id`, attach the new socket, restore state, re-send `STATE_UPDATE`, and return to `AWAIT_ACK`.
