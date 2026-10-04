# Application Protocol Blueprint & Network Messaging Specification
## Tic-Tac-Toe Custom Messaging Protocol with State Handshaking & Session Recovery

## 1. Overview & Objectives

This document specifies the custom application-layer messaging protocol designed for a networked Tic-Tac-Toe game over TCP. The protocol enforces deterministic binary length-prefix framing, mandatory board-state confirmation handshakes (`STATE_UPDATE` $\rightarrow$ `ACK_STATE`), 10-second retransmit timers, and a state suspension/reconnection architecture to handle transient drops without losing match context.

---

## 2. Transport Layer & Packet Framing Mechanism

### 2.1 Transport Protocol
- **Transport Protocol**: Transmission Control Protocol (TCP)
- **Serialization Format**: UTF-8 Encoded JSON
- **Byte Order**: Network Byte Order (Big-Endian, `!` in Python `struct`)

### 2.2 Framing Rule: Fixed-Width Length-Prefixed Binary Header (Option B)
TCP is a continuous byte-stream protocol without inherent message boundaries. To guarantee reliable message boundaries and solve TCP stream fragmentation (messages split across multiple `recv()` calls) and coalescing (multiple back-to-back messages arriving in a single `recv()` chunk), all wire transmissions are prepended with a fixed 4-byte unsigned integer header specifying the exact byte length of the UTF-8 serialized JSON payload.

$$\text{[ 4-Byte Header (Big-Endian UInt32) ]} + \text{[ N-Byte Serialized JSON Payload ]}$$

#### Receiver Extraction Logic
1. **Read Header**: Read exactly 4 bytes from the TCP stream using an exact-read buffer accumulator (`recv_exact(sock, 4)`).
2. **Unpack Header**: Unpack the 4 bytes using Network Byte Order (`struct.unpack("!I", header)`), yielding payload byte length $N$.
3. **Read Payload**: Read exactly $N$ bytes from the stream using the accumulator (`recv_exact(sock, N)`).
4. **Deserialize**: Decode UTF-8 bytes to string and parse JSON object.

#### Advantages
1. **No Escaping/Delimiter Collisions**: Payloads can contain newlines, spaces, or raw text without breaking message boundary parsing.
2. **Deterministic Allocation**: Receivers read exactly 4 bytes first, inspect payload length $N$, and allocate/read precisely $N$ bytes.
3. **Immunity to Fragmentation/Coalescing**: Prevents partial JSON parsing errors when TCP segments are fragmented or merged across `recv()` calls.

### 2.3 On-the-Wire Raw Byte Stream Examples (Continuous TCP Stream)

#### Example 1: Stream Coalescing (`MOVE` followed immediately by `STATE_UPDATE`)
Shows two complete back-to-back messages arriving in a single continuous byte stream.

```text
Stream Offset: 00000000
Header (Hex) : 00 00 00 48  (Payload Length = 72 bytes)
Payload (Str): {"msg_type":"MOVE","player_id":"Player_X","payload":{"row":0,"col":2},"timestamp":1727000005}

Stream Offset: 0000004C
Header (Hex) : 00 00 00 7C  (Payload Length = 124 bytes)
Payload (Str): {"msg_type":"STATE_UPDATE","player_id":"SERVER","payload":{"sequence_id":101,"board":["","","X","","","","","",""],"turn":"Player_Y"},"timestamp":1727000006}
```
### 3.1 Message Summary Table

| Message Type | Direction | Purpose & Description |
| :--- | :--- | :--- |
| `CONNECT` | Client $\rightarrow$ Server | Client requests entry or session resume using `player_id`. |
| `LOBBY_WAIT` | Server $\rightarrow$ Client | Server notifies Player X to await Player Y connection. |
| `GAME_START` | Server $\rightarrow$ Client | Server announces game start and assigns symbols (`X` / `O`). |
| `MOVE` | Client $\rightarrow$ Server | Active player submits move coordinates (`row`, `col`). |
| `STATE_UPDATE` | Server $\rightarrow$ Client | Server broadcasts board state and `sequence_id` after a turn. |
| `ACK_STATE` | Client $\rightarrow$ Server | Opponent confirms receipt and verification of board state. |
| `STATE_RETRANSMIT` | Server $\rightarrow$ Client | Periodic ping re-sent after 10s if `ACK_STATE` is not received. |
| `ERROR` | Server $\rightarrow$ Client | Server notifies client of invalid move, out-of-turn play, or malformed packet. |
| `DISCONNECT` | Client $\rightarrow$ Server | Client indicates intent to quit gracefully. |
| `GAME_OVER` | Server $\rightarrow$ Client | Server broadcasts match end, winner/draw status, and final scores. |
---
