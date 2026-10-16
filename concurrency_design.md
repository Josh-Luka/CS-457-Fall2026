# Server Concurrency & State Synchronization Architecture

## 1. Server Concurrency Architecture & Connection Lifecycle
The server implements **Option A: Multi-Threading** using the Python `threading` module and blocking sockets. 

**Complete Connection Lifecycle:**
1. **Listening & Accept:** The main server thread binds to the designated port and enters an infinite `while True:` loop, calling `server_socket.accept()` to block and wait for incoming TCP connections.
2. **Client Registration:** Upon connection, a new client socket is appended to the shared active client list. A dedicated worker thread (`threading.Thread`) is spawned, passing the client socket and address as arguments.
3. **Active Game Loop Servicing:** Inside the worker thread, the server enters a `while True:` loop using the Sprint 1 framing protocol (`recv_exact(sock, 4)`) to read length-prefixed messages. The thread blocks waiting for data from its specific client without stalling the main server or the opponent's thread.
4. **Socket Teardown:** If a client sends a `DISCONNECT` message, or if `recv()` returns `0` bytes (TCP EOF), or if a `ConnectionResetError` is caught, the worker thread triggers the teardown phase. It removes the socket from the shared client list, safely closes the socket (`sock.close()`), notifies the remaining opponent via a `GAME_OVER` (forfeit) message, and cleanly exits the thread.

## 2. Thread Safety, Lock Acquisition & State Isolation Strategy
Because multiple worker threads run concurrently and mutate the same game session, shared memory structures must be strictly protected from race conditions.

**Explicit Shared Resources:** 
The centralized Game State Object contains the following shared variables:
* **Game Board Matrix:** The 9-element array representing the grid.
* **Active Turn State:** The string/ID indicating whose turn it is.
* **Connected Client Socket List:** Array of active TCP socket objects.
* **Round Scores:** Dictionary mapping player IDs to their win count.

**Lock Acquisition (Critical Sections):** 
A single global `threading.Lock()` (e.g., `game_state_lock`) is utilized. A critical section occurs anytime a thread processes a `MOVE` or alters the state.
1. The thread receives a parsed JSON payload and requests the lock: `with game_state_lock:`
2. **Validation:** It reads the "Active Turn State" and "Game Board Matrix" to ensure the move is legal.
3. **Mutation:** It updates the board array, increments the sequence ID, and switches the turn. If a win/draw is detected, it updates the "Round Scores".
4. **Broadcast:** While still holding the lock, it iterates through the "Connected Client Socket List" and calls `sock.sendall()` to transmit the new state to all clients synchronously.
5. **Release:** The lock is automatically released upon exiting the `with` block, allowing the other thread to process subsequent moves.

## 3. Score & Leaderboard Synchronization Design
Round scores are stored in server memory inside the shared dictionary. Upon detecting a win condition during the Critical Section lock, the server generates a `GAME_OVER` payload containing the updated `final_scores` leaderboard. The server broadcasts this payload synchronously to both clients, signaling them to display the updated scores and reset their local board UI for the next round.

## 4. Move Validation & State Broadcast Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client1 as Client 1 (Player X)
    participant Server as Game Server
    actor Client2 as Client 2 (Player O)

    Client1->>Server: MOVE (row: 0, col: 2)
    
    Note over Server: Thread 1 acquires `game_state_lock`.<br>Validates: Is it Player X's turn?<br>Is cell (0,2) empty?
    
    alt Valid Move (Standard Turn)
        Note over Server: Mutate State: Update Board Matrix.<br>Switch Turn State.
        Server-->>Client1: STATE_UPDATE (Board, Turn: Player O)
        Server-->>Client2: STATE_UPDATE (Board, Turn: Player O)
        Note over Server: Thread 1 releases lock.
        
    else Valid Move (Win Condition & Score Sync)
        Note over Server: Mutate State: Update Board Matrix.<br>Detect Win. Increment Round Scores.
        Server-->>Client1: GAME_OVER (Winner: Player X, final_scores)
        Server-->>Client2: GAME_OVER (Winner: Player X, final_scores)
        Note over Server: Thread 1 releases lock.
        
    else Invalid / Out of Turn Move
        Note over Server: Validation fails.<br>Thread 1 releases lock.
        Server-->>Client1: ERROR (error_code: OUT_OF_TURN)
    end
