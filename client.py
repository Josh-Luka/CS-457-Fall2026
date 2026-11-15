import argparse
import socket
import sys
import struct
import os

def send_message(sock, message):
    """Sprint 1: Length-prefix framing send logic"""
    encoded = message.encode('utf-8')
    msg_length = struct.pack('!I', len(encoded))
    sock.sendall(msg_length + encoded)

def recv_message(sock):
    """Sprint 1: Length-prefix framing receive logic with timeout for responsive KeyboardInterrupt"""
    sock.settimeout(1.0) # Allows Ctrl+C to break out immediately even when waiting
    while True:
        try:
            raw_msglen = recvall(sock, 4)
            if not raw_msglen:
                return None
            msglen = struct.unpack('!I', raw_msglen)[0]
            data = recvall(sock, msglen)
            if not data:
                return None
            return data.decode('utf-8')
        except socket.timeout:
            continue
        except KeyboardInterrupt:
            raise

def recvall(sock, n):
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data
    
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    parser = argparse.ArgumentParser(description="Sprint 3 Client Application")
    parser.add_argument('-i', '--hostname', required=True, help="Server DNS hostname")
    parser.add_argument('-p', '--port', required=True, type=int, help="Server port")
    args = parser.parse_args()

    try:
        server_ip = socket.gethostbyname(args.hostname)
    except socket.gaierror:
        print(f"[ERROR] Unable to resolve DNS hostname '{args.hostname}'.")
        print("Please check your Cisco router DNS configuration ('ip dns server' / 'ip host') or verify domain spelling.")
        sys.exit(1)
        
    print(f"[SUCCESS] Resolved {args.hostname} to {server_ip}")

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        client_socket.connect((server_ip, args.port))
        print(f"[CONNECTED] Connected to server at {server_ip}:{args.port}")
        
        while True:
            try:
                msg = recv_message(client_socket)
            except socket.timeout:
                continue
                
            if not msg:
                print("\n[DISCONNECTED] Server closed the connection.")
                break
                
            if msg == "SERVER_FULL":
                print("The server is currently full. Try again later.")
                break
            elif msg == "YOUR_TURN":
                print("\n>>> Your Turn! <<<")
                move = input("Enter your move (1-9): ")
                send_message(client_socket, move)
            elif msg == "WAITING":
                print("\nWaiting for opponent's move...")
            elif msg == "INVALID_MOVE":
                print("\n[!] Invalid move or spot already taken. Please try again.")
            elif msg == "WIN":
                print("\n*** CONGRATULATIONS! YOU WIN! ***")
                break
            elif msg == "LOSE":
                print("\n*** GAME OVER. YOU LOSE! ***")
                break
            elif msg == "TIE":
                print("\n*** IT'S A TIE! ***")
                break
            elif msg.startswith("UPDATE"):
                clear_screen()
                print(msg[7:])
            else:
                print(msg)
                
    except ConnectionRefusedError:
        print(f"[ERROR] Connection refused. Is the server running on {server_ip}:{args.port}?")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[DISCONNECTING] Exiting game gracefully...")
    finally:
        client_socket.close()

if __name__ == "__main__":
    main()
