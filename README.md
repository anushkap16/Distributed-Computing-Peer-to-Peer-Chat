# Decentralized Peer-to-Peer Chat Application

A serverless, peer-to-peer chat application. Every running instance is both a server (listening for connections) and a client (initiating connections), so there is no central server that can fail, be overloaded, or store your messages. Messages are ordered consistently across all peers using **Lamport logical clocks**.

Built in Python with TCP sockets, threading, and Flask, with an HTML/JavaScript (Tailwind CSS) front end.

---

## Features

- **Direct P2P networking**: peers connect to each other over TCP sockets; no central server.
- **Broadcast messaging**: a message sent by one peer is delivered to every connected peer.
- **Consistent ordering**: Lamport clocks are incremented on send and merged on receive (`max(local, received) + 1`), and messages are sorted by Lamport timestamp (with wall-clock time as a tiebreaker).
- **Message info**: each message shows the sender, text, and time.
- **Deduplication**: each chat message gets a signature (`sender-lamportTimestamp-message`), so a message is only displayed once. Duplicate connections between the same two peers are also rejected.
- **Replies**: reply to a specific message; the original is previewed above the reply.
- **Emoji reactions**: pick from ❤️ 👍 😭 😂 or add any emoji with ➕. Hover a reaction to see who reacted.
- **Change username at any time**: all peers see a system notice about the change.
- **Live updates**: the chat refreshes automatically (the browser polls the backend every second).
- **Thread-safe**: a `threading.Lock` protects the shared message list, peer list, and Lamport clock.

---

## Requirements

- Python 3.x (developed and tested with Python 3.12)
- Flask
- A modern web browser
- An internet connection **for styling only**: `login.html` and `chat.html` load Tailwind CSS from `https://cdn.tailwindcss.com`. Messaging itself works on a LAN without internet, but the pages will be unstyled if the CDN is unreachable.

Install Flask:

```bash
pip install flask
```

---

## Project Structure

```
Decentralized_Chat/
├── app.py            # Flask web server (controller): HTTP routes, session handling
├── peer_client.py    # PeerClient class (model): TCP networking, Lamport clock, dedup, reactions
├── templates/
│   ├── login.html    # Username entry page
│   ├── chat.html     # Main chat interface
│   └── peers.html    # Simple peer-list template (not used by the current routes)
└── static/
    └── style.css     # Basic stylesheet (used by peers.html)
```

---

## Running the App

Each peer is one instance of `app.py`, started with a **web port**. The P2P (TCP) port is automatically set to **web port + 1000**.

| You run              | Web UI (browser)        | P2P port (for others to connect to) |
| -------------------- | ----------------------- | ----------------------------------- |
| `python app.py 5000` | http://localhost:5000   | 6000                                |
| `python app.py 5001` | http://localhost:5001   | 6001                                |
| `python app.py 5002` | http://localhost:5002   | 6002                                |

### Quick start: three peers on one computer

Open three terminals in the project folder:

```bash
# Terminal 1
python app.py 5000

# Terminal 2
python app.py 5001

# Terminal 3
python app.py 5002
```

Then:

