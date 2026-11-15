import argparse
import socket
import threading
import struct
import time

def send_message(conn, message):
    """Sprint 1: Length-prefix framing send"""
    encoded = message.encode('utf-8')
    msg_length = struct.pack('!I', len(encoded))
    conn.sendall(msg_length + encoded)

def recv_message(conn):
    """Sprint 1: Length-prefix framing receive"""
    raw_msglen = recvall(conn, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack('!I', raw_msglen)[0]
    data = recvall(conn, msglen)
    if not data:
        return None
    return data.decode('utf-8')

def recvall(conn, n):
    data = bytearray()
    while len(data) < n:
        packet = conn.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data

# Sprint 1 FSM State Manager for the Game Room
class GameRoom:
    def __init__(self):
        self.lock = threading.Lock()
        self.players = []
        self.current_turn = 0
        self.board = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        self.game_over = False

    def get_board_display(self):
        b = self.board
        return f"\n {b[0]} | {b[1]} | {b[2]} \n---+---+---\n {b[3]} | {b[4]} | {b[5]} \n---+---+---\n {b[6]} | {b[7]} | {b[8]} \n"

# Global game state (supports exactly 1 concurrent 2-player game for Sprint 3 test)
game_room = GameRoom()

# Sprint 2 Concurrency: Threaded connection handler
def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    
    with game_room.lock:
        player_id = len(game_room.players)
        if player_id >= 2:
            send_message(conn, "SERVER_FULL")
            conn.close()
            return
        game_room.players.append(conn)
        
    symbol = "X" if player_id == 0 else "O"
    send_message(conn, f"Connected as Player {player_id + 1} ({symbol}).")
    
    if player_id == 0:
        send_message(conn, "Waiting for Player 2 to join...")
    
    # Wait until both players are connected before starting FSM
    while len(game_room.players) < 2:
        time.sleep(0.5)
    
    # Initial board broadcast
    send_message(conn, "UPDATE\nGame Start!\n" + game_room.get_board_display())
    
    try:
        while not game_room.game_over:
            # Check turn state
            if game_room.current_turn % 2 == player_id:
                send_message(conn, "YOUR_TURN")
                
                # FSM: Read Input
                move_data = recv_message(conn)
                if not move_data:
                    break # Graceful disconnect
                    
                # Process player move
                try:
                    move_idx = int(move_data.strip()) - 1
                    with game_room.lock:
                        if 0 <= move_idx <= 8 and game_room.board[move_idx] not in ["X", "O"]:
                            game_room.board[move_idx] = symbol
                            game_room.current_turn += 1
                            
                            # Broadcast state changes
                            for p in game_room.players:
                                send_message(p, "UPDATE\n" + game_room.get_board_display())
                        else:
                            send_message(conn, "INVALID_MOVE")
                except ValueError:
                    send_message(conn, "INVALID_MOVE")
            else:
                send_message(conn, "WAITING")
                
                # Halt execution for this thread until it is our turn
                last_turn = game_room.current_turn
                while game_room.current_turn == last_turn and not game_room.game_over:
                    time.sleep(0.2)
                    
    except (ConnectionResetError, BrokenPipeError):
        print(f"[DISCONNECT] {addr} closed unexpectedly.")
    finally:
        with game_room.lock:
            if conn in game_room.players:
                game_room.players.remove(conn)
        conn.close()
        print(f"[CLOSED] Connection with {addr} terminated.")

def main():
    parser = argparse.ArgumentParser(description="Sprint 3 Server Application")
    parser.add_argument('-p', '--port', required=True, type=int, help="Listening port")
    args = parser.parse_args()

    # Initialize TCP Socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow port reuse so you aren't locked out if it crashes during local dev
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to 0.0.0.0 as required for Sprint 4 CML infrastructure
    server_socket.bind(('0.0.0.0', args.port))
    server_socket.listen()
    print(f"[LISTENING] Server is listening on 0.0.0.0:{args.port}")

    try:
        while True:
            # Main loop only handles accepting new connections
            conn, addr = server_socket.accept()
            
            # Dispatch connection to independent worker thread (Sprint 2 spec)
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()
            
            print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()
