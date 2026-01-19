# Server: python chatroom.py server
# Client: python chatroom.py

import socket, threading, random, sys, os, json, shutil, subprocess, time
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

# ── Config ──────────────
HOST = '0.0.0.0'
PORT = 55555
USERS_FILE = "users.json"

# ── Data ────────────────
users = {}       # username -> {"first_seen": iso, "last_active": iso}
active = {}      # username -> {"client": socket, "ip": str}
rooms = {}       # code -> {"name": str, "public": bool, "admin": str, "users": set, "banned": set}

# ── Helpers ─────────────
def load_users():
    global users
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE,'r') as f:
            users = json.load(f)
    else:
        users = {}

def save_users():
    with open(USERS_FILE,'w') as f:
        json.dump(users,f)

def gen_code():
    return ''.join(random.choices("0123456789", k=10))

def broadcast(code, msg, exclude=None):
    if code not in rooms: return
    for u in rooms[code]["users"]:
        if u != exclude and u in active:
            try: active[u]["client"].send(f"MSG:{msg}\n".encode())
            except: pass

# ── Server ─────────────
def handle_client(client, addr):
    ip = addr[0]
    name = None
    try:
        client.send("MSG:Welcome! Enter username (3-20 chars, no spaces):\n".encode())
        while not name:
            data = client.recv(1024).decode(errors='ignore').strip()
            if not data: return
            if len(data)<3 or len(data)>20 or ' ' in data:
                client.send(b"MSG:Invalid username\n")
                continue
            if data in active:
                client.send(b"MSG:Username already in use\n")
                continue
            name = data
            active[name] = {"client": client, "ip": ip}
            if name not in users:
                users[name] = {"first_seen": datetime.utcnow().isoformat(), "last_active": datetime.utcnow().isoformat()}
            users[name]["last_active"] = datetime.utcnow().isoformat()
            save_users()

        # Ensure global chat exists
        if "0000000000" not in rooms:
            rooms["0000000000"] = {"name":"Global Chat","public":True,"admin":None,"users":set(),"banned":set()}
        rooms["0000000000"]["users"].add(name)
        current_room = "0000000000"

        # Main menu
        menu = "\nMAIN MENU\n1) Create Chat\n2) Join Chat\n3) Public Chats\nChoose [1-3]:\n"
        client.send(f"MSG:{menu}".encode())
        choice = client.recv(1024).decode(errors='ignore').strip()

        if choice=="1":  # Create chat
            client.send(b"Admin? Y/N: ")
            admin_input = client.recv(1024).decode(errors='ignore').strip().lower()
            admin = name if admin_input=="y" else None
            client.send(b"Public? Y/N: ")
            public_input = client.recv(1024).decode(errors='ignore').strip().lower()
            public = True if public_input=="y" else False
            code = gen_code()
            rooms[code] = {"name": f"{name}'s Room","public":public,"admin":admin,"users":{name},"banned":set()}
            current_room = code
            client.send(f"MSG:{Fore.BLUE}Room Code: {code} (keep it to join later){Style.RESET_ALL}\n".encode())

        elif choice=="2":  # Join chat
            client.send(b"Enter room code: ")
            code = client.recv(1024).decode(errors='ignore').strip()
            if code in rooms:
                if name in rooms[code]["banned"]:
                    client.send(b"MSG:You are banned from this room\n")
                    return
                rooms[code]["users"].add(name)
                current_room = code
                broadcast(code, f"{name} joined", name)
            else:
                client.send(b"MSG:Room not found\n")

        elif choice=="3":  # Public chats
            public_rooms = [f"{c} - {r['name']} ({len(r['users'])})" for c,r in rooms.items() if r["public"]]
            if not public_rooms:
                client.send(b"MSG:No public rooms\n")
            else:
                client.send(f"MSG:Public Rooms:\n" + "\n".join(public_rooms) + "\n".encode())

        # Chat loop
        while True:
            data = client.recv(4096).decode(errors='ignore').strip()
            if not data: break

            # Admin commands
            if current_room in rooms and rooms[current_room]["admin"] == name:
                if data.startswith("/ban "):
                    target = data[5:].strip()
                    if target in rooms[current_room]["users"]:
                        rooms[current_room]["banned"].add(target)
                        rooms[current_room]["users"].remove(target)
                        if target in active:
                            try:
                                active[target]["client"].send(b"MSG:You were banned by admin!\n")
                                active[target]["client"].close()
                            except: pass
                            del active[target]
                        broadcast(current_room, f"{target} was banned by admin")
                    else:
                        client.send(b"MSG:User not found in room\n")
                    continue

                if data.startswith("/kick "):
                    target = data[6:].strip()
                    if target in rooms[current_room]["users"]:
                        rooms[current_room]["users"].remove(target)
                        if target in active:
                            try:
                                active[target]["client"].send(b"MSG:You were kicked by admin!\n")
                                active[target]["client"].close()
                            except: pass
                            del active[target]
                        broadcast(current_room, f"{target} was kicked by admin")
                    else:
                        client.send(b"MSG:User not found in room\n")
                    continue

                if data.startswith("/remove"):
                    for u in list(rooms[current_room]["users"]):
                        if u in active:
                            try:
                                active[u]["client"].send(b"MSG:This room was removed by admin!\n")
                                active[u]["client"].close()
                            except: pass
                            del active[u]
                    del rooms[current_room]
                    client.send(b"MSG:Room removed successfully\n")
                    break

            # Normal message
            broadcast(current_room, f"{name} > {data}", name)

    finally:
        if name:
            active.pop(name,None)
            users[name]["last_active"] = datetime.utcnow().isoformat()
            save_users()
            for r in rooms.values():
                r["users"].discard(name)
        client.close()
        print(f"[-] {name} ({ip}) disconnected")

