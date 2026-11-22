import argparse
import json
import socket
import struct
import sys
import threading
from typing import Any, Dict, List, Optional


DEFAULT_SERVER = "server.luka.edu"
DEFAULT_PORT = 8080
HEADER_STRUCT = struct.Struct("!I")
MAX_PAYLOAD_BYTES = 65536


def sendFramedMessage(sock: socket.socket, payload: Dict[str, Any]) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("Payload exceeds maximum allowed byte size.")
    frame = HEADER_STRUCT.pack(len(encoded)) + encoded
    sock.sendall(frame)


def recvExact(sock: socket.socket, byteCount: int) -> Optional[bytes]:
    chunks = bytearray()
    while len(chunks) < byteCount:
        remaining = byteCount - len(chunks)
        chunk = sock.recv(remaining)
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def recvFramedMessage(sock: socket.socket) -> Optional[Dict[str, Any]]:
    rawHeader = recvExact(sock, HEADER_STRUCT.size)
    if rawHeader is None:
        return None
    messageLength = HEADER_STRUCT.unpack(rawHeader)[0]
    if messageLength <= 0 or messageLength > MAX_PAYLOAD_BYTES:
        raise ValueError(f"Invalid framed message length: {messageLength}")
    rawBody = recvExact(sock, messageLength)
    if rawBody is None:
        return None
    decoded = json.loads(rawBody.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Decoded JSON frame must be an object.")
    return decoded


def renderBoard(board: List[str], scores: Dict[str, int], activeTurn: str, gamePhase: str, mySymbol: Optional[str]) -> None:
    cells = []
    for idx in range(9):
        val = board[idx]
        if val == "":
            cells.append(str(idx))
        else:
            cells.append(val)

    print("\n" + "=" * 38)
    if mySymbol is not None:
        print(f"You are Player: {mySymbol} | Phase: {gamePhase} | Turn: {activeTurn}")
    else:
        print(f"Phase: {gamePhase} | Turn: {activeTurn}")
    print(f"Scores -> X: {scores.get('X', 0)} | O: {scores.get('O', 0)} | Ties: {scores.get('TIES', 0)}")
    print("-" * 38)
    print(f"  {cells[0]} | {cells[1]} | {cells[2]} ")
    print(" ---+---+---")
    print(f"  {cells[3]} | {cells[4]} | {cells[5]} ")
    print(" ---+---+---")
    print(f"  {cells[6]} | {cells[7]} | {cells[8]} ")
    print("=" * 38)


class ClientState:
    def __init__(self, alias: str) -> None:
        self.alias = alias
        self.lock = threading.Lock()
        self.symbol: Optional[str] = None
        self.board: List[str] = [""] * 9
        self.scores: Dict[str, int] = {"X": 0, "O": 0, "TIES": 0}
        self.activeTurn: str = "X"
        self.gamePhase: str = "CONNECTING"


def receiveLoop(sock: socket.socket, state: ClientState, stopEvent: threading.Event) -> None:
    try:
        while not stopEvent.is_set():
            msg = recvFramedMessage(sock)
            if msg is None:
                print("\n[DISCONNECTED] Server closed connection.")
                stopEvent.set()
                break

            msgType = msg.get("type")
            with state.lock:
                if "yourSymbol" in msg and msg["yourSymbol"] in ("X", "O"):
                    state.symbol = msg["yourSymbol"]
                if "board" in msg and isinstance(msg["board"], list):
                    state.board = list(msg["board"])
                if "scores" in msg and isinstance(msg["scores"], dict):
                    state.scores = dict(msg["scores"])
                if "activeTurn" in msg:
                    state.activeTurn = str(msg["activeTurn"])
                if "gamePhase" in msg:
                    state.gamePhase = str(msg["gamePhase"])

                infoText = str(msg.get("message", ""))
                if msgType == "STATE_RESUME":
                    print(f"\n[STATE_RESUME] {infoText}")
                    renderBoard(state.board, state.scores, state.activeTurn, state.gamePhase, state.symbol)
                elif msgType in ("GAME_START", "STATE_UPDATE", "GAME_OVER", "WAITING"):
                    print(f"\n[{msgType}] {infoText}")
                    renderBoard(state.board, state.scores, state.activeTurn, state.gamePhase, state.symbol)
                elif msgType == "ERROR":
                    print(f"\n[SERVER ERROR] {infoText}")
                else:
                    print(f"\n[{msgType}] {infoText}")

            if state.activeTurn == state.symbol and state.gamePhase == "IN_PROGRESS":
                print("Enter cell index (0-8) or 'reset' > ", end="", flush=True)

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if not stopEvent.is_set():
            print(f"\n[NETWORK ERROR] {exc}")
            stopEvent.set()


def resolveTargetAddress(targetHost: str, port: int) -> str:
    try:
        resolvedIp = socket.gethostbyname(targetHost)
        print(f"[DNS] Resolved '{targetHost}' -> {resolvedIp}:{port}")
        return resolvedIp
    except socket.gaierror as exc:
        print(f"[DNS ERROR] Failed to resolve '{targetHost}': {exc}", file=sys.stderr)
        sys.exit(1)


def parseArguments(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CS-457 Stateful Tic-Tac-Toe TCP Client"
    )
    parser.add_argument(
        "-i",
        "--ip",
        dest="serverHost",
        default=DEFAULT_SERVER,
        help=f"Server hostname or IP address (default: {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Server TCP port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "-a",
        "--alias",
        dest="alias",
        required=True,
        help="Player alias/ID used to join or resume an active match",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parseArguments(sys.argv[1:])
    resolvedIp = resolveTargetAddress(args.serverHost, args.port)
    state = ClientState(alias=args.alias)
    stopEvent = threading.Event()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((resolvedIp, args.port))
        sendFramedMessage(sock, {"type": "CONNECT", "alias": args.alias})
    except OSError as exc:
        print(f"[CONNECTION FAILED] Could not connect to {resolvedIp}:{args.port}: {exc}", file=sys.stderr)
        sock.close()
        sys.exit(1)

    readerThread = threading.Thread(
        target=receiveLoop,
        args=(sock, state, stopEvent),
        daemon=True,
    )
    readerThread.start()

    try:
        while not stopEvent.is_set():
            try:
                userInput = input()
            except EOFError:
                break

            cleaned = userInput.strip().lower()
            if not cleaned:
                continue

            if cleaned in ("quit", "exit"):
                break

            if cleaned == "reset":
                sendFramedMessage(sock, {"type": "RESET"})
                continue

            if cleaned.isdigit():
                cellIdx = int(cleaned)
                sendFramedMessage(sock, {"type": "MOVE", "cell": cellIdx})
            else:
                print("Invalid input. Enter 0-8 to place a mark, 'reset', or 'quit'.")
    except KeyboardInterrupt:
        print("\n[CLIENT EXIT] Terminating client session.")
    finally:
        stopEvent.set()
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


if __name__ == "__main__":
    main()
