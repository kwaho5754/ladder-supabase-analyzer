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

def find_all_matches(block, full_data):
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
    if not matches:
        matches.append({
            "값": "❌ 없음",
            "블럭": "❌ 없음",
            "순번": "없음"
        })
    return matches

# index.html 반환
@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

# 예측 API
@app.route("/predict")
def predict():
    try:
        mode = request.args.get("mode", "3block_orig")
        size = int(mode[0])

        # 🔧 최신 회차 기준 정렬 (date_round만 사용)
        response = supabase.table(SUPABASE_TABLE) \
            .select("*") \
            .order("date_round", desc=True) \
            .limit(3000) \
            .execute()

        raw = list(reversed(response.data))
        print("[📦 Supabase 첫 줄]", raw[0])  # 🔍 디버깅용 출력

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

        matches = find_all_matches(flow, all_data)

        return jsonify({
            "예측회차": round_num,
            "예측값들": matches
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# 실행
if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
