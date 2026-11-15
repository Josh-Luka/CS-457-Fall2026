import argparse
import socket
import threading
import struct
import time

def send_message(conn, message):
    encoded = message.encode('utf-8')
    msg_length = struct.pack('!I', len(encoded))
    conn.sendall(msg_length + encoded)

def recv_message(conn):
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

class GameRoom:
    def __init__(self):
        self.lock = threading.Lock()
        self.players = []          # List of tuples: (conn, addr)
        self.current_turn = 0
        self.board = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        self.game_over = False

    def reset(self):
        self.current_turn = 0
        self.board = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        self.game_over = False

    def get_board_display(self):
        b = self.board
        return f"\n {b[0]} | {b[1]} | {b[2]} \n---+---+---\n {b[3]} | {b[4]} | {b[5]} \n---+---+---\n {b[6]} | {b[7]} | {b[8]} \n"

    def check_winner(self):
        wins = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8), # Rows
            (0, 3, 6), (1, 4, 7), (2, 5, 8), # Cols
            (0, 4, 8), (2, 4, 6)             # Diagonals
        ]
        for a, b, c in wins:
            if self.board[a] == self.board[b] == self.board[c] and self.board[a] in ["X", "O"]:
                return self.board[a] # Returns 'X' or 'O'
        if all(spot in ["X", "O"] for spot in self.board):
            return "TIE"
        return None

game_room = GameRoom()

def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    
    with game_room.lock:
        if len(game_room.players) >= 2:
            send_message(conn, "SERVER_FULL")
            conn.close()
            return
        game_room.players.append((conn, addr))
        player_id = len(game_room.players) - 1
        
    symbol = "X" if player_id == 0 else "O"
    send_message(conn, f"Connected as Player {player_id + 1} ({symbol}).")
    
    if player_id == 0:
        send_message(conn, "Waiting for Player 2 to join...")
    
    # Wait until 2 players are connected
    while True:
        with game_room.lock:
            if len(game_room.players) < 2:
                pass
            else:
                break
        time.sleep(0.5)
    
    # If game was reset or starting fresh, initialize board for both when player 2 joins
    with game_room.lock:
        if player_id == 0 and game_room.game_over:
            game_room.reset()

    time.sleep(0.2) # Small sync delay
    send_message(conn, "UPDATE\nGame Start!\n" + game_room.get_board_display())
    
    try:
        while True:
            with game_room.lock:
                if game_room.game_over:
                    break
                is_my_turn = (game_room.current_turn % 2 == player_id)

            if is_my_turn:
                send_message(conn, "YOUR_TURN")
                move_data = recv_message(conn)
                if not move_data:
                    break # Disconnect
                
                try:
                    move_idx = int(move_data.strip()) - 1
                    with game_room.lock:
                        if 0 <= move_idx <= 8 and game_room.board[move_idx] not in ["X", "O"]:
                            game_room.board[move_idx] = symbol
                            
                            winner = game_room.check_winner()
                            if winner:
                                game_room.game_over = True
                                # Broadcast final board
                                for idx, (p_conn, _) in enumerate(game_room.players):
                                    send_message(p_conn, "UPDATE\n" + game_room.get_board_display())
                                    if winner == "TIE":
                                        send_message(p_conn, "TIE")
                                    elif (winner == "X" and idx == 0) or (winner == "O" and idx == 1):
                                        send_message(p_conn, "WIN")
                                    else:
                                        send_message(p_conn, "LOSE")
                            else:
                                game_room.current_turn += 1
                                for p_conn, _ in game_room.players:
                                    send_message(p_conn, "UPDATE\n" + game_room.get_board_display())
                        else:
                            send_message(conn, "INVALID_MOVE")
                except ValueError:
                    send_message(conn, "INVALID_MOVE")
            else:
                send_message(conn, "WAITING")
                # Wait until turn changes or game ends
                while True:
                    with game_room.lock:
                        if game_room.game_over or (game_room.current_turn % 2 == player_id):
                            break
                    time.sleep(0.2)
                    
    except (ConnectionResetError, BrokenPipeError):
        print(f"[DISCONNECT] {addr} closed unexpectedly.")
    finally:
        with game_room.lock:
            # Remove this player from room
            game_room.players = [p for p in game_room.players if p[0] != conn]
            game_room.reset() # Reset room so next players get a fresh game
            # Notify remaining player if any
            for p_conn, _ in game_room.players:
                try:
                    send_message(p_conn, "\n[NOTICE] Opponent disconnected. Resetting room, waiting for new player...")
                except:
                    pass
        conn.close()
        print(f"[CLOSED] Connection with {addr} terminated.")

def main():
    parser = argparse.ArgumentParser(description="Sprint 3 Server Application")
    parser.add_argument('-p', '--port', required=True, type=int, help="Listening port")
    args = parser.parse_args()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind(('0.0.0.0', args.port))
    server_socket.listen()
    print(f"[LISTENING] Server is listening on 0.0.0.0:{args.port}")

    try:
        while True:
            conn, addr = server_socket.accept()
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
