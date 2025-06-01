from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from collections import Counter, defaultdict
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

def find_matches(block, full_data):
    top_matches, bottom_matches = [], []
    block_len = len(block)

    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            # 상단값
            top_idx = i - 1
            top_val = full_data[top_idx] if top_idx >= 0 else "❌ 없음"
            top_matches.append(top_val)

            # 하단값
            bottom_idx = i + block_len
            bottom_val = full_data[bottom_idx] if bottom_idx < len(full_data) else "❌ 없음"
            bottom_matches.append(bottom_val)

    return top_matches[:5], bottom_matches[:5]

@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

@app.route("/predict_top1")
def predict_top1():
    try:
        response = supabase.table(SUPABASE_TABLE) \
            .select("*") \
            .order("reg_date", desc=True) \
            .order("date_round", desc=True) \
            .limit(3000).execute()

        raw = response.data
        round_num = int(raw[0]["date_round"]) + 1
        all_data = [convert(d) for d in raw]

        transform_modes = {
            "orig": lambda x: x,
            "flip_full": flip_full,
            "flip_start": flip_start,
            "flip_odd_even": flip_odd_even
        }

        block_top1 = {}

        for block_size in [3, 4, 5, 6]:
            top_vals, bottom_vals = [], []

            for transform_name, transform_func in transform_modes.items():
                recent_block = all_data[:block_size]
                transformed = transform_func(recent_block)
                top, bottom = find_matches(transformed, all_data)
                top_vals.extend([v for v in top if v != "❌ 없음"])
                bottom_vals.extend([v for v in bottom if v != "❌ 없음"])

            top_counter = Counter(top_vals)
            bottom_counter = Counter(bottom_vals)

            block_top1[f"{block_size}줄"] = {
                "상단Top1": top_counter.most_common(1)[0][0] if top_counter else "❌ 없음",
                "하단Top1": bottom_counter.most_common(1)[0][0] if bottom_counter else "❌ 없음"
            }

        return jsonify({
            "예측회차": round_num,
            "블럭별Top1": block_top1
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