# ── Client ─────────────
def start_server_background():
    """Try to start server if not running."""
    s = socket.socket()
    try:
        s.connect(("localhost", PORT))
        s.close()
        return False  # already running
    except:
        # Start server subprocess
        if sys.platform.startswith("win"):
            subprocess.Popen([sys.executable, sys.argv[0], "server"], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([sys.executable, sys.argv[0], "server"])
        time.sleep(1)
        return True

def client_main():
    os.system('cls' if os.name=='nt' else 'clear')
    columns = shutil.get_terminal_size().columns

    # Centered text
    print("\n"*5)
    print(" " * ((columns - len("tchat"))//2) + f"{Style.DIM}{Fore.RED}tchat{Style.RESET_ALL}")
    print(" " * ((columns - len("https://github.com/nicopancakes/tchat"))//2) + "https://github.com/nicopancakes/tchat")
    print("\n"*2)

    # Auto-start server if needed
    print(f"{Fore.YELLOW}Checking server...{Style.RESET_ALL}")
    started = start_server_background()
    if started:
        print(f"{Fore.GREEN}Server started in background!{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Server already running.{Style.RESET_ALL}")

    host = "localhost"
    port = PORT
    print(f"{Fore.YELLOW}Connecting to {host}:{port}...{Style.RESET_ALL}")

    s = socket.socket()
    try:
        s.connect((host, port))
    except Exception as e:
        print(f"{Fore.RED}Connection failed: {e}")
        return

    # Username
    username = input(f"{Fore.CYAN}Enter username (3-20 chars, no spaces): {Style.RESET_ALL}").strip()
    while not (3<=len(username)<=20) or ' ' in username:
        username = input(f"{Fore.RED}Invalid. Enter username: {Style.RESET_ALL}").strip()
    s.send((username+"\n").encode())

    # Menu
    print("\n1) Create Chat  2) Join Chat  3) Public Chats\n")
    choice = input(f"{Fore.GREEN}Choose option [1-3]: {Style.RESET_ALL}").strip()
    s.send((choice+"\n").encode())
    if choice=="1":
        admin = input("Admin? Y/N: ").strip()
        s.send((admin+"\n").encode())
        public = input("Public? Y/N: ").strip()
        s.send((public+"\n").encode())
    elif choice=="2":
        code = input("Enter room code: ").strip()
        s.send((code+"\n").encode())

    # Receive messages
    def recv_loop():
        while True:
            try:
                data = s.recv(4096).decode(errors='ignore').strip()
                if not data: break
                if data.startswith("MSG:"): print(data[4:])
            except: break

    threading.Thread(target=recv_loop, daemon=True).start()

    # Chat input
    try:
        while True:
            msg = input(f"{Fore.GREEN}> ").strip()
            if msg: s.send((msg+"\n").encode())
    except: s.close()

# ── Entry ─────────────
if __name__=="__main__":
    load_users()
    if len(sys.argv)>1 and sys.argv[1].lower()=="server":
        print(f"{Fore.MAGENTA}Server running on port {PORT}...{Style.RESET_ALL}")
        srv = socket.socket()
        srv.bind((HOST, PORT))
        srv.listen(10)
        try:
            while True:
                cl, addr = srv.accept()
                threading.Thread(target=handle_client,args=(cl,addr),daemon=True).start()
        except KeyboardInterrupt: print("\nServer stopped")
    else:
        client_main()
