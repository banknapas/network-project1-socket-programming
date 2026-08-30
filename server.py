"""
WTRP Server (WebToon Retrieval Protocol) v1.0
==============================================
Application-layer protocol server running on top of TCP.

Text-based request/response format (similar in spirit to HTTP but custom):

Request:
    METHOD /path WTRP/1.0
    Header: value

    [body]

Response:
    WTRP/1.0 <code> <phrase>
    Header: value

    [body]

Supported methods (kept minimal to match the simplified client menu):
    LIST_SERIES              -> list every series with its episode count
    GET_EPISODE               -> metadata of one episode (total pages)
    GET_PAGE                  -> content of a single page of an episode

Run:
    python3 server.py [port]
"""

import socket
import sys
import threading

HOST = "0.0.0.0"
DEFAULT_PORT = 5050

STATUS_PHRASES = {
    200: "OK",
    206: "Partial Content",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}

# ---------------------------------------------------------------------------
# In-memory "database" of webtoons
# ---------------------------------------------------------------------------
DB = {
    1: {
        "title": "Moon Hunter",
        "author": "J. Kim",
        "genre": "Fantasy",
        "episodes": {
            1: {
                "title": "The Awakening",
                "pages": [
                    "หน้า 1: พระเอกตื่นขึ้นกลางป่าลึก",
                    "หน้า 2: พบรอยเท้าประหลาดบนพื้นดิน",
                    "หน้า 3: เสียงหอนดังมาจากที่ไกล",
                    "หน้า 4: เขาควักดาบโบราณออกมา",
                    "หน้า 5: จบตอนที่ 1 ด้วยแสงจันทร์สีเลือด",
                ],
            },
            2: {
                "title": "The Chase",
                "pages": [
                    "หน้า 1: การไล่ล่าเริ่มต้นกลางคืน",
                    "หน้า 2: เขาสะดุดรากไม้ล้มลง",
                    "หน้า 3: มีใครบางคนยื่นมือช่วย",
                ],
            },
        },
    },
    2: {
        "title": "Cafe of Small Miracles",
        "author": "S. Park",
        "genre": "Slice of Life",
        "episodes": {
            1: {
                "title": "New Employee",
                "pages": [
                    "หน้า 1: เธอเดินเข้าร้านกาแฟเป็นวันแรก",
                    "หน้า 2: เจ้าของร้านยิ้มให้อย่างอบอุ่น",
                ],
            }
        },
    },
}


def make_response(code: int, headers: dict | None = None, body: str = "") -> str:
    phrase = STATUS_PHRASES.get(code, "Unknown")
    headers = headers or {}
    lines = [f"WTRP/1.0 {code} {phrase}"]
    if body:
        headers["Content-Length"] = str(len(body.encode("utf-8")))
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append("")  # blank line separates headers/body
    lines.append(body)
    return "\r\n".join(lines) + "\r\n"


def parse_request(raw: str):
    lines = raw.split("\r\n")
    if not lines or not lines[0].strip():
        return None, None, {}, ""
    request_line = lines[0].strip()
    parts = request_line.split(" ")
    if len(parts) != 3:
        return None, None, {}, ""
    method, path, version = parts
    headers = {}
    body_lines = []
    in_body = False
    for line in lines[1:]:
        if not in_body and line == "":
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
        else:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip()] = v.strip()
    body = "\r\n".join(body_lines).strip()
    return method, path, headers, body


def handle_request(method: str, path: str, headers: dict, body: str) -> str:
    try:
        if method == "LIST_SERIES":
            # id|title|author|genre|episode_count
            def ep_label(n):
                return f"{n} episode" if n == 1 else f"{n} episodes"

            lines = [
                f"{sid}|{info['title']}|{info['author']}|{info['genre']}|{ep_label(len(info['episodes']))}"
                for sid, info in DB.items()
            ]
            return make_response(200, body="\n".join(lines))

        if method == "GET_EPISODE":
            # /series/{id}/ep/{no}
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[2] != "ep":
                return make_response(400, body="Malformed path")
            sid, eno = int(parts[1]), int(parts[3])
            if sid not in DB or eno not in DB[sid]["episodes"]:
                return make_response(404, body="Episode not found")
            ep = DB[sid]["episodes"][eno]
            headers_out = {"Series-Id": sid, "Episode": eno,
                           "Total-Pages": len(ep["pages"])}
            return make_response(200, headers_out, ep["title"])

        if method == "GET_PAGE":
            # /series/{id}/ep/{no}/page/{p}
            parts = path.strip("/").split("/")
            if len(parts) != 6 or parts[2] != "ep" or parts[4] != "page":
                return make_response(400, body="Malformed path")
            sid, eno, pno = int(parts[1]), int(parts[3]), int(parts[5])
            if sid not in DB or eno not in DB[sid]["episodes"]:
                return make_response(404, body="Episode not found")
            pages = DB[sid]["episodes"][eno]["pages"]
            if pno < 1 or pno > len(pages):
                return make_response(404, body="Page not found")
            headers_out = {"Series-Id": sid, "Episode": eno,
                           "Page": pno, "Total-Pages": len(pages)}
            return make_response(206, headers_out, pages[pno - 1])

        return make_response(405, body=f"Unknown method: {method}")

    except Exception as e:
        return make_response(500, body=f"Server error: {e}")


def client_thread(conn: socket.socket, addr):
    client_id = f"{addr[0]}:{addr[1]}"
    print(f"[+] Client connected: {client_id}")
    with conn:
        while True:
            try:
                data = conn.recv(4096)
            except ConnectionResetError:
                break
            if not data:
                break
            buf = data.decode("utf-8", errors="replace")
            method, path, headers, body = parse_request(buf)
            if method is None:
                continue

            print(f"\n--- Received from {client_id} ---")
            print(f"{method} {path} WTRP/1.0")
            for k, v in headers.items():
                print(f"{k}: {v}")
            if body:
                print(f"(body) {body}")

            response = handle_request(method, path, headers, body)
            conn.sendall(response.encode("utf-8"))

            status_line = response.split("\r\n", 1)[0]
            print(f"--- Sent to {client_id} ---")
            print(status_line)
    print(f"[-] Client disconnected: {client_id}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, port))
    server_sock.listen(5)
    print(f"WTRP Server listening on {HOST}:{port} (TCP)")

    try:
        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=client_thread, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
