import argparse
import json
import socket
import struct
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
GRACE_PERIOD_SECONDS = 60.0
HEADER_STRUCT = struct.Struct("!I")
MAX_PAYLOAD_BYTES = 65536

WIN_LINES: List[Tuple[int, int, int]] = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
]


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


def evaluateBoard(board: List[str]) -> Tuple[Optional[str], bool]:
    for idxA, idxB, idxC in WIN_LINES:
        markA = board[idxA]
        if markA != "" and markA == board[idxB] and markA == board[idxC]:
            return markA, False
    if "" not in board:
        return None, True
    return None, False


class PlayerSession:
    def __init__(self, alias: str, symbol: str, conn: Optional[socket.socket]) -> None:
        self.alias = alias
        self.symbol = symbol
        self.conn = conn
        self.status = "CONNECTED" if conn is not None else "TEMPORARILY_DISCONNECTED"
        self.disconnectedAt: Optional[float] = None
        self.sendLock = threading.Lock()


class GameRoom:
    def __init__(self, roomId: str) -> None:
        self.roomId = roomId
        self.stateLock = threading.Lock()
        self.playersByAlias: Dict[str, PlayerSession] = {}
        self.playersBySymbol: Dict[str, PlayerSession] = {}
        self.board: List[str] = [""] * 9
        self.scores: Dict[str, int] = {"X": 0, "O": 0, "TIES": 0}
        self.activeTurn: str = "X"
        self.gamePhase: str = "WAITING_FOR_PLAYERS"
        self.graceDeadline: Optional[float] = None
        self.graceTimer: Optional[threading.Timer] = None

    def buildStateSnapshot(self, eventType: str, message: str) -> Dict[str, Any]:
        statuses = {}
        for symbol, session in self.playersBySymbol.items():
            statuses[symbol] = {
                "alias": session.alias,
                "status": session.status,
            }
        return {
            "type": eventType,
            "roomId": self.roomId,
            "board": list(self.board),
            "scores": dict(self.scores),
            "activeTurn": self.activeTurn,
            "gamePhase": self.gamePhase,
            "players": statuses,
            "message": message,
        }

    def sendToSessionLocked(self, session: PlayerSession, payload: Dict[str, Any]) -> None:
        if session.conn is None or session.status != "CONNECTED":
            return
        try:
            with session.sendLock:
                sendFramedMessage(session.conn, payload)
        except OSError:
            session.status = "TEMPORARILY_DISCONNECTED"
            session.disconnectedAt = time.monotonic()
            session.conn = None

    def broadcastLocked(self, payload: Dict[str, Any]) -> None:
        for session in self.playersBySymbol.values():
            self.sendToSessionLocked(session, payload)

    def cancelGraceTimerLocked(self) -> None:
        if self.graceTimer is not None:
            self.graceTimer.cancel()
            self.graceTimer = None
        self.graceDeadline = None

    def startGraceTimerLocked(self, disconnectedSymbol: str) -> None:
        self.cancelGraceTimerLocked()
        self.graceDeadline = time.monotonic() + GRACE_PERIOD_SECONDS
        timer = threading.Timer(
            GRACE_PERIOD_SECONDS,
            self._handleGraceExpiry,
            args=(disconnectedSymbol,),
        )
        timer.daemon = True
        self.graceTimer = timer
        timer.start()

    def _handleGraceExpiry(self, disconnectedSymbol: str) -> None:
        with self.stateLock:
            session = self.playersBySymbol.get(disconnectedSymbol)
            if session is None or session.status != "TEMPORARILY_DISCONNECTED":
                return
            self.gamePhase = "FORFEITED"
            opponentSymbol = "O" if disconnectedSymbol == "X" else "X"
            if opponentSymbol in self.scores:
                self.scores[opponentSymbol] += 1
            snapshot = self.buildStateSnapshot(
                "GAME_OVER",
                f"Player {disconnectedSymbol} ({session.alias}) did not reconnect within {int(GRACE_PERIOD_SECONDS)}s.",
            )
            self.broadcastLocked(snapshot)
            print(f"[GRACE EXPIRED] Room {self.roomId}: Player {disconnectedSymbol} timed out.")

    def registerOrReconnect(self, alias: str, conn: socket.socket) -> Tuple[bool, str, Optional[PlayerSession]]:
        with self.stateLock:
            existing = self.playersByAlias.get(alias)
            if existing is not None:
                if existing.status == "CONNECTED" and existing.conn is not None:
                    return False, f"Alias '{alias}' is already actively connected.", None
                existing.conn = conn
                existing.status = "CONNECTED"
                existing.disconnectedAt = None
                self.cancelGraceTimerLocked()
                if self.gamePhase == "PAUSED_DISCONNECT":
                    self.gamePhase = "IN_PROGRESS"
                resumePayload = self.buildStateSnapshot(
                    "STATE_RESUME",
                    f"Player {existing.symbol} ({alias}) reconnected. Resuming match.",
                )
                resumePayload["yourSymbol"] = existing.symbol
                self.broadcastLocked(resumePayload)
                print(
                    f"[RECONNECT] Alias '{alias}' re-bound as Player {existing.symbol}; "
                    f"sent STATE_RESUME (turn={self.activeTurn}, scores={self.scores})."
                )
                return True, f"Reconnected as Player {existing.symbol}.", existing

            if len(self.playersBySymbol) >= 2:
                return False, "Game room is full.", None

            symbol = "X" if "X" not in self.playersBySymbol else "O"
            newSession = PlayerSession(alias=alias, symbol=symbol, conn=conn)
            self.playersByAlias[alias] = newSession
            self.playersBySymbol[symbol] = newSession

            if len(self.playersBySymbol) == 2:
                self.gamePhase = "IN_PROGRESS"
                startPayload = self.buildStateSnapshot(
                    "GAME_START",
                    "Both players connected. Player X moves first.",
                )
                for sym, sess in self.playersBySymbol.items():
                    personalPayload = dict(startPayload)
                    personalPayload["yourSymbol"] = sym
                    self.sendToSessionLocked(sess, personalPayload)
                print(f"[GAME START] Room {self.roomId}: X and O ready.")
            else:
                self.gamePhase = "WAITING_FOR_PLAYERS"
                waitPayload = self.buildStateSnapshot(
                    "WAITING",
                    f"Joined as Player {symbol} ({alias}). Waiting for opponent...",
                )
                waitPayload["yourSymbol"] = symbol
                self.sendToSessionLocked(newSession, waitPayload)
                print(f"[JOIN] Alias '{alias}' assigned Player {symbol}.")

            return True, f"Joined as Player {symbol}.", newSession

    def handleDisconnect(self, session: PlayerSession, reason: str) -> None:
        with self.stateLock:
            if session.conn is not None:
                try:
                    session.conn.close()
                except OSError:
                    pass
                session.conn = None

            if session.status == "TEMPORARILY_DISCONNECTED":
                return

            session.status = "TEMPORARILY_DISCONNECTED"
            session.disconnectedAt = time.monotonic()

            if self.gamePhase in ("IN_PROGRESS", "PAUSED_DISCONNECT"):
                self.gamePhase = "PAUSED_DISCONNECT"
                self.startGraceTimerLocked(session.symbol)
                print(
                    f"[DISCONNECT PRESERVED] {reason} -> Player {session.symbol} ({session.alias}) "
                    f"marked TEMPORARILY_DISCONNECTED. Holding board={self.board}, "
                    f"turn={self.activeTurn}, scores={self.scores} for {int(GRACE_PERIOD_SECONDS)}s."
                )
                notifyPayload = self.buildStateSnapshot(
                    "STATE_UPDATE",
                    f"Player {session.symbol} ({session.alias}) disconnected ({reason}). "
                    f"State preserved for {int(GRACE_PERIOD_SECONDS)}s grace period.",
                )
                self.broadcastLocked(notifyPayload)
            else:
                print(f"[DISCONNECT] Player {session.symbol} ({session.alias}) disconnected ({reason}).")

    def applyMove(self, session: PlayerSession, cellIndex: int) -> None:
        with self.stateLock:
            if self.gamePhase != "IN_PROGRESS":
                errPayload = {
                    "type": "ERROR",
                    "message": f"Cannot play move while game phase is {self.gamePhase}.",
                }
                self.sendToSessionLocked(session, errPayload)
                return

            if session.symbol != self.activeTurn:
                errPayload = {
                    "type": "ERROR",
                    "message": f"Not your turn. Active turn is Player {self.activeTurn}.",
                }
                self.sendToSessionLocked(session, errPayload)
                return

            if not isinstance(cellIndex, int) or cellIndex < 0 or cellIndex > 8:
                errPayload = {
                    "type": "ERROR",
                    "message": "Cell index must be an integer between 0 and 8.",
                }
                self.sendToSessionLocked(session, errPayload)
                return

            if self.board[cellIndex] != "":
                errPayload = {
                    "type": "ERROR",
                    "message": f"Cell {cellIndex} is already occupied.",
                }
                self.sendToSessionLocked(session, errPayload)
                return

            self.board[cellIndex] = session.symbol
            winner, isTie = evaluateBoard(self.board)

            if winner is not None:
                self.scores[winner] += 1
                self.gamePhase = "ROUND_OVER"
                endPayload = self.buildStateSnapshot(
                    "GAME_OVER",
                    f"Player {winner} wins the round!",
                )
                self.broadcastLocked(endPayload)
                return

            if isTie:
                self.scores["TIES"] += 1
                self.gamePhase = "ROUND_OVER"
                tiePayload = self.buildStateSnapshot(
                    "GAME_OVER",
                    "Round ended in a tie.",
                )
                self.broadcastLocked(tiePayload)
                return

            self.activeTurn = "O" if self.activeTurn == "X" else "X"
            updatePayload = self.buildStateSnapshot(
                "STATE_UPDATE",
                f"Player {session.symbol} played cell {cellIndex}. Turn: Player {self.activeTurn}.",
            )
            self.broadcastLocked(updatePayload)

    def handleReset(self, session: PlayerSession) -> None:
        with self.stateLock:
            self.board = [""] * 9
            self.activeTurn = "X"
            self.cancelGraceTimerLocked()
            if len(self.playersBySymbol) == 2:
                self.gamePhase = "IN_PROGRESS"
            else:
                self.gamePhase = "WAITING_FOR_PLAYERS"
            resetPayload = self.buildStateSnapshot(
                "STATE_UPDATE",
                f"Board reset by {session.alias}. Turn: Player X.",
            )
            self.broadcastLocked(resetPayload)


