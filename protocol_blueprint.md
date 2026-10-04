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
#### Example 2: Stream Fragmentation (`ACK_STATE` split across reads)
Shows a single ping confirmation message split mid-stream across network packets.

```text
Packet 1 Read (Header + First 30 Bytes of Payload):
[0x00, 0x00, 0x00, 0x50] + {"msg_type":"ACK_STATE","player

Packet 2 Read (Remaining 50 Bytes of Payload):
_id":"Player_Y","payload":{"sequence_id":101,"status":"VERIFIED"},"timestamp":1727000007}
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

### 3.2 Structured Schema Specifications & Sample Payloads

#### 1. `CONNECT` (Client $\rightarrow$ Server)
* **Purpose**: Registers player session alias or resumes suspended match.
* **Schema**:
  * `msg_type` (string): `"CONNECT"`
  * `player_id` (string): Unique client identifier
  * `timestamp` (integer): Unix timestamp in seconds
```json
{
  "msg_type": "CONNECT",
  "player_id": "Player_X",
  "timestamp": 1727000000
}
```
#### 2. `LOBBY_WAIT` (Server $\rightarrow$ Client)
* **Purpose**: Notifies host that server is listening for opponent.
* **Schema**:
  * `msg_type` (string): `"LOBBY_WAIT"`
  * `player_id` (string): Recipient ID
  * `message` (string): Status description
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "LOBBY_WAIT",
  "player_id": "Player_X",
  "message": "Waiting for opponent to connect...",
  "timestamp": 1727000001
}
```
#### 3. `GAME_START` (Server $\rightarrow$ Client)
* **Purpose**: Signals game initiation and assigns role/symbol.
* **Schema**:
  * `msg_type` (string): `"GAME_START"`
  * `player_id` (string): `"SERVER"`
  * `payload` (object):
    * `assigned_role` (string): `"Player_X"` or `"Player_Y"`
    * `symbol` (string): `"X"` or `"O"`
    * `opponent_id` (string): Opponent ID
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "GAME_START",
  "player_id": "SERVER",
  "payload": {
    "assigned_role": "Player_X",
    "symbol": "X",
    "opponent_id": "Player_Y"
  },
  "timestamp": 1727000002
}
```
#### 4. `MOVE` (Client $\rightarrow$ Server)
* **Purpose**: Active player submits move coordinates.
* **Schema**:
  * `msg_type` (string): `"MOVE"`
  * `player_id` (string): Submitting player ID
  * `payload` (object):
    * `row` (integer): Zero-indexed row coordinate (0–2)
    * `col` (integer): Zero-indexed column coordinate (0–2)
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "MOVE",
  "player_id": "Player_X",
  "payload": {
    "row": 0,
    "col": 2
  },
  "timestamp": 1727000005
}
```
#### 5. `STATE_UPDATE` (Server $\rightarrow$ Client)
* **Purpose**: Broadcasts updated board state requiring ACK ping.
* **Schema**:
  * `msg_type` (string): `"STATE_UPDATE"`
  * `player_id` (string): `"SERVER"`
  * `payload` (object):
    * `sequence_id` (integer): Monotonically increasing turn ID
    * `board` (array of strings): 9-element array representing board cells
    * `turn` (string): Active player ID for next turn
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "STATE_UPDATE",
  "player_id": "SERVER",
  "payload": {
    "sequence_id": 101,
    "board": ["", "", "X", "", "", "", "", "", ""],
    "turn": "Player_Y"
  },
  "timestamp": 1727000006
}
```
#### 6. `ACK_STATE` (Client $\rightarrow$ Server)
* **Purpose**: Confirms opponent verified and accepted updated board state.
* **Schema**:
  * `msg_type` (string): `"ACK_STATE"`
  * `player_id` (string): Responding player ID
  * `payload` (object):
    * `sequence_id` (integer): Sequence ID being acknowledged
    * `status` (string): `"VERIFIED"`
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "ACK_STATE",
  "player_id": "Player_Y",
  "payload": {
    "sequence_id": 101,
    "status": "VERIFIED"
  },
  "timestamp": 1727000007
}
```
#### 7. `STATE_RETRANSMIT` (Server $\rightarrow$ Client)
* **Purpose**: Re-sends state ping after 10-second ACK timeout.
* **Schema**:
  * `msg_type` (string): `"STATE_RETRANSMIT"`
  * `player_id` (string): `"SERVER"`
  * `payload` (object):
    * `retry_attempt` (integer): Retry count (1–3)
    * `sequence_id` (integer): Sequence ID being retransmitted
    * `board` (array of strings): Current 9-element board state
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "STATE_RETRANSMIT",
  "player_id": "SERVER",
  "payload": {
    "retry_attempt": 1,
    "sequence_id": 101,
    "board": ["", "", "X", "", "", "", "", "", ""]
  },
  "timestamp": 1727000016
}
```
#### 8. `ERROR` (Server $\rightarrow$ Client)
* **Purpose**: Notifies client of out-of-turn play, overwriting spaces, or syntax errors.
* **Schema**:
  * `msg_type` (string): `"ERROR"`
  * `player_id` (string): `"SERVER"`
  * `payload` (object):
    * `error_code` (string): `"OUT_OF_TURN"` or `"INVALID_COORDINATES"`
    * `message` (string): Human-readable error message
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "ERROR",
  "player_id": "SERVER",
  "payload": {
    "error_code": "OUT_OF_TURN",
    "message": "It is not your turn. Current turn: Player_Y."
  },
  "timestamp": 1727000018
}
```
#### 9. `DISCONNECT` (Client $\rightarrow$ Server)
* **Purpose**: Graceful client departure notification.
* **Schema**:
  * `msg_type` (string): `"DISCONNECT"`
  * `player_id` (string): Leaving player ID
  * `payload` (object):
    * `reason` (string): Departure reason (e.g., `"USER_QUIT"`)
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "DISCONNECT",
  "player_id": "Player_X",
  "payload": {
    "reason": "USER_QUIT"
  },
  "timestamp": 1727000020
}
```
#### 10. `GAME_OVER` (Server $\rightarrow$ Client)
* **Purpose**: Broadcasts game end outcome, winner/draw, or forfeit status.
* **Schema**:
  * `msg_type` (string): `"GAME_OVER"`
  * `player_id` (string): `"SERVER"`
  * `payload` (object):
    * `outcome` (string): `"WIN"`, `"DRAW"`, or `"FORFEIT"`
    * `winner` (string): ID of winning player or `"NONE"`
    * `reason` (string): Explanation (e.g., `"3 in a row across row 0"` or `"Opponent disconnected"`)
    * `final_scores` (object): Player score map
  * `timestamp` (integer): Unix timestamp
```json
{
  "msg_type": "GAME_OVER",
  "player_id": "SERVER",
  "payload": {
    "outcome": "WIN",
    "winner": "Player_X",
    "reason": "3 in a row across row 0",
    "final_scores": {
      "Player_X": 1,
      "Player_Y": 0
    }
  },
  "timestamp": 1727000021
}
```
## 4. Connection Termination & Socket Lifecycle Management

### 4.1 Graceful Application Disconnection
When a client exits intentionally:
1. Client sends a structured `DISCONNECT` message via the framed socket.
2. Server handles `DISCONNECT`, notifies the remaining player via `GAME_OVER` (declaring forfeit win), and closes socket.
3. Operating System initiates standard TCP 4-way FIN teardown.

### 4.2 Handling the TCP 0-Byte EOF Condition
When a remote socket closes cleanly via TCP FIN, calling `recv()` does not raise an exception; instead, it returns `0 bytes` (`b""` in Python).
* **Infinite Loop Prevention**: Sockets loops MUST check `if not data: break`. Failing to check `b""` causes an infinite loop consuming 100% CPU.

### 4.3 Abrupt Termination & Exception Handling
Network drops, process crashes (`kill -9`), or physical disconnects trigger OS-level socket exceptions during read/write operations:
* **`ConnectionResetError` (TCP RST)**: Peer host crashed or forcefully reset socket.
* **`BrokenPipeError` (`EPIPE`)**: Occurs when writing `sendall()` to a socket closed by peer.

```python
def receive_message(sock):
    try:
        header = recv_exact(sock, 4)
        if not header:  # 0-Byte EOF detected (Clean TCP FIN)
            return None
        length = struct.unpack("!I", header)[0]
        payload = recv_exact(sock, length)
        if not payload:  # EOF during payload extraction
            return None
        return json.loads(payload.decode("utf-8"))
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        return None  # Abrupt connection drop detected
```
