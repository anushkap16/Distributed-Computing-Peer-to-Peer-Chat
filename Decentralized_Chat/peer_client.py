import socket
import threading
import json
import datetime

class PeerClient:
    # Constructor for the PeerClient class. Initializes the P2P engine and starts the server thread to listen for incoming connections.
    def __init__(self, port=6000): # The default port for P2P connections is 6000, but it can be overridden by passing a different port number when creating an instance of PeerClient.
        self.port = port # The port this peer listens on for P2P connections. This is separate from the Flask app port.
        self.username = "Unknown"
        self.messages = [] # List of all messages (chat and system) to be displayed in the UI, stored in order of arrival.
        self.peers = []  # List of socket objects
        self.connected_peer_details = [] # List of strings "IP:PORT" for the UI
        self.lamport_clock = 0
        self.lock = threading.Lock() # Lock to protect shared state across threads (messages, peers, lamport_clock, etc.) (Privacy, etc)
        self.running = True # Running means the server is active and should keep accepting connections and messages.
        self.seen_signatures = set() # To prevent processing the same message multiple times in case of duplicates.
        
        # Start the server thread to listen for incoming P2P connections.
        threading.Thread(target=self.start_server, daemon=True).start()

    # Sets up the server socket to listen for incoming connections from other peers. When a new connection is accepted, it starts a new thread to handle communication with that peer.
    def start_server(self):
        try:
            # AF_NET means we are using IPv4 addresses which are standard for local networks.
            # SOCK_STREAM means we are using TCP for reliable communication.
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # Create a TCP socket for listening to incoming connections.
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # This option allows us to reuse the same port immediately after restarting the app, without waiting for the OS to clear it.
            self.server_sock.bind(('', self.port)) # We can accept connections from any IP address that can reach this machine on that port.
            self.server_sock.listen(5) # Start listening for incoming connections. The argument '5' is the backlog, which is the maximum number of queued connections or waiting connections before the server starts refusing new ones.
            print(f"P2P Engine listening on port {self.port}") # Print a message on sidebar of UI to indicate that the P2P engine is up and running on the specified port.

            while self.running:
                conn, addr = self.server_sock.accept() # Wait for connections.
                
                # 1. Immediately send our P2P port to the new connection.
                # This allows the other side to know exactly which node just accepted them.
                try:
                    handshake = {"type": "handshake", "port": self.port}
                    conn.sendall((json.dumps(handshake) + "\n").encode())
                except Exception as e:
                    print(f"Handshake send failed: {e}")
                    conn.close()
                    continue

                # 2. Start the receive loop.
                # We no longer add to self.peers here. 
                # The receive_loop will handle the identification and deduplication before adding this connection to the active lists.
                peer_label = f"{addr[0]}:{addr[1]}"
                threading.Thread(target=self.receive_loop, args=(conn, peer_label), daemon=True).start()
                
        except Exception as e:
            print(f"Server Error: {e}")

    # Connect to peers given IP address and port when peer server submits a connection request
    # Return values will be used in app.py later
    def connect(self, ip, port):
        target = f"{ip}:{port}"
        # Prevent connecting to self
        if int(port) == self.port:
            return "self"

        with self.lock:
            if target in self.connected_peer_details:
                return "exists"

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0) 
            s.connect((ip, int(port)))
            s.settimeout(None) 
            
            # IMMEDIATELY tell the other peer who we are (our P2P port)
            # This allows the receiver to identify us and check for duplicates
            handshake = {"type": "handshake", "port": self.port}
            s.sendall((json.dumps(handshake) + "\n").encode())
            
            # We don't add to sidebar yet! 
            # We wait for the receive_loop to confirm the handshake.
            threading.Thread(target=self.receive_loop, args=(s, target), daemon=True).start()
            return "success"
        except Exception as e:
            return "failed"

    # Broadcast message(s) to connected peers.
    def broadcast(self, payload): # Payload is a dictionary containing the message data that we want to send to all connected peers. This could be a chat message, a system message, or a reaction.
        # In the form of a payload dictionary because we want to be able to send different types of messages (chat, system, reaction) with different fields, and using a dictionary allows us to be flexible with the message structure.
        raw_data = (json.dumps(payload) + "\n").encode()
        with self.lock:
            for i, peer in enumerate(self.peers[:]):
                try:
                    peer.sendall(raw_data)
                except:
                    # Cleanup disconnected peers
                    if peer in self.peers:
                        self.peers.remove(peer)
                        if i < len(self.connected_peer_details):
                            self.connected_peer_details.pop(i)

    # Send a chat message to all peers. This is called by the Flask app when the user submits a new message.
    def send_message(self, ignored_session_name, text, reply_to=None):
        with self.lock:
            self.lamport_clock += 1
            msg_payload = {
                "type": "chat",
                "sender": self.username,
                "message": text,
                "lamportTimestamp": self.lamport_clock,
                "time": datetime.datetime.now().isoformat(),
                "reply_to": reply_to,
                "reactions": {}
            }
        self.add_message(msg_payload)
        self.broadcast(msg_payload)

    # Broadcast a system message to all peers indicating that this peer has changed their username. 
    # Allows other peers to update their UI accordingly.
    def broadcast_name_change(self, old_name, new_name):
        # We wrap this as a 'system' type message so the UI can render it differently
        payload = {
            "type": "system",
            "message": f"Peer {self.port} changed name: {old_name} → {new_name}",
            "lamportTimestamp": self.lamport_clock,
            "time": datetime.datetime.now().isoformat()
        }
        self.add_message(payload)
        self.broadcast(payload)

    # Receive loop for handling incoming messages from a specific peer connection. This runs in a separate thread for each peer connection.
    def receive_loop(self, conn, addr_label):
        buffer = ""
        peer_port = None
        while self.running:
            try:
                data = conn.recv(4096)
                if not data: break
                buffer += data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    msg = json.loads(line)

                    # HANDLE HANDSHAKE
                    if msg.get("type") == "handshake":
                        peer_port = msg.get("port")
                        label = f"127.0.0.1:{peer_port}"
                        
                        with self.lock:
                            # If we already have a connection to this specific port, 
                            # close this new one to avoid duplicates.
                            if label in self.connected_peer_details:
                                conn.close()
                                return
                            
                            self.peers.append(conn)
                            self.connected_peer_details.append(label)
                        continue

                    # (Normal message handling continues here...)
                    if "lamportTimestamp" in msg:
                        with self.lock:
                            self.lamport_clock = max(self.lamport_clock, msg["lamportTimestamp"]) + 1
                    self.add_message(msg)
            except:
                break
        
        # Cleanup on disconnect
        with self.lock:
            if conn in self.peers:
                idx = self.peers.index(conn)
                self.peers.remove(conn)
                label = f"127.0.0.1:{peer_port}"
                if label in self.connected_peer_details:
                    self.connected_peer_details.remove(label)
        conn.close()

    # Add a new message to the local message list and update the UI. This is called both for incoming messages from peers and for messages we send ourselves.
    def add_message(self, message):
        if message.get("type") == "reaction":
            self.handle_reaction(message)
            return

        # We generate a unique signature for each message based on its content and sender. 
        with self.lock:
            # Generate sig for chat messages only
            if message.get("type") == "chat":
                msg_sig = f"{message['sender']}-{message['lamportTimestamp']}-{message['message']}"
                message['sig'] = msg_sig
            else:
                # Use time/msg for system message uniqueness
                msg_sig = f"system-{message.get('time')}"
                message['sig'] = msg_sig
            
            if msg_sig not in self.seen_signatures:
                self.messages.append(message)
                self.seen_signatures.add(msg_sig)
                self.messages.sort(key=lambda m: (m.get("lamportTimestamp", 0), m.get("time", "")))

    # Handle incoming reactions by updating the corresponding message's reactions dictionary. This allows the UI to display the reaction counts and who reacted.
    def handle_reaction(self, reaction_data):
        with self.lock:
            for m in self.messages:
                if m.get('sig') == reaction_data["target_sig"]:
                    m.setdefault("reactions", {})[reaction_data["sender"]] = reaction_data["emoji"]
                    break
    
    # Send a reaction to a specific message. This is called by the Flask app when the user submits a reaction in the UI.
    def send_reaction(self, message_sig, emoji):
        """
        Broadcasts a reaction to a specific message signature.
        """
        reaction_payload = {
            "type": "reaction",
            "target_sig": message_sig,
            "sender": self.username,
            "emoji": emoji
        }
        # Update our local message list so we see it immediately
        self.handle_reaction(reaction_payload)
        # Tell everyone else
        self.broadcast(reaction_payload)