def serveClient(conn: socket.socket, addr: Tuple[str, int], room: GameRoom) -> None:
    session: Optional[PlayerSession] = None
    try:
        helloMsg = recvFramedMessage(conn)
        if helloMsg is None:
            conn.close()
            return

        msgType = helloMsg.get("type")
        alias = str(helloMsg.get("alias", "")).strip()
        if msgType not in ("CONNECT", "RECONNECT") or not alias:
            sendFramedMessage(conn, {"type": "ERROR", "message": "First message must include a valid alias."})
            conn.close()
            return

        ok, statusMsg, boundSession = room.registerOrReconnect(alias, conn)
        if not ok or boundSession is None:
            sendFramedMessage(conn, {"type": "ERROR", "message": statusMsg})
            conn.close()
            return

        session = boundSession
        print(f"[CLIENT BOUND] {alias} ({session.symbol}) from {addr[0]}:{addr[1]}")

        while True:
            msg = recvFramedMessage(conn)
            if msg is None:
                room.handleDisconnect(session, "EOF / client closed socket")
                break

            command = msg.get("type")
            if command == "MOVE":
                cell = msg.get("cell")
                room.applyMove(session, cell)
            elif command == "RESET":
                room.handleReset(session)
            else:
                room.sendToSessionLocked(
                    session,
                    {"type": "ERROR", "message": f"Unknown message type: {command}"},
                )

    except ConnectionResetError as exc:
        if session is not None:
            room.handleDisconnect(session, f"ConnectionResetError: {exc}")
    except BrokenPipeError as exc:
        if session is not None:
            room.handleDisconnect(session, f"BrokenPipeError: {exc}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if session is not None:
            room.handleDisconnect(session, f"Socket/Protocol error: {exc}")
        else:
            try:
                conn.close()
            except OSError:
                pass


def parseArguments(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CS-457 Stateful Tic-Tac-Toe TCP Server"
    )
    parser.add_argument(
        "-i",
        "--ip",
        dest="host",
        default=DEFAULT_HOST,
        help=f"Bind IP address (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Bind TCP port (default: {DEFAULT_PORT})",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parseArguments(sys.argv[1:])
    room = GameRoom(roomId="LUKA-ROOM-1")

    serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serverSock.bind((args.host, args.port))
    serverSock.listen(16)
    print(f"[SERVER LISTENING] {args.host}:{args.port} (grace={int(GRACE_PERIOD_SECONDS)}s)")

    try:
        while True:
            conn, addr = serverSock.accept()
            worker = threading.Thread(
                target=serveClient,
                args=(conn, addr, room),
                daemon=True,
            )
            worker.start()
    except KeyboardInterrupt:
        print("\n[SERVER SHUTDOWN] Stopping listener.")
    finally:
        serverSock.close()


if __name__ == "__main__":
    main()
