"""
WTRP Client (WebToon Retrieval Protocol) v1.0
==============================================
Interactive text client that talks to server.py over TCP using the
custom WTRP application-layer protocol.

Menu is intentionally minimal:
    1) List all series (shows how many episodes each series has)
    2) Read an episode (loads every page in order, top -> bottom)
    9) Quit

Run:
    python3 client.py [host] [port]
"""

import socket
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5050


def build_request(method: str, path: str, headers: dict | None = None, body: str = "") -> str:
    headers = headers or {}
    lines = [f"{method} {path} WTRP/1.0"]
    if body:
        headers["Content-Length"] = str(len(body.encode("utf-8")))
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append(body)
    return "\r\n".join(lines) + "\r\n"


def parse_response(raw: str):
    lines = raw.split("\r\n")
    status_line = lines[0]
    parts = status_line.split(" ", 2)
    version = parts[0]
    code = int(parts[1])
    phrase = parts[2] if len(parts) > 2 else ""
    headers = {}
    body_lines = []
    in_body = False
    for line in lines[1:]:
        if not in_body and line == "":
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
        elif ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    body = "\r\n".join(body_lines).strip()
    return code, phrase, headers, body


def send_request(sock: socket.socket, method: str, path: str,
                  headers: dict | None = None, body: str = ""):
    request = build_request(method, path, headers, body)

    print("\n=== Sending Request ===")
    print(request.strip("\r\n"))

    sock.sendall(request.encode("utf-8"))
    data = sock.recv(8192).decode("utf-8", errors="replace")

    code, phrase, resp_headers, resp_body = parse_response(data)

    print("=== Received Response ===")
    print(f"Status: {code} {phrase}")
    for k, v in resp_headers.items():
        print(f"{k}: {v}")
    if resp_body:
        print(f"Body:\n{resp_body}")
    print("=========================")

    return code, phrase, resp_headers, resp_body


def list_all_series(sock: socket.socket):
    """1) List all series, showing how many episodes each one has."""
    send_request(sock, "LIST_SERIES", "/series")


def read_episode(sock: socket.socket):
    """
    2) Read an episode: load every page in order, top -> bottom.

    Step 1: GET_EPISODE to find out the total number of pages.
    Step 2: loop page 1, 2, 3, ... last page, sending one GET_PAGE
            request per page and printing each page's content as it
            arrives, so the whole episode is displayed top to bottom
            just like scrolling down a webtoon.
    """
    sid = input("Series id: ").strip()
    eno = input("Episode no: ").strip()

    code, phrase, headers, body = send_request(
        sock, "GET_EPISODE", f"/series/{sid}/ep/{eno}"
    )
    if code != 200:
        print(f"[!] Cannot load episode (server returned {code} {phrase}). Aborting.")
        return

    total_pages = int(headers.get("Total-Pages", 0))
    if total_pages <= 0:
        print("[!] Episode has no pages.")
        return

    print(f"\n>>> Reading episode top to bottom ({total_pages} page(s)) <<<")

    for page_no in range(1, total_pages + 1):
        print(f"\n----- Page {page_no}/{total_pages} -----")
        code, phrase, headers, body = send_request(
            sock, "GET_PAGE", f"/series/{sid}/ep/{eno}/page/{page_no}"
        )
        if code != 206 and code != 200:
            print(f"[!] Failed to load page {page_no}: {code} {phrase}. Stopping.")
            break

    print(f"\n>>> Reached the end of episode {eno} <<<")


MENU = """
WebToon Reader (WTRP Client)
-----------------------------
1) List all series
2) Read an episode
9) Quit
Choose an option: """


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP
    sock.connect((host, port))
    print(f"Connected to WTRP server at {host}:{port} (TCP)")

    try:
        while True:
            choice = input(MENU).strip()

            if choice == "1":
                list_all_series(sock)

            elif choice == "2":
                read_episode(sock)

            elif choice == "9":
                print("Bye!")
                break

            else:
                print("Invalid option, try again.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
