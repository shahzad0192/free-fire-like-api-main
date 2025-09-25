from flask import Flask, request, jsonify
import asyncio, json, binascii, requests, aiohttp, urllib3, os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
from google.protobuf.message import DecodeError
import like_pb2, like_count_pb2, uid_generator_pb2
from config import URLS_INFO, URLS_LIKE, FILES, DEFAULT_TOKEN_FILE

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)

def load_tokens(server):
    """Load tokens for specific server and convert to list format"""
    try:
        # Get the token file name for this server
        token_file = FILES.get(server, DEFAULT_TOKEN_FILE)
        file_path = f"tokens/{token_file}"
        
        # Load the JSON file
        with open(file_path, 'r') as f:
            tokens_dict = json.load(f)
        
        # Convert dictionary to list format that your code expects
        tokens_list = []
        for key, token_value in tokens_dict.items():
            if key.startswith('token'):  # Only process token keys
                tokens_list.append({"token": token_value})
        
        print(f"Loaded {len(tokens_list)} tokens for server {server} from {token_file}")
        return tokens_list
        
    except FileNotFoundError:
        print(f"Token file not found: {file_path}")
        return []
    except Exception as e:
        print(f"Error loading tokens: {e}")
        return []

def get_headers(token):
    return {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip", 
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB50",
    }

def encrypt_message(data):
    cipher = AES.new(b'Yg&tc%DEuh6%Zc^8', AES.MODE_CBC, b'6oyZDr22E3ychjM%')
    return binascii.hexlify(cipher.encrypt(pad(data, AES.block_size))).decode()

def create_like(uid, region):
    m = like_pb2.like()
    m.uid, m.region = int(uid), region
    return m.SerializeToString()

def create_uid(uid):
    m = uid_generator_pb2.uid_generator()
    m.saturn_, m.garena = int(uid), 1
    return m.SerializeToString()

async def send(token, url, data):
    headers = get_headers(token)
    async with aiohttp.ClientSession() as s:
        async with s.post(url, data=bytes.fromhex(data), headers=headers) as r: 
            return await r.text() if r.status == 200 else None

async def multi(uid, server, url):
    enc = encrypt_message(create_like(uid, server))
    tokens = load_tokens(server)
    
    if not tokens:
        raise Exception(f"No tokens found for server {server}")
    
    print(f"Using {len(tokens)} tokens for {len(tokens)} requests")
    return await asyncio.gather(*[send(tokens[i % len(tokens)]['token'], url, enc) for i in range(len(tokens))])

def get_info(enc, server, token):
    urls = URLS_INFO
    r = requests.post(urls.get(server, "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"),
                      data=bytes.fromhex(enc), headers=get_headers(token), verify=False)
    try: 
        p = like_count_pb2.Info()
        p.ParseFromString(r.content)
        return p
    except DecodeError: 
        return None

@app.route("/like")
def like():
    uid = request.args.get("uid")
    server = request.args.get("server", "").upper()
    
    if not uid or not server: 
        return jsonify(error="UID and server required"), 400
    
    try:
        tokens = load_tokens(server)
        if not tokens:
            return jsonify(error=f"No tokens available for server {server}"), 500
        
        enc = encrypt_message(create_uid(uid))
        before, tok = None, None
        
        for t in tokens[:10]:  # Try first 10 tokens
            before = get_info(enc, server, t["token"])
            if before: 
                tok = t["token"]
                break
        
        if not before: 
            return jsonify(error="Player not found"), 500
        
        before_like = int(json.loads(MessageToJson(before)).get('AccountInfo', {}).get('Likes', 0))
        urls = URLS_LIKE
        
        # Send likes using available tokens
        asyncio.run(multi(uid, server, urls.get(server, "https://clientbp.ggblueshark.com/LikeProfile")))
        
        after = json.loads(MessageToJson(get_info(enc, server, tok)))
        after_like = int(after.get('AccountInfo', {}).get('Likes', 0))
        
        likes_added = after_like - before_like
        
        return jsonify({
            "credits": "great.thug4ff.com",
            "likes_added": likes_added,
            "likes_before": before_like,
            "likes_after": after_like,
            "player": after.get('AccountInfo', {}).get('PlayerNickname', ''),
            "uid": after.get('AccountInfo', {}).get('UID', 0),
            "status": 1 if likes_added > 0 else 2,
            "tokens_used": len(tokens)
        })
        
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route("/tokens")
def token_info():
    """Check available tokens for each server"""
    token_info = {}
    for server in FILES.keys():
        tokens = load_tokens(server)
        token_info[server] = {
            "token_count": len(tokens),
            "token_file": FILES.get(server, DEFAULT_TOKEN_FILE)
        }
    return jsonify(token_info)

if __name__ == "__main__":
    # Create tokens directory if it doesn't exist
    os.makedirs("tokens", exist_ok=True)
    app.run(debug=True, use_reloader=False)