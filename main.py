from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from collections import Counter
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
    return [('우' if s == '좌' else '좌') + c + ('짝' if o == '홀' else '홀') for s, c, o in map(parse_block, block)]

def flip_start(block):
    return [s + ('4' if c == '3' else '3') + ('홀' if o == '짝' else '짝') for s, c, o in map(parse_block, block)]

def flip_odd_even(block):
    return [('우' if s == '좌' else '좌') + ('4' if c == '3' else '3') + o for s, c, o in map(parse_block, block)]

def find_all_matches(block, full_data):
    top_matches = []
    bottom_matches = []
    block_len = len(block)

    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            top_index = i - 1
            top_pred = full_data[top_index] if top_index >= 0 else "❌ 없음"
            top_matches.append({"값": top_pred, "블럭": ">".join(block), "순번": i + 1})

            bottom_index = i + block_len
            bottom_pred = full_data[bottom_index] if bottom_index < len(full_data) else "❌ 없음"
            bottom_matches.append({"값": bottom_pred, "블럭": ">".join(block), "순번": i + 1})

    top_matches = sorted(top_matches, key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 99999)[:5]
    bottom_matches = sorted(bottom_matches, key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 99999)[:5]

    return top_matches, bottom_matches

@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

@app.route("/predict")
def predict():
    try:
        mode = request.args.get("mode", "3block_orig")
        size = int(mode[0])

        response = supabase.table(SUPABASE_TABLE).select("*") \
            .order("reg_date", desc=True).order("date_round", desc=True).limit(3000).execute()
        raw = response.data
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

        top, bottom = find_all_matches(flow, all_data)

        return jsonify({
            "예측회차": round_num,
            "상단값들": top,
            "하단값들": bottom
        })

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/predict_top1_summary")
def predict_top1_summary():
    try:
        response = supabase.table(SUPABASE_TABLE).select("*") \
            .order("reg_date", desc=True).order("date_round", desc=True).limit(3000).execute()
        raw = response.data
        all_data = [convert(d) for d in raw]

        transform_modes = {
            "orig": lambda x: x,
            "flip_full": flip_full,
            "flip_start": flip_start,
            "flip_odd_even": flip_odd_even
        }

        summary = {}

        for size in [3, 4, 5, 6]:
            top_values = []
            bottom_values = []

            for transform_fn in transform_modes.values():
                recent_block = all_data[:size]
                flow = transform_fn(recent_block)
                top, bottom = find_all_matches(flow, all_data)
                top_values += [v["값"] for v in top if v["값"] != "❌ 없음"]
                bottom_values += [v["값"] for v in bottom if v["값"] != "❌ 없음"]

            top_counter = Counter(top_values)
            bottom_counter = Counter(bottom_values)

            summary[f"{size}줄"] = {
                "Top1상단": top_counter.most_common(1)[0][0] if top_counter else "❌ 없음",
                "Top1하단": bottom_counter.most_common(1)[0][0] if bottom_counter else "❌ 없음"
            }

        return jsonify({"Top1요약": summary})
    except Exception as e:
        return jsonify({"error": str(e)})
