# Server Concurrency & State Synchronization Architecture

## 1. Server Concurrency Model Selection
The server implements **Option A: Multi-Threading** using the Python `threading` module and standard blocking sockets. 

**Execution Flow:** 
The main server thread listens for incoming TCP connections. Upon a successful `accept()`, a dedicated worker thread (`threading.Thread`) is spawned to handle the new client socket. 

**Justification & Blocking I/O Compatibility:** 
Because each client connection operates within its own isolated thread, the server can safely utilize the blocking `recv_exact(sock, 4)` length-prefixed framing extraction logic defined in the Sprint 1 protocol blueprint. The worker thread will block while awaiting the 4-byte Big-Endian header or the subsequent JSON payload without stalling the opponent's thread or the main server loop.

## 2. Thread Safety & Mutex Locking Strategy
Because multiple client threads run concurrently and interact with the same underlying game instance, shared memory structures must be strictly protected from race conditions.

**Shared State:** 
The server maintains a centralized Game State Object in memory containing:
* The 9-element board array.
* The active turn tracker (`turn`).
* The sequence ID counter (`sequence_id`).
* The score dictionary.
* The active client socket list.

**Lock Acquisition Strategy:** 
A single `threading.Lock()` (e.g., `game_state_lock`) is instantiated globally for the game session. Whenever a thread needs to evaluate or mutate the game state, it must acquire the lock (e.g., using a `with game_state_lock:` context manager). 

**Critical Section Execution:**
1. Thread acquires the lock.
2. Thread verifies move validity against the current board state and turn tracker.
3. Thread updates the board array, increments the `sequence_id`, and switches the active `turn`.
4. Thread constructs the `STATE_UPDATE` payload and transmits it to the clients.
5. Thread releases the lock.

## 3. Score & Leaderboard Synchronization Design
**Memory Storage:** 
Round scores are maintained in the shared Game State Object as a Python dictionary mapping the `player_id` to integer scores (e.g., `{"Player_X": 1, "Player_Y": 0}`). This dictionary is protected by the `game_state_lock`.

**Broadcast Logic:** 
Upon the completion of a round (triggered by a win condition or a draw), the thread handling the final valid `MOVE` acquires the state lock, updates the internal score dictionary, and generates a `GAME_OVER` message. The server iterates through the shared client socket list and transmits the length-prefixed `GAME_OVER` JSON payload—containing the `final_scores` mapping and the outcome reason—to both clients synchronously.

## 4. State & Score Broadcast Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client1 as Client 1 (Player X)
    participant Server as Game Server
    actor Client2 as Client 2 (Player O)

    Client1->>Server: MOVE (row: 0, col: 2)
    
    Note over Server: Thread 1 acquires lock.<br>Validates: Is it Player X's turn?<br>Is cell (0,2) empty?
    
    alt Valid Move
        Note over Server: Update Board Array<br>Increment sequence_id<br>Switch Turn<br>Release lock.
        Server-->>Client1: STATE_UPDATE (sequence_id: 101, turn: Player_Y)
        Server-->>Client2: STATE_UPDATE (sequence_id: 101, turn: Player_Y)
        
        Note over Client1, Client2: Clients parse length-prefixed payload<br>Verify board state
        Client1->>Server: ACK_STATE (sequence_id: 101, status: VERIFIED)
        Client2->>Server: ACK_STATE (sequence_id: 101, status: VERIFIED)
        
    else Invalid / Out of Turn Move
        Note over Server: Thread 1 identifies out-of-turn execution.<br>Releases lock.
        Server-->>Client1: ERROR (error_code: OUT_OF_TURN)
    end
