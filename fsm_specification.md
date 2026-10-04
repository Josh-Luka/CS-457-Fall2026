# Finite State Machine (FSM) Specification
## Tic-Tac-Toe Game Engine with Handshake Verification and Reconnection Recovery

## Mermaid FSM State Diagram
```mermaid
stateDiagram-v2
    [*] --> INIT
    
    INIT --> WAITING_FOR_PLAYERS : Server Started on Player x Client & Listening for Player y
    
    WAITING_FOR_PLAYERS --> GAME_START : Player Y Connected
    
    GAME_START --> PLAYER_TURN : Initialize Board & Confirm Connection
    
    PLAYER_TURN --> AWAIT_ACK : Active Player Sends MOVE (Broadcast STATE_UPDATE)
    PLAYER_TURN --> PLAYER_TURN : Invalid Move (Over Wrote Previously Claimed Space) / Out of Turn (Send ERROR)
    
    AWAIT_ACK --> EVALUATE_MOVE : Receive ACK_STATE from Opponent
    AWAIT_ACK --> AWAIT_ACK : 10s Timeout (Send STATE_RETRANSMIT)
    AWAIT_ACK --> STATE_SUSPENDED : Client Disconnects / Drop Detected
    
    STATE_SUSPENDED --> AWAIT_ACK : Client Reconnects (Resume Session)
    STATE_SUSPENDED --> GAME_OVER : Reconnect Timeout Expired (Forfeit)
    
    EVALUATE_MOVE --> PLAYER_TURN : Valid Move (Empty space taken within game board) & ACK Verified (Next Player Turn)
    EVALUATE_MOVE --> GAME_OVER : Victory or Draw Detected
    
    GAME_OVER --> CLEANUP : Broadcast Final Results
    
    CLEANUP --> WAITING_FOR_PLAYERS : Reset State
```
## State Definitions
| State Name | Description |
| :--- | :--- |
| `INIT` | Game host process initializes networking and socket bindings. |
| `WAITING_FOR_PLAYERS` | Player X host starts listening for Player Y to connect. |
| `GAME_START` | Both players connected; game board initialized and connection confirmed. |
| `PLAYER_TURN` | Active player's turn. Out-of-turn moves or overwriting taken spaces trigger error payloads. |
| `AWAIT_ACK` | Active player submitted move; host waiting for `ACK_STATE` from opponent. 10s timer active. |
| `EVALUATE_MOVE` | Move verified via `ACK_STATE`; evaluates valid empty space placements, win/draw conditions, or turn toggles. |
| `STATE_SUSPENDED` | Opponent connection dropped. Match paused awaiting session reconnect. |
| `GAME_OVER` | Game concluded via victory, draw, or forfeit timeout. |
| `CLEANUP` | Broadcasts final results and resets board state to accept new matches. |

## State Transition Logic