1. Open `http://localhost:5000`, `http://localhost:5001`, and `http://localhost:5002` in separate browser windows. Using separate windows (or a private/incognito window for each) keeps their login sessions apart.
2. On each page, enter a username and click **Start Chatting**.
3. On the first peer, enter IP `127.0.0.1` and port `6001` (the other peer's **P2P port**, not its web port), then click **Connect**.
4. Connect the remaining peers the same way (for example, peer 3 connects to `6000` and `6001`).
5. Start chatting.

> **Important:** when connecting, always enter the other peer's **P2P port** (web port + 1000). Your own P2P port is shown in the top-left of the chat sidebar as "Your Port".

### Connecting across different computers on the same LAN

Run `app.py` on each machine, then enter the other machine's local IP address (for example `192.168.1.25`) and its P2P port in the Connect form. The IP field defaults to `127.0.0.1` if left blank. Make sure your firewall allows incoming TCP connections on the P2P port.

See [Known Limitations](#known-limitations) for caveats about LAN use.

---

## Using the Chat

| Action             | How                                                                              |
| ------------------ | -------------------------------------------------------------------------------- |
| Connect to a peer  | Enter IP and P2P port in the sidebar, click **Connect**                          |
| Send a message     | Type in the message box, press **Send**                                          |
| Reply to a message | Hover a message and click **Reply**; click ✕ above the input to cancel          |
| React to a message | Hover a message and click an emoji, or ➕ to enter any emoji                      |
| See who reacted    | Hover over a reaction                                                            |
| Change username    | Type a new name in **Settings** and click **Update Username**                    |

Connection errors you may see: connecting to your own port, connecting to a peer you are already connected to, or a failed connection (unreachable peer or wrong port).

---

## How It Works

The app uses a four-layer hybrid P2P architecture:

```
Browser (HTML/JS)  ──HTTP──▶  Flask (app.py)  ──method calls──▶  PeerClient (peer_client.py)  ──TCP/JSON──▶  Other peers
```

1. **Startup**: `app.py` reads the web port, calculates the P2P port (+1000), and creates a `PeerClient`, which immediately starts a background thread listening for incoming TCP connections.
2. **Connecting**: `PeerClient.connect(ip, port)` opens a TCP socket and sends a `handshake` message containing its P2P port. The receiving peer replies with its own handshake, and duplicate connections are closed.
3. **Sending**: Flask's `/send` route calls `PeerClient.send_message()`, which increments the Lamport clock, builds a JSON payload, stores it locally, and broadcasts it to every connected socket.
4. **Receiving**: each connection has its own `receive_loop` thread. Messages are newline-delimited JSON. On receipt, the Lamport clock is updated, the message signature is checked against `seen_signatures`, and the message is added to the sorted list.
5. **Display**: the browser polls `/messages` every second and re-renders the chat.

### Message format

```json
{
  "type": "chat",
  "sender": "Alice",
  "message": "Hello!",
  "lamportTimestamp": 3,
  "time": "2026-03-08T10:54:00.000000",
  "reply_to": null,
  "reactions": {}
}
```

Other message types: `handshake` (peer identification), `reaction` (emoji on a message signature), and `system` (e.g. username-change notices).

### Flask routes

| Route              | Method | Purpose                                  |
| ------------------ | ------ | ---------------------------------------- |
| `/`                | GET    | Login page                               |
| `/login`           | POST   | Store username in session and PeerClient |
| `/chat`            | GET    | Main chat page                           |
| `/connect`         | POST   | Connect to another peer                  |
| `/send`            | POST   | Send a chat message (optional reply)     |
| `/react`           | POST   | Send an emoji reaction                   |
| `/messages`        | GET    | Current messages and connected peers     |
| `/change_username` | POST   | Change username and notify peers         |

---

## Troubleshooting

- **`Usage: python app.py <PORT>`**: you must pass a web port as the first argument.
- **"Address already in use"**: another process is using that port. Pick a different web port (remember the P2P port is web port + 1000).
- **"Connection failed"**: check that the other peer is running, that you used its *P2P* port (not its web port), and that the IP is correct and reachable.
- **Page has no styling**: the Tailwind CDN could not be loaded. Check your internet connection.
- **Two peers share a login**: use a separate browser window, profile, or private window for each peer, since peers on `localhost` share cookies across ports.

---

## Known Limitations

- **Local network only.** There is no NAT traversal, so peers on different networks cannot connect. There is also no encryption or authentication, so only use it on networks you trust.
- **Manual peer discovery.** Users must type the IP and port of the peer they want to connect to.
- **Loopback peer labels.** After a handshake, a peer is listed in the sidebar and tracked for duplicates as `127.0.0.1:<port>`, regardless of its real IP. Cross-machine connections can work, but the sidebar may show `127.0.0.1` and peers on different machines that happen to use the same P2P port number may be treated as duplicates.
- **No persistence.** Messages are held in memory only and are lost when a peer closes. A newly connected peer does not receive earlier history.

---

## Ideas for Future Improvements

- Automatic peer discovery on the LAN
- NAT traversal, encryption, and identity verification for internet-wide use
- Saved chat history and syncing history to new peers
- Image/file sharing and voice messages
- Typing indicators, read receipts, and group chats

---

## Tech Stack

| Component     | Technology                  |
| ------------- | --------------------------- |
| Backend       | Python 3                    |
| Web framework | Flask                       |
| Frontend      | HTML5, JavaScript, Tailwind CSS |
| Networking    | TCP sockets (`socket`)      |
| Concurrency   | `threading`                 |
| Data format   | JSON                        |
