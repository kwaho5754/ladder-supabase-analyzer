from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "ladder")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def convert(entry):
    side = '좌' if entry['start_point'] == 'LEFT' else '우'
    count = str(entry['line_count'])
    oe = '짝' if entry['odd_even'] == 'EVEN' else '홀'
    return f"{side}{count}{oe}"

def parse_block(s):
    return s[0], s[1:-1], s[-1]

def flip_full(block):
    return [
        ('우' if s == '좌' else '좌') + c + ('짝' if o == '홀' else '홀')
        for s, c, o in map(parse_block, block)
    ]

def flip_start(block):
    return [
        s + ('4' if c == '3' else '3') + ('홀' if o == '짝' else '짝')
        for s, c, o in map(parse_block, block)
    ]

def flip_odd_even(block):
    return [
        ('우' if s == '좌' else '좌') + ('4' if c == '3' else '3') + o
        for s, c, o in map(parse_block, block)
    ]

def find_all_matches(block, full_data, mode="above"):
    matches = []
    block_len = len(block)
    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            if mode == "above":
                pred_index = i - 1
            else:
                pred_index = i + block_len
            if 0 <= pred_index < len(full_data):
                pred = full_data[pred_index]
            else:
                pred = "❌ 없음"
            matches.append({
                "값": pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })
    if not matches:
        matches.append({
            "값": "❌ 없음",
            "블럭": ">".join(block),
            "순번": "❌"
        })
    return matches

@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

@app.route("/predict")
def predict():
    try:
        mode = request.args.get("mode", "3block_orig")
        size = int(mode[0])

        response = supabase.table(SUPABASE_TABLE) \
            .select("*") \
            .order("reg_date", desc=True) \
            .order("date_round", desc=True) \
            .limit(3000) \
            .execute()

        raw = response.data
        print("[📦 Supabase 첫 줄]", raw[0])

        round_num = int(raw[0]["date_round"]) + 1

        all_data = [convert(d) for d in raw]
        recent_flow = all_data[:size]

        if "flip_full" in mode:
            flow = flip_full(recent_flow)
        elif "flip_start" in mode:
            flow = flip_start(recent_flow)
        elif "flip_odd_even" in mode:
            flow = flip_odd_even(recent_flow)
        else:
            flow = recent_flow

        matches_above = find_all_matches(flow, all_data, mode="above")
        matches_below = find_all_matches(flow, all_data, mode="below")

        matches_above = sorted(matches_above, key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 99999)[:5]
        matches_below = sorted(matches_below, key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 99999)[:5]

        return jsonify({
            "예측회차": round_num,
            "상단기준": matches_above,
            "하단기준": matches_below
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
