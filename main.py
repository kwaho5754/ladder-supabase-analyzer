from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from collections import Counter

load_dotenv()

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "ladder")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def convert(entry):
    side = '좌' if entry['start_point'] == 'LEFT' else '우'
    count = '삼' if entry['line_count'] == 3 else '사'
    oe = '짝' if entry['odd_even'] == 'EVEN' else '홀'
    return f"{side}{count}{oe}"

def parse_block(s):
    return s[0], s[1], s[2]

def flip_full(block):
    return [("우" if s == "좌" else "좌") + c + ("짝" if o == "홀" else "홀") for s, c, o in map(parse_block, block)]

def flip_start(block):
    return [("우" if s == "좌" else "좌") + c + o for s, c, o in map(parse_block, block)]

def flip_odd_even(block):
    return [s + c + ("짝" if o == "홀" else "홀") for s, c, o in map(parse_block, block)]

def find_matching_predictions(block, data):
    block_len = len(block)
    predictions = []
    for i in reversed(range(block_len, len(data))):
        candidate = data[i-block_len:i]
        if candidate == block:
            prev_index = i - block_len - 1
            if 0 <= prev_index < len(data):
                predictions.append(data[prev_index])
    return predictions

@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

@app.route("/predict_top3_summary")
def predict_summary():
    try:
        response = supabase.table(SUPABASE_TABLE)\
            .select("*")\
            .order("reg_date", desc=True)\
            .order("date_round", desc=True)\
            .limit(5000)\
            .execute()

        raw = response.data
        all_data = [convert(d) for d in raw]
        recent_block = all_data[:4]  # 최근 4줄 블럭

        blocks = {
            "원본": recent_block,
            "완전대칭": flip_full(recent_block),
            "시작점반전": flip_start(recent_block),
            "홀짝반전": flip_odd_even(recent_block)
        }

        total_predictions = []
        for name, blk in blocks.items():
            preds = find_matching_predictions(blk, all_data)
            total_predictions.extend(preds)

        valid_set = {"좌삼짝", "우삼홀", "좌사홀", "우사짝"}
        filtered = [p for p in total_predictions if p in valid_set]

        if len(set(filtered)) < 2:
            return jsonify({
                "예측 그룹 (3/4)": [],
                "제외값": "데이터 부족",
                "설명": "4가지 방향 모두에서 유효한 예측값 부족"
            })

        counter = Counter(filtered)
        excluded = sorted(counter.items(), key=lambda x: x[1])[0][0]
        group = [k for k in valid_set if k != excluded and k in counter]

        return jsonify({
            "예측 그룹 (3/4)": [f"{g} ({counter[g]}회)" for g in group],
            "제외값": f"{excluded} ({counter.get(excluded, 0)}회)",
            "설명": "4줄 블럭 기준, 4방향(원본/대칭/시작반전/홀짝반전) 매칭 → 가장 적은 1개 제외 방식"
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
