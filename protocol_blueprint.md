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

### 2.2 Framing Rule: Fixed-Width Length-Prefixed Binary Header
TCP is a continuous byte-stream protocol without inherent message boundaries. To guarantee reliable message boundaries, all wire transmissions are prepended with a fixed 4-byte unsigned integer header specifying the exact byte length of the UTF-8 serialized JSON payload.

$$\text{[ 4-Byte Header (Big-Endian UInt32) ]} + \text{[ N-Byte Serialized JSON Payload ]}$$

#### Advantages
1. **No Escaping/Delimiter Collisions**: Payloads can contain newlines, spaces, or raw text without breaking message boundary parsing.
2. **Deterministic Allocation**: Receivers read exactly 4 bytes first, inspect payload length $N$, and allocate/read precisely $N$ bytes.
3. **Immunity to Fragmentation/Coalescing**: Prevents partial JSON parsing errors when TCP segments are fragmented or merged across `recv()` calls.

### 2.3 Wire Stream Examples (Continuous TCP Byte Stream)

#### Example 1: `MOVE` followed by `STATE_UPDATE` (Continuous Stream)
```text
Stream Offset: 00000000
Header (Hex) : 00 00 00 48  (Payload Length = 72 bytes)
Payload (Str): {"msg_type":"MOVE","player_id":"Player_X","payload":{"row":0,"col":2},"timestamp":1727000005}

Stream Offset: 0000004C
Header (Hex) : 00 00 00 7C  (Payload Length = 124 bytes)
Payload (Str): {"msg_type":"STATE_UPDATE","player_id":"SERVER","payload":{"sequence_id":101,"board":["","","X","","","","","",""],"turn":"Player_Y"},"timestamp":1727000006}
