from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
import os

# .env 환경변수 로드
load_dotenv()

app = Flask(__name__)
CORS(app)

# Supabase 연결 정보
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "ladder")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 사다리 결과값 변환
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

def find_top_matches(block, full_data):
    matches = []
    block_len = len(block)
    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            pred_index = i - 1
            pred = full_data[pred_index] if pred_index >= 0 else "❌ 없음"
            matches.append({
                "값": pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })
    return matches[:5] if matches else [{
        "값": "❌ 없음",
        "블럭": ">".join(block),
        "순번": "❌"
    }]

def find_bottom_matches(block, full_data):
    matches = []
    block_len = len(block)
    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            pred_index = i + block_len
            pred = full_data[pred_index] if pred_index < len(full_data) else "❌ 없음"
            matches.append({
                "값": pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })
    return matches[:5] if matches else [{
        "값": "❌ 없음",
        "블럭": ">".join(block),
        "순번": "❌"
    }]

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

        top_matches = find_top_matches(flow, all_data)
        bottom_matches = find_bottom_matches(flow, all_data)

        return jsonify({
            "예측회차": round_num,
            "상단값들": top_matches,
            "하단값들": bottom_matches
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
