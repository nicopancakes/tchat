# TChat - Raspberry Pi OS 32-bit Full Script
import socket, threading, random, sys, os, json, time, shutil
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

HOST='0.0.0.0'
PORT=55555
USERS_FILE='users.json'

users={}
active={}
rooms={}

def load_users():
    global users
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE,'r') as f: users=json.load(f)
    else: users={}

def save_users():
    with open(USERS_FILE,'w') as f: json.dump(users,f)

def gen_code(): return ''.join(random.choices("0123456789",k=10))
def gen_username(): return f"User{random.randint(1000,9999)}"

def broadcast(code,msg,exclude=None):
    if code not in rooms: return
    for u in rooms[code]["users"]:
        if u!=exclude and u in active:
            try: active[u]["client"].send(f"MSG:{msg}\n".encode())
            except: pass

def handle_client(client,addr):
    ip = addr[0]
    name = gen_username()
    active[name] = {"client":client,"ip":ip}
    if name not in users:
        users[name] = {"first_seen":datetime.utcnow().isoformat(),"last_active":datetime.utcnow().isoformat()}
    users[name]["last_active"]=datetime.utcnow().isoformat()
    save_users()

    current_room=None

    # Menu loop
    client.send(b"MENU\n")
    while current_room is None:
        try:
            client.send(b"MSG:1) Create Chat\nMSG:2) Join Chat\nMSG:3) Public Chats\nMSG:Select option (1-3):\n")
            option=client.recv(1024).decode(errors='ignore').strip()
            if option=='1':
                client.send(b"MSG:Admin? (Y/N):\n")
                admin_resp=client.recv(1024).decode(errors='ignore').strip().upper()
                is_admin=admin_resp=='Y'
                client.send(b"MSG:Public? (Y/N):\n")
                pub_resp=client.recv(1024).decode(errors='ignore').strip().upper()
                is_public=pub_resp=='Y'
                code=gen_code()
                rooms[code]={"name":f"{name}'s Room","public":is_public,"admin":name if is_admin else None,"users":set([name]),"banned":set()}
                current_room=code
                if not is_public:
                    client.send(f"MSG:Private Room Code: {code}\n".encode())
                broadcast(current_room,f"{name} created the chat")
            elif option=='2':
                client.send(b"MSG:Enter room code:\n")
                code=client.recv(1024).decode(errors='ignore').strip()
                if code in rooms:
                    if name in rooms[code]["banned"]:
                        client.send(b"MSG:You are banned from this room\n")
                        continue
                    rooms[code]["users"].add(name)
                    current_room=code
                    broadcast(current_room,f"{name} joined the chat",name)
                else: client.send(b"MSG:Room not found\n")
            elif option=='3':
                public_list=[r for r in rooms if rooms[r]["public"]]
                client.send(f"MSG:Public Rooms: {', '.join(public_list) or 'None'}\n".encode())
            else:
                client.send(b"MSG:Invalid option\n")
        except:
            client.close()
            return

    client.send(f"MSG:Welcome {name} to {rooms[current_room]['name']}\n".encode())

    while True:
        try:
            data=client.recv(4096).decode(errors='ignore').strip()
            if not data: break

            # Admin commands
            if rooms[current_room].get("admin")==name:
                if data.startswith("/ban "):
                    target=data[5:].strip()
                    if target in rooms[current_room]["users"]:
                        rooms[current_room]["banned"].add(target)
                        rooms[current_room]["users"].remove(target)
                        if target in active:
                            try: active[target]["client"].send(b"MSG:You were banned!\n"); active[target]["client"].close()
                            except: pass; del active[target]
                        broadcast(current_room,f"{target} was banned by admin")
                        continue
                if data.startswith("/kick "):
                    target=data[6:].strip()
                    if target in rooms[current_room]["users"]:
                        rooms[current_room]["users"].remove(target)
                        if target in active:
                            try: active[target]["client"].send(b"MSG:You were kicked!\n"); active[target]["client"].close()
                            except: pass; del active[target]
                        broadcast(current_room,f"{target} was kicked by admin")
                        continue
                if data.startswith("/remove"):
                    for u in list(rooms[current_room]["users"]):
                        if u in active:
                            try: active[u]["client"].send(b"MSG:Room removed by admin!\n"); active[u]["client"].close()
                            except: pass; del active[u]
                    del rooms[current_room]
                    break

            broadcast(current_room,f"{name} > {data}",name)
        except: break

    active.pop(name,None)
    for r in rooms.values(): r["users"].discard(name)
    save_users()
    client.close()

def start_server():
    srv=socket.socket()
    srv.bind((HOST,PORT))
    srv.listen(10)
    print(f"{Fore.MAGENTA}Server running on port {PORT}...{Style.RESET_ALL}")
    try:
        while True:
            cl,addr=srv.accept()
            threading.Thread(target=handle_client,args=(cl,addr),daemon=True).start()
    except KeyboardInterrupt: print("\nServer stopped")

def client_main():
    os.system('clear')
    columns=shutil.get_terminal_size().columns
    print("\n"*5)
    print(" "*((columns-len("tchat"))//2)+f"{Style.DIM}{Fore.RED}tchat{Style.RESET_ALL}")
    print(" "*((columns-len("https://github.com/nicopancakes/tchat"))//2)+"https://github.com/nicopancakes/tchat\n\n")
    time.sleep(0.5)
    s=socket.socket()
    s.connect(("localhost",PORT))

    def recv_loop():
        while True:
            try:
                data=s.recv(4096).decode(errors='ignore').strip()
                if not data: break
                if data.startswith("MSG:"): print(data[4:])
            except: break
    threading.Thread(target=recv_loop,daemon=True).start()

    try:
        while True:
            msg=input(f"{Fore.GREEN}> ").strip()
            if msg: s.send((msg+"\n").encode())
    except: s.close()

if __name__=="__main__":
    load_users()
    if len(sys.argv)>1 and sys.argv[1]=="server":
        start_server()
    else:
        # auto-start server if not running
        try:
            test=socket.socket(); test.connect(("localhost",PORT)); test.close()
        except: 
            os.system(f"python3 {sys.argv[0]} server &")
            time.sleep(1)
        client_main()
