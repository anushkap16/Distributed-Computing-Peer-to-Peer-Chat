# sys is used to read command-line arguments (i.e. port number)
import sys
# Flask is the web framework used to create the user interface.
# render_template: loads HTML files, request: handles form data.
# session: remembers user data, jsonify: sends data back to the browser in JSON format.
# session is important for keeping track of the logged-in user across different pages and requests.
# JSON format is a common way to send structured data between the server and the client (browser)
from flask import Flask, render_template, request, redirect, session, jsonify
# PeerClient is the class that manages all P2P communication. Includes functions and data structures for communication in chat.
from peer_client import PeerClient

# Initialize the Flask application.
app = Flask(__name__)
# Secret key is required to use 'session' for keeping users logged in.
# Will be used when we set the username after login of peers.
app.secret_key = "p2p_fixed_key"

# Check if the user provided a port number in terminal when running this file.
# It's <2 because sys.argv is a list that stores the command-line arguments passed to a script when it is run and port is required to run file.
if len(sys.argv) < 2:
    print("Usage: python app.py <PORT>") # Guides the user how to run file correctly.
    sys.exit(1) # Exit program. (1) indicates an error occurred.

# Set the Web UI port and calculate a separate port for the P2P engine (1000 higher).
WEB_PORT = int(sys.argv[1]) # The Web UI port for the browser.
P2P_PORT = WEB_PORT + 1000 # The P2P port for background data. We add 1000 to avoid conflicts with the Web UI port.
peer_client = PeerClient(port=P2P_PORT)

# The Home Page: Displays the login screen in .html file.
# @app.route("/") means this function will be called when the user visits the root URL.
@app.route("/")
def login_page():
    return render_template("login.html") # Loads the login.html file from the templates folder and sends it to the browser.

# The Login Handler: Processes the login form submission.
# @app.route("/login", methods=["POST"]) means this function will be called when the username is entered.
# "POST" means that it takes submitted data (the username) from the form in the login page.
@app.route("/login", methods=["POST"])
def handle_login():
    username = request.form.get("username") # Where "POST" comes is utilized.
    if not username:
        return "Username is required", 400
    
    session["username"] = username # Session remembers data across pages. Username is stored across different pages.
    peer_client.username = username # Store the username in the PeerClient instance for use in P2P communication.
    
    return redirect("/chat") # Redirects user to the chat page.

# The Chat Page: Displays the main chat interface.
# @app.route("/chat") means this function will be called when the user visits the /chat URL.
@app.route("/chat")
def chat_page():
    if "username" not in session:
        return redirect("/") # If user tries chatting without entering username, they will be redirected to login page.
    
    peer_client.username = session["username"] # Ensure that PeerClient class has username.
    return render_template("chat.html", username=session["username"], p2p=P2P_PORT) # Loads the chat and gives important data.

# Connect to Peer: Handles the form submission for connecting to a new peer.
# @app.route("/connect", methods=["POST"]) means this function will be called when the user submits the connect form in the chat page.
@app.route("/connect", methods=["POST"])
def connect_to_peer():
    ip = request.form.get("ip") or "127.0.0.1"
    port = request.form.get("port")
    
    result = peer_client.connect(ip, port) # Calls connection function in PeerClient class.
    
    # Values will be returned from the connect function in PeerClient class.
    if result == "self": 
        return jsonify({"status": "error", "message": "That’s your port!"}), 400
    if result == "exists":
        return jsonify({"status": "error", "message": "Already connected to this peer"}), 409
    if result == "success":
        return jsonify({"status": "success"})
    
    return jsonify({"status": "error", "message": "Connection failed"}), 400

# Send Message: Handles the form submission for sending a new message.
# @app.route("/send", methods=["POST"]) means this function will be called when the user submits the send message form in the chat page.
@app.route("/send", methods=["POST"])
def send_msg():
    text = request.form.get("message") # Function comes from the form in the chat page. Gets the message text that the user wants to send.
    # Retrieve the signature of the message being replied to, if any
    reply_to = request.form.get("reply_to") # Replying to a specific message.
    
    if text and peer_client.username: # If there is text to send and the user has a username, then we can send the message.
        # Pass the reply_to signature to the P2P engine
        peer_client.send_message(peer_client.username, text, reply_to=reply_to) 
    return "", 204 # 204: No content sent

# React to Message: Handles the form submission for reacting to a message with an emoji.
# @app.route("/react", methods=["POST"]) means this function will be called when the user submits the react form in the chat page.
@app.route("/react", methods=["POST"])
def react():
    sig = request.form.get("sig") # sig means the signature of the message being reacted to. This is how we know which message the reaction belongs to.
    emoji = request.form.get("emoji") # The emoji reaction obtained from the form in the chat page.
    if sig and emoji and peer_client.username:
        peer_client.send_reaction(sig, emoji) # Calls the send_reaction function in PeerClient class.
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

# Get Messages: Provides the current list of messages and peer information to the UI.
# @app.route("/messages") means this function will be called when the browser requests the /messages URL, which happens periodically in the chat page to update the message list.
@app.route("/messages")
def get_messages():
    return jsonify({
        "messages": peer_client.messages,
        "peer_count": len(peer_client.peers),
        "active_peers": peer_client.connected_peer_details # New field for UI
    })

# Change Username: Handles the form submission for changing the username.
# @app.route("/change_username", methods=["POST"]) means this function will be called when the user submits the change username form in the chat page.
@app.route("/change_username", methods=["POST"])
def change_username():
    new_username = request.form.get("new_username")
    if not new_username:
        return jsonify({"status": "error", "message": "Username cannot be empty"}), 400
    
    old_username = peer_client.username # Store the old username before changing it, so we can broadcast the change to other peers.
    
    # Update local state
    session["username"] = new_username
    peer_client.username = new_username
    
    # Broadcast the change to the network
    peer_client.broadcast_name_change(old_username, new_username) # Inform other peers about the change.
    
    # Optional: Print it on the host's console too
    print(f"*** You (Peer {peer_client.port}) changed name from {old_username} to {new_username} ***")
    
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=WEB_PORT, debug=False